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
UI_BUNDLE_REVISION = "20260818-spreadsheet-openpyxl"

# Bump when DNA/ingest code Lambda must redeploy even if CDK asset cache is stale.
DNA_BUNDLE_REVISION = "20260819-spreadsheet-induction-fallback"

LambdaDepsProfile = Literal["full", "ui", "reporting"]

_PROFILE_REQUIREMENTS: dict[LambdaDepsProfile, str] = {
    "full": "requirements.txt",
    "ui": "requirements-lambda-ui.txt",
    "reporting": "requirements-lambda-reporting.txt",
}

PACKAGE_HIVEFLOW_ROOTS: tuple[Path, ...] = (
    PROJECT_ROOT / "packages" / "hiveflow-platform" / "src" / "hiveflow",
    PROJECT_ROOT / "packages" / "hiveflow-connectors" / "src" / "hiveflow",
    PROJECT_ROOT / "packages" / "hiveflow-lake" / "src" / "hiveflow",
    PROJECT_ROOT / "packages" / "hiveflow-dna" / "src" / "hiveflow",
    PROJECT_ROOT / "packages" / "hiveflow-portal" / "src" / "hiveflow",
    PROJECT_ROOT / "packages" / "hiveflow" / "src" / "hiveflow",
)

_PACKAGE_INCLUDE_GLOBS = [
    "!packages/hiveflow-platform/src/hiveflow/**",
    "!packages/hiveflow-connectors/src/hiveflow/**",
    "!packages/hiveflow-lake/src/hiveflow/**",
    "!packages/hiveflow-dna/src/hiveflow/**",
    "!packages/hiveflow-portal/src/hiveflow/**",
    "!packages/hiveflow/src/hiveflow/**",
]

CODE_ASSET_EXCLUDE = [
    "**",
    *_PACKAGE_INCLUDE_GLOBS,
    "!config.yaml",
    "!process_config.yaml",
]

PIP_PLATFORM = "manylinux2014_x86_64"
PIP_PYTHON = "3.12"


def assemble_hiveflow_tree(dest: Path) -> None:
    """Merge installable package src trees into a single ``hiveflow`` package dir."""
    dest.mkdir(parents=True, exist_ok=True)
    for root in PACKAGE_HIVEFLOW_ROOTS:
        if root.is_dir():
            shutil.copytree(root, dest, dirs_exist_ok=True)


def iter_hiveflow_source_files() -> list[tuple[str, Path]]:
    files: list[tuple[str, Path]] = []
    for root in PACKAGE_HIVEFLOW_ROOTS:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if path.is_file():
                rel = path.relative_to(root).as_posix()
                files.append((f"{root.parent.parent.name}:{rel}", path))
    return files


def _deps_asset_exclude(profile: LambdaDepsProfile) -> list[str]:
    requirements_file = _PROFILE_REQUIREMENTS[profile]
    return ["**", f"!{requirements_file}"]


def _combined_asset_exclude(profile: LambdaDepsProfile) -> list[str]:
    requirements_file = _PROFILE_REQUIREMENTS[profile]
    return [
        "**",
        f"!{requirements_file}",
        *_PACKAGE_INCLUDE_GLOBS,
        "!config.yaml",
        "!process_config.yaml",
    ]


def _requirements_path(profile: LambdaDepsProfile) -> Path:
    return PROJECT_ROOT / _PROFILE_REQUIREMENTS[profile]


def _hash_hiveflow_sources(digest: "hashlib._Hash") -> None:
    for label, path in iter_hiveflow_source_files():
        digest.update(label.encode("utf-8"))
        digest.update(path.read_bytes())


def _profile_asset_hash(profile: LambdaDepsProfile) -> str:
    """Content-aware hash so UI/reporting Lambdas redeploy when source changes."""
    digest = hashlib.sha256(f"{UI_BUNDLE_REVISION}:{profile}".encode("utf-8"))
    digest.update(_requirements_path(profile).read_bytes())
    _hash_hiveflow_sources(digest)
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


def _copy_runtime_config(output_dir: Path) -> None:
    shutil.copy2(PROJECT_ROOT / "config.yaml", output_dir / "config.yaml")
    process_config = PROJECT_ROOT / "process_config.yaml"
    if process_config.exists():
        shutil.copy2(process_config, output_dir / "process_config.yaml")


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
    """Install deps and copy hiveflow into one Lambda package (no layer)."""

    def __init__(self, profile: LambdaDepsProfile = "full") -> None:
        self._profile = profile

    def try_bundle(self, output_dir: str, _options: BundlingOptions) -> bool:
        try:
            subprocess.run(
                _pip_install_command(output_dir, self._profile),
                check=True,
                capture_output=True,
            )
            assemble_hiveflow_tree(Path(output_dir) / "hiveflow")
            _copy_runtime_config(Path(output_dir))
            (Path(output_dir) / ".hiveflow-bundle-rev").write_text(
                f"{UI_BUNDLE_REVISION}:{self._profile}\n",
                encoding="utf-8",
            )
        except (subprocess.CalledProcessError, OSError):
            return False
        return True


