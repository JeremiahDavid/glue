from pathlib import Path

from meshflow.bc.token_store import (
    load_watermarks,
    save_watermarks,
    watermarks_state_path,
)
from meshflow.config import BCSettings


def _bc_settings(tmp_path: Path) -> BCSettings:
    return BCSettings(
        client_id="client",
        client_secret="secret",
        tenant_id="tenant",
        environment_name="Production",
        company_id="company",
        data_dir=tmp_path,
        s3_prefix="raw/dbc",
    )


def test_watermarks_state_path_under_bronze_prefix(tmp_path) -> None:
    settings = _bc_settings(tmp_path)
    assert watermarks_state_path(settings) == tmp_path / "raw" / "dbc" / "_state" / "watermarks.json"


def test_save_and_load_watermarks_local(tmp_path) -> None:
    settings = _bc_settings(tmp_path)
    save_watermarks(settings, {"customers": "2026-01-01T00:00:00Z"})
    assert load_watermarks(settings) == {"customers": "2026-01-01T00:00:00Z"}


def test_load_watermarks_migrates_from_secret_when_store_empty(monkeypatch, tmp_path) -> None:
    settings = _bc_settings(tmp_path)

    monkeypatch.setattr(
        "meshflow.secrets_manager.get_secret_json",
        lambda _secret_id: {"watermarks": {"customers": "2026-02-01T00:00:00Z"}},
    )
    monkeypatch.setattr(
        "meshflow.secrets_manager.resolve_secret_id",
        lambda: "meshflow-poc-dbc-dev",
    )

    loaded = load_watermarks(settings)
    assert loaded == {"customers": "2026-02-01T00:00:00Z"}
    assert load_watermarks(settings) == {"customers": "2026-02-01T00:00:00Z"}
    assert watermarks_state_path(settings).is_file()
