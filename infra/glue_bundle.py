from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

import jsii
from aws_cdk import AssetHashType, BundlingOptions, BundlingOutput, ILocalBundling, aws_lambda as _lambda, aws_s3_assets as s3_assets
from constructs import Construct

from lambda_bundle import (
    PROJECT_ROOT,
    assemble_meshflow_tree,
    iter_meshflow_source_files,
    _copy_runtime_config,
)

GLUE_BUNDLE_REVISION = "20260813-glue-py39-compat"
GLUE_PYTHON_VERSION = "3.9"
GLUE_PIP_PLATFORM = "manylinux2014_x86_64"
GLUE_BRONZE_SCRIPT_PATH = PROJECT_ROOT / "scripts" / "glue_bronze_ingest.py"
GLUE_SILVER_SCRIPT_PATH = PROJECT_ROOT / "scripts" / "glue_silver_consolidate.py"
GLUE_REQUIREMENTS_PATH = PROJECT_ROOT / "requirements-glue.txt"


def _glue_pip_install_command(output_dir: str) -> list[str]:
    return [
        sys.executable,
        "-m",
        "pip",
        "install",
        "-t",
        output_dir,
        "--platform",
        GLUE_PIP_PLATFORM,
        "--python-version",
        GLUE_PYTHON_VERSION,
        "--only-binary=:all:",
        "-r",
        str(GLUE_REQUIREMENTS_PATH),
    ]


def _glue_bundle_asset_hash() -> str:
    digest = hashlib.sha256(GLUE_BUNDLE_REVISION.encode("utf-8"))
    digest.update(GLUE_REQUIREMENTS_PATH.read_bytes())
    for label, path in iter_meshflow_source_files():
        digest.update(label.encode("utf-8"))
        digest.update(path.read_bytes())
    for name in ("config.yaml", "process_config.yaml"):
        candidate = PROJECT_ROOT / name
        if candidate.is_file():
            digest.update(name.encode("utf-8"))
            digest.update(candidate.read_bytes())
    return digest.hexdigest()[:32]


def _docker_glue_assemble_meshflow() -> str:
    copies = " && ".join(
        (
            "mkdir -p \"$staging/meshflow\"",
            "cp -a /asset-input/packages/meshflow-platform/src/meshflow/. \"$staging/meshflow/\"",
            "cp -a /asset-input/packages/meshflow-connectors/src/meshflow/. \"$staging/meshflow/\"",
            "cp -a /asset-input/packages/meshflow-lake/src/meshflow/. \"$staging/meshflow/\"",
            "cp -a /asset-input/packages/meshflow-dna/src/meshflow/. \"$staging/meshflow/\"",
            "cp -a /asset-input/packages/meshflow-portal/src/meshflow/. \"$staging/meshflow/\"",
            "cp -a /asset-input/packages/meshflow/src/meshflow/. \"$staging/meshflow/\"",
        )
    )
    return copies


def _docker_glue_bundle_command() -> str:
    return (
        "set -euo pipefail && "
        "staging=$(mktemp -d) && "
        f"pip install -r /asset-input/requirements-glue.txt -t \"$staging\" "
        f"--platform {GLUE_PIP_PLATFORM} --python-version {GLUE_PYTHON_VERSION} "
        f"--only-binary=:all: && "
        f"{_docker_glue_assemble_meshflow()} && "
        "cp /asset-input/config.yaml \"$staging/config.yaml\" && "
        "(test -f /asset-input/process_config.yaml && "
        "cp /asset-input/process_config.yaml \"$staging/process_config.yaml\" || true) && "
        "cd \"$staging\" && zip -qr /asset-output/meshflow-glue-bundle.zip . && "
        "rm -rf \"$staging\""
    )


def _zip_directory(source_dir: Path, zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source_dir.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(source_dir).as_posix())


def _stage_glue_bundle(staging_dir: Path) -> None:
    subprocess.run(
        _glue_pip_install_command(str(staging_dir)),
        check=True,
        capture_output=True,
    )
    assemble_meshflow_tree(staging_dir / "meshflow")
    _copy_runtime_config(staging_dir)


@jsii.implements(ILocalBundling)
class LocalGlueExtraPyFilesBundling:
    """Stage meshflow + deps into a single Glue ``--extra-py-files`` zip archive."""

    def try_bundle(self, output_dir: str, _options: BundlingOptions) -> bool:
        output = Path(output_dir)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                staging = Path(tmp)
                _stage_glue_bundle(staging)
                _zip_directory(staging, output / "meshflow-glue-bundle.zip")
        except (subprocess.CalledProcessError, OSError):
            return False
        return True


@dataclass(frozen=True)
class MeshflowGlueJobAssets:
    script_asset: s3_assets.Asset
    extra_py_files_asset: s3_assets.Asset


MeshflowGlueBronzeAssets = MeshflowGlueJobAssets
MeshflowGlueSilverAssets = MeshflowGlueJobAssets


def meshflow_glue_extra_py_files_asset(scope: Construct) -> s3_assets.Asset:
    """Shared meshflow + dependency zip for Glue Python Shell jobs."""
    return s3_assets.Asset(
        scope,
        "MeshflowGlueBundleAsset",
        path=str(PROJECT_ROOT),
        exclude=["**", "!requirements-glue.txt"],
        bundling=BundlingOptions(
            image=_lambda.Runtime.PYTHON_3_12.bundling_image,
            command=["bash", "-c", _docker_glue_bundle_command()],
            local=LocalGlueExtraPyFilesBundling(),
            output_type=BundlingOutput.ARCHIVED,
        ),
        asset_hash=_glue_bundle_asset_hash(),
        asset_hash_type=AssetHashType.CUSTOM,
    )


def _meshflow_glue_job_assets(
    scope: Construct,
    *,
    script_path: Path,
    script_construct_id: str,
    extra_py_files_asset: s3_assets.Asset | None = None,
) -> MeshflowGlueJobAssets:
    if not script_path.is_file():
        raise FileNotFoundError(f"Glue script not found: {script_path}")

    return MeshflowGlueJobAssets(
        script_asset=s3_assets.Asset(
            scope,
            script_construct_id,
            path=str(script_path),
        ),
        extra_py_files_asset=extra_py_files_asset or meshflow_glue_extra_py_files_asset(scope),
    )


def meshflow_glue_bronze_assets(
    scope: Construct,
    *,
    extra_py_files_asset: s3_assets.Asset | None = None,
) -> MeshflowGlueBronzeAssets:
    """Upload bronze ingest Glue script and dependency zip to the CDK asset bucket."""
    return _meshflow_glue_job_assets(
        scope,
        script_path=GLUE_BRONZE_SCRIPT_PATH,
        script_construct_id="MeshflowGlueBronzeScriptAsset",
        extra_py_files_asset=extra_py_files_asset,
    )


def meshflow_glue_silver_assets(
    scope: Construct,
    *,
    extra_py_files_asset: s3_assets.Asset | None = None,
) -> MeshflowGlueSilverAssets:
    """Upload silver consolidate Glue script and dependency zip to the CDK asset bucket."""
    return _meshflow_glue_job_assets(
        scope,
        script_path=GLUE_SILVER_SCRIPT_PATH,
        script_construct_id="MeshflowGlueSilverScriptAsset",
        extra_py_files_asset=extra_py_files_asset,
    )
