from __future__ import annotations

import sys
from pathlib import Path

INFRA_DIR = Path(__file__).resolve().parents[1] / "infra"
sys.path.insert(0, str(INFRA_DIR))

from cdk_scope import resolve_cdk_scope
from lambda_bundle import (
    CODE_ASSET_EXCLUDE,
    LocalPythonCodeBundling,
    LocalPythonCombinedBundling,
    LocalPythonDepsBundling,
    _deps_asset_exclude,
    _profile_asset_hash,
    meshflow_lambda_code,
    meshflow_lambda_deps_code,
)


def test_deps_asset_exclude_only_tracks_requirements() -> None:
    ui_exclude = _deps_asset_exclude("ui")
    assert "!requirements-lambda-ui.txt" in ui_exclude
    assert "**" in ui_exclude


def test_code_asset_exclude_tracks_meshflow_source() -> None:
    assert "!packages/meshflow-platform/src/meshflow/**" in CODE_ASSET_EXCLUDE
    assert "!packages/meshflow-portal/src/meshflow/**" in CODE_ASSET_EXCLUDE
    assert "!config.yaml" in CODE_ASSET_EXCLUDE


def test_meshflow_lambda_code_factory_returns_asset() -> None:
    first = meshflow_lambda_code()
    second = meshflow_lambda_code()
    assert first is not second
    assert first.path == second.path


def test_meshflow_lambda_deps_code_factory_returns_asset() -> None:
    first = meshflow_lambda_deps_code()
    second = meshflow_lambda_deps_code()
    assert first is not second
    assert first.path == second.path


def test_local_code_bundling_copies_meshflow(tmp_path) -> None:
    output_dir = tmp_path / "bundle"
    output_dir.mkdir()
    assert LocalPythonCodeBundling().try_bundle(str(output_dir), None) is True
    assert (output_dir / "meshflow" / "__init__.py").exists()
    assert (output_dir / "config.yaml").exists()


def test_resolve_cdk_scope_defaults_to_all() -> None:
    assert resolve_cdk_scope() == "all"


def test_resolve_cdk_scope_accepts_platform_and_ingest() -> None:
    assert resolve_cdk_scope(context="platform") == "platform"
    assert resolve_cdk_scope(env="ingest") == "ingest"


def test_resolve_cdk_scope_rejects_unknown_values() -> None:
    try:
        resolve_cdk_scope(context="ui-only")
    except ValueError as exc:
        assert "Invalid CDK scope" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_profile_asset_hash_differs_between_ui_and_reporting() -> None:
    assert _profile_asset_hash("ui") != _profile_asset_hash("reporting")


def test_local_combined_reporting_bundling_includes_pyarrow(tmp_path) -> None:
    output_dir = tmp_path / "bundle"
    output_dir.mkdir()
    assert LocalPythonCombinedBundling("reporting").try_bundle(str(output_dir), None) is True
    assert (output_dir / "pyarrow" / "__init__.py").exists()
    assert (output_dir / "meshflow" / "__init__.py").exists()
    assert (output_dir / "typing_extensions.py").exists()
    referencing_dist = next(output_dir.glob("referencing-*.dist-info"))
    version = next(
        line.split(":", 1)[1].strip()
        for line in referencing_dist.joinpath("METADATA").read_text(encoding="utf-8").splitlines()
        if line.startswith("Version:")
    )
    major, minor, *_ = (int(part) for part in version.split("."))
    assert (major, minor) < (0, 36)