@jsii.implements(ILocalBundling)
class LocalPythonCodeBundling:
    """Copy hiveflow source and config locally when Docker is unavailable."""

    def try_bundle(self, output_dir: str, _options: BundlingOptions) -> bool:
        try:
            assemble_hiveflow_tree(Path(output_dir) / "hiveflow")
            _copy_runtime_config(Path(output_dir))
            (Path(output_dir) / ".hiveflow-dna-bundle-rev").write_text(
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


def _docker_assemble_hiveflow() -> str:
    """Bash snippet: merge package src trees into /asset-output/hiveflow."""
    copies = " && ".join(
        (
            "cp -a /asset-input/packages/hiveflow-platform/src/hiveflow/. /asset-output/hiveflow/",
            "cp -a /asset-input/packages/hiveflow-connectors/src/hiveflow/. /asset-output/hiveflow/",
            "cp -a /asset-input/packages/hiveflow-lake/src/hiveflow/. /asset-output/hiveflow/",
            "cp -a /asset-input/packages/hiveflow-dna/src/hiveflow/. /asset-output/hiveflow/",
            "cp -a /asset-input/packages/hiveflow-portal/src/hiveflow/. /asset-output/hiveflow/",
            "cp -a /asset-input/packages/hiveflow/src/hiveflow/. /asset-output/hiveflow/",
        )
    )
    return f"mkdir -p /asset-output/hiveflow && {copies}"


def _docker_combined_command(profile: LambdaDepsProfile) -> str:
    requirements_file = _PROFILE_REQUIREMENTS[profile]
    return (
        f"pip install -r /asset-input/{requirements_file} -t /asset-output && "
        f"{_docker_assemble_hiveflow()} && "
        "cp /asset-input/config.yaml /asset-output/config.yaml && "
        f"echo {UI_BUNDLE_REVISION}:{profile} > /asset-output/.hiveflow-bundle-rev && "
        "(test -f /asset-input/process_config.yaml && "
        "cp /asset-input/process_config.yaml /asset-output/process_config.yaml || true)"
    )


def hiveflow_lambda_combined_code(profile: LambdaDepsProfile = "full") -> _lambda.Code:
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


def hiveflow_lambda_deps_code(profile: LambdaDepsProfile = "full") -> _lambda.Code:
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
    _hash_hiveflow_sources(digest)
    for name in ("config.yaml", "process_config.yaml"):
        candidate = PROJECT_ROOT / name
        if candidate.is_file():
            digest.update(name.encode("utf-8"))
            digest.update(candidate.read_bytes())
    return digest.hexdigest()[:32]


def hiveflow_lambda_code() -> _lambda.Code:
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
                f"{_docker_assemble_hiveflow()} && "
                "cp /asset-input/config.yaml /asset-output/config.yaml && "
                f"echo {DNA_BUNDLE_REVISION} > /asset-output/.hiveflow-dna-bundle-rev && "
                "(test -f /asset-input/process_config.yaml && "
                "cp /asset-input/process_config.yaml /asset-output/process_config.yaml || true)",
            ],
            local=LocalPythonCodeBundling(),
        ),
    )


def hiveflow_lambda_deps_layer(
    scope: Construct,
    construct_id: str,
    *,
    profile: LambdaDepsProfile = "full",
) -> _lambda.LayerVersion:
    descriptions = {
        "full": "HiveFlow full Python dependencies (ingest/DNA)",
        "ui": "HiveFlow UI Python dependencies (global site/login)",
        "reporting": "HiveFlow reporting Python dependencies (charts/KPIs)",
    }
    return _lambda.LayerVersion(
        scope,
        construct_id,
        code=hiveflow_lambda_deps_code(profile),
        compatible_runtimes=[_lambda.Runtime.PYTHON_3_12],
        description=descriptions[profile],
    )


@dataclass(frozen=True)
class HiveFlowLambdaRuntime:
    code: _lambda.Code
    layers: list[_lambda.ILayerVersion]


def hiveflow_lambda_runtime(
    scope: Construct,
    layer_id: str = "HiveFlowDeps",
    *,
    profile: LambdaDepsProfile = "full",
) -> HiveFlowLambdaRuntime:
    # Single zip per function — avoids Lambda's 250MB unzipped function+layers cap.
    # A HiveFlowDeps layer on functions that still carry an older combined zip
    # duplicates pip deps (~220MB + ~220MB) and fails deploy.
    _ = layer_id  # kept for call-site compatibility; layers are no longer used
    return HiveFlowLambdaRuntime(
        code=hiveflow_lambda_combined_code(profile),
        layers=[],
    )
