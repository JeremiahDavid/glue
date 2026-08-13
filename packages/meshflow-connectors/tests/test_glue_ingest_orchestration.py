from __future__ import annotations

from meshflow.ingest.glue_runner import resolve_glue_ingest_runtime
from meshflow.ingest.orchestration_handlers import finalize_handler


def test_resolve_glue_ingest_runtime_uses_explicit_args() -> None:
    run_id, full_load = resolve_glue_ingest_runtime(
        {"run_id": "20260730T120000Z", "full_load": "true"}
    )
    assert run_id == "20260730T120000Z"
    assert full_load is True


def test_resolve_glue_ingest_runtime_generates_run_id_when_missing() -> None:
    run_id, full_load = resolve_glue_ingest_runtime({})
    assert len(run_id) == 16
    assert full_load is False


def test_finalize_handler_reads_manifest(monkeypatch) -> None:
    manifest = {
        "source": "dbc",
        "run_id": "20260730T120000Z",
        "entities": [{"entity": "customers", "row_count": 3}],
        "ingest_summary": {"succeeded": 1, "failed": 0, "total": 1},
        "manifest_path": "s3://bucket/raw/dbc/20260730T120000Z/manifest.json",
    }
    monkeypatch.setenv("MESHFLOW_SOURCE", "dbc")
    monkeypatch.setattr(
        "meshflow.ingest.orchestration_handlers.finalize_ingest_from_manifest",
        lambda **kwargs: manifest,
    )

    result = finalize_handler(
        {
            "run_id": "20260730T120000Z",
            "full_load": False,
            "full_rebuild": False,
        },
        None,
    )
    assert result["status"] == "ok"
    assert result["manifest"] == manifest
