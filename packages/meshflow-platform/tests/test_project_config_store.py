"""Tests for Lambda/CodeBuild config.yaml persistence helpers."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from meshflow.project_config import (
    LAMBDA_WRITABLE_CONFIG_PATH,
    ensure_writable_config_path,
    refresh_platform_config,
    save_project_config,
    sync_config_for_codebuild,
)


def test_ensure_writable_config_path_uses_tmp_in_lambda(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundled = tmp_path / "config.yaml"
    bundled.write_text("companies: {}\n", encoding="utf-8")
    monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "platform-dev-platform-admin-serve")
    monkeypatch.delenv("MESHFLOW_CONFIG_PATH", raising=False)
    monkeypatch.delenv("MESHFLOW_CONFIG_S3_URI", raising=False)
    monkeypatch.setattr(
        "meshflow.project_config.bundled_config_path",
        lambda: bundled,
    )
    monkeypatch.setattr(
        "meshflow.project_config.LAMBDA_WRITABLE_CONFIG_PATH",
        tmp_path / "writable" / "config.yaml",
    )

    resolved = ensure_writable_config_path()

    assert resolved == tmp_path / "writable" / "config.yaml"
    assert resolved.is_file()
    assert resolved.read_text(encoding="utf-8") == "companies: {}\n"


def test_save_project_config_uploads_to_s3(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "config.yaml"
    uploads: list[tuple[str, Path]] = []

    monkeypatch.setenv("MESHFLOW_CONFIG_S3_URI", "s3://platform-config/config.yaml")
    monkeypatch.setattr(
        "meshflow.project_config.sync_config_to_s3",
        lambda source, uri=None: uploads.append(((uri or "s3://platform-config/config.yaml"), source)),
    )

    payload = {"companies": {"acme": {"environments": {"dev": {}}}}}
    saved = save_project_config(payload, config_path)

    assert saved == config_path
    assert yaml.safe_load(config_path.read_text(encoding="utf-8")) == payload
    assert uploads == [("s3://platform-config/config.yaml", config_path)]


def test_refresh_platform_config_downloads_latest_copy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dest = tmp_path / "config.yaml"
    source = tmp_path / "source.yaml"
    source.write_text("companies:\n  poc2: {}\n", encoding="utf-8")

    monkeypatch.setenv("MESHFLOW_CONFIG_S3_URI", "s3://platform-config/config.yaml")
    monkeypatch.setenv("MESHFLOW_CONFIG_PATH", str(dest))
    monkeypatch.setattr(
        "meshflow.project_config.download_config_from_s3",
        lambda uri, path: (
            path.parent.mkdir(parents=True, exist_ok=True),
            path.write_text(source.read_text(encoding="utf-8"), encoding="utf-8"),
            True,
        )[-1],
    )

    resolved = refresh_platform_config()

    assert resolved == dest
    assert "poc2" in dest.read_text(encoding="utf-8")


def test_sync_config_for_codebuild_downloads_repo_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    dest = repo_root / "config.yaml"
    source = tmp_path / "source.yaml"
    source.write_text("platform:\n  environments: {}\n", encoding="utf-8")

    monkeypatch.setenv("MESHFLOW_CONFIG_S3_URI", "s3://platform-config/config.yaml")
    monkeypatch.setattr("meshflow.project_config.find_project_root", lambda: repo_root)
    monkeypatch.setattr(
        "meshflow.project_config.download_config_from_s3",
        lambda uri, path: (
            path.parent.mkdir(parents=True, exist_ok=True),
            path.write_text(source.read_text(encoding="utf-8"), encoding="utf-8"),
            True,
        )[-1],
    )

    resolved = sync_config_for_codebuild()

    assert resolved == dest
    assert dest.is_file()
    assert dest.read_text(encoding="utf-8") == source.read_text(encoding="utf-8")


def test_ensure_writable_config_path_keeps_local_repo_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AWS_LAMBDA_FUNCTION_NAME", raising=False)
    monkeypatch.delenv("MESHFLOW_CONFIG_PATH", raising=False)

    resolved = ensure_writable_config_path()

    assert resolved.name == "config.yaml"
    assert resolved != LAMBDA_WRITABLE_CONFIG_PATH
