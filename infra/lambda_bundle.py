from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import jsii
from aws_cdk import AssetHashType, BundlingOptions, ILocalBundling, aws_lambda as _lambda
from constructs import Construct

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Bump when UI/reporting Lambda code must redeploy even if CDK asset cache is stale.
UI_BUNDLE_REVISION = "20260805-kpi-format-deny"

# Bump when DNA/ingest code Lambda must redeploy even if CDK asset cache is stale.
DNA_BUNDLE_REVISION = "20260804-company-dna-config"

LambdaDepsProfile = Literal["full", "ui", "reporting"]

_PROFILE_REQUIREMENTS: dict[LambdaDepsProfile, str] = {
    "full": "requirements.txt",
    "ui": "requirements-lambda-ui.txt",
    "reporting": "requirements-lambda-reporting.txt",
}

CODE_ASSET_EXCLUDE = [
    "**",
    "!src/meshflow/**",
    "!config.yaml",
    "!process_config.yaml",
]

PIP_PLATFORM = "manylinux2014_x86_64"
PIP_PYTHON = "3.12"


def _deps_asset_exclude(profile: LambdaDepsProfile) -> list[str]:
    requirements_file = _PROFILE_REQUIREMENTS[profile]
    return ["**", f"!{requirements_file}"]


def _combined_asset_exclude(profile: LambdaDepsProfile) -> list[str]:
    requirements_file = _PROFILE_REQUIREMENTS[profile]
    return [
        "**",
        f"!{requirements_file}",
        "!src/meshflow/**",
        "!config.yaml",
        "!process_config.yaml",
    ]


def _requirements_path(profile: LambdaDepsProfile) -> Path:
    return PROJECT_ROOT / _PROFILE_REQUIREMENTS[profile]


def _profile_asset_hash(profile: LambdaDepsProfile) -> str:
    """Content-aware hash so UI/reporting Lambdas redeploy when source changes."""
    digest = hashlib.sha256(f"{UI_BUNDLE_REVISION}:{profile}".encode("utf-8"))
    digest.update(_requirements_path(profile).read_bytes())
    root = PROJECT_ROOT / "src" / "meshflow"
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(path.read_bytes())
    for name in ("config.yaml", "process_config.yaml"):
        candidate = PROJECT_ROOT / name
        if candidate.is_file():
            digest.update(name.encode("utf-8"))
            digest.update(candidate.read_bytes())
    return digest.hexdigest()[:32]


def _pip_install_command(output_dir: str, profile: LambdaDepsProfile) -> list[str]:
    return [
        sys.executable,
        "-m",
        "pip",
        "install",
        "-t",
        output_dir,
        "--platform",
        PIP_PLATFORM,
        "--python-version",
        PIP_PYTHON,
        "--only-binary=:all:",
        "-r",
        str(_requirements_path(profile)),
    ]


@jsii.implements(ILocalBundling)
class LocalPythonDepsBundling:
    """Install Lambda dependencies locally when Docker is unavailable."""

    def __init__(self, profile: LambdaDepsProfile = "full") -> None:
        self._profile = profile

    def try_bundle(self, output_dir: str, _options: BundlingOptions) -> bool:
        python_dir = Path(output_dir) / "python"
        python_dir.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.run(
                _pip_install_command(str(python_dir), self._profile),
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError:
            return False
        return True


@jsii.implements(ILocalBundling)
class LocalPythonCombinedBundling:
    """Install deps and copy meshflow into one Lambda package (no layer)."""

    def __init__(self, profile: LambdaDepsProfile = "full") -> None:
        self._profile = profile

    def try_bundle(self, output_dir: str, _options: BundlingOptions) -> bool:
        try:
            subprocess.run(
                _pip_install_command(output_dir, self._profile),
                check=True,
                capture_output=True,
            )
            shutil.copytree(
                PROJECT_ROOT / "src" / "meshflow",
                Path(output_dir) / "meshflow",
                dirs_exist_ok=True,
            )
            shutil.copy2(PROJECT_ROOT / "config.yaml", Path(output_dir) / "config.yaml")
            process_config = PROJECT_ROOT / "process_config.yaml"
            if process_config.exists():
                shutil.copy2(process_config, Path(output_dir) / "process_config.yaml")
            (Path(output_dir) / ".meshflow-bundle-rev").write_text(
                f"{UI_BUNDLE_REVISION}:{self._profile}\n",
                encoding="utf-8",
            )
        except (subprocess.CalledProcessError, OSError):
            return False
        return True


@jsii.implements(ILocalBundling)
class LocalPythonCodeBundling:
    """Copy meshflow source and config locally when Docker is unavailable."""

    def try_bundle(self, output_dir: str, _options: BundlingOptions) -> bool:
        try:
            shutil.copytree(
                PROJECT_ROOT / "src" / "meshflow",
                Path(output_dir) / "meshflow",
                dirs_exist_ok=True,
            )
            shutil.copy2(PROJECT_ROOT / "config.yaml", Path(output_dir) / "config.yaml")
            process_config = PROJECT_ROOT / "process_config.yaml"
            if process_config.exists():
                shutil.copy2(process_config, Path(output_dir) / "process_config.yaml")
            (Path(output_dir) / ".meshflow-dna-bundle-rev").write_text(
                f"{DNA_BUNDLE_REVISION}\n",
                encoding="utf-8",
            )
        except OSError:
            return False
        return True


# Backward-compatible alias for ingeststack imports.
LocalPythonBundling = LocalPythonDepsBundling


def _docker_deps_command(profile: LambdaDepsProfile) -> str:
    requirements_file = _PROFILE_REQUIREMENTS[profile]
    return f"pip install -r /asset-input/{requirements_file} -t /asset-output/python"


def _docker_combined_command(profile: LambdaDepsProfile) -> str:
    requirements_file = _PROFILE_REQUIREMENTS[profile]
    return (
        f"pip install -r /asset-input/{requirements_file} -t /asset-output && "
        "cp -r /asset-input/src/meshflow /asset-output/meshflow && "
        "cp /asset-input/config.yaml /asset-output/config.yaml && "
        f"echo {UI_BUNDLE_REVISION}:{profile} > /asset-output/.meshflow-bundle-rev && "
        "(test -f /asset-input/process_config.yaml && "
        "cp /asset-input/process_config.yaml /asset-output/process_config.yaml || true)"
    )


def meshflow_lambda_combined_code(profile: LambdaDepsProfile = "full") -> _lambda.Code:
    """Single deployment package — avoids the 250MB function+layers combined limit."""
    return _lambda.Code.from_asset(
        str(PROJECT_ROOT),
        exclude=_combined_asset_exclude(profile),
        asset_hash_type=AssetHashType.CUSTOM,
        asset_hash=_profile_asset_hash(profile),
        bundling=BundlingOptions(
            image=_lambda.Runtime.PYTHON_3_12.bundling_image,
            command=["bash", "-c", _docker_combined_command(profile)],
            local=LocalPythonCombinedBundling(profile),
        ),
    )


def meshflow_lambda_deps_code(profile: LambdaDepsProfile = "full") -> _lambda.Code:
    return _lambda.Code.from_asset(
        str(PROJECT_ROOT),
        exclude=_deps_asset_exclude(profile),
        bundling=BundlingOptions(
            image=_lambda.Runtime.PYTHON_3_12.bundling_image,
            command=["bash", "-c", _docker_deps_command(profile)],
            local=LocalPythonDepsBundling(profile),
        ),
    )


def _dna_code_asset_hash() -> str:
    """Content-aware hash so DNA Lambda redeploys when source or revision changes."""
    digest = hashlib.sha256(DNA_BUNDLE_REVISION.encode("utf-8"))
    root = PROJECT_ROOT / "src" / "meshflow"
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(path.read_bytes())
    for name in ("config.yaml", "process_config.yaml"):
        candidate = PROJECT_ROOT / name
        if candidate.is_file():
            digest.update(name.encode("utf-8"))
            digest.update(candidate.read_bytes())
    return digest.hexdigest()[:32]


def meshflow_lambda_code() -> _lambda.Code:
    return _lambda.Code.from_asset(
        str(PROJECT_ROOT),
        exclude=CODE_ASSET_EXCLUDE,
        asset_hash_type=AssetHashType.CUSTOM,
        asset_hash=_dna_code_asset_hash(),
        bundling=BundlingOptions(
            image=_lambda.Runtime.PYTHON_3_12.bundling_image,
            command=[
                "bash",
                "-c",
                "cp -r /asset-input/src/meshflow /asset-output/meshflow && "
                "cp /asset-input/config.yaml /asset-output/config.yaml && "
                f"echo {DNA_BUNDLE_REVISION} > /asset-output/.meshflow-dna-bundle-rev && "
                "(test -f /asset-input/process_config.yaml && "
                "cp /asset-input/process_config.yaml /asset-output/process_config.yaml || true)",
            ],
            local=LocalPythonCodeBundling(),
        ),
    )


def meshflow_lambda_deps_layer(
    scope: Construct,
    construct_id: str,
    *,
    profile: LambdaDepsProfile = "full",
) -> _lambda.LayerVersion:
    descriptions = {
        "full": "Meshflow full Python dependencies (ingest/DNA)",
        "ui": "Meshflow UI Python dependencies (global site/login)",
        "reporting": "Meshflow reporting Python dependencies (charts/KPIs)",
    }
    return _lambda.LayerVersion(
        scope,
        construct_id,
        code=meshflow_lambda_deps_code(profile),
        compatible_runtimes=[_lambda.Runtime.PYTHON_3_12],
        description=descriptions[profile],
    )


@dataclass(frozen=True)
class MeshflowLambdaRuntime:
    code: _lambda.Code
    layers: list[_lambda.ILayerVersion]


def meshflow_lambda_runtime(
    scope: Construct,
    layer_id: str = "MeshflowDeps",
    *,
    profile: LambdaDepsProfile = "full",
) -> MeshflowLambdaRuntime:
    # UI/reporting use a single slim zip (no layer) to stay under Lambda size limits.
    # Ingest/DNA use layer + code copy for faster rebuilds when only source changes.
    if profile in ("ui", "reporting"):
        return MeshflowLambdaRuntime(
            code=meshflow_lambda_combined_code(profile),
            layers=[],
        )
    return MeshflowLambdaRuntime(
        code=meshflow_lambda_code(),
        layers=[meshflow_lambda_deps_layer(scope, layer_id, profile=profile)],
    )
