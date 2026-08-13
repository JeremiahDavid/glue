from __future__ import annotations

from meshflow.ingest.orchestration_handlers import finalize_handler


def test_finalize_handler_reads_manifest_when_entity_results_missing(monkeypatch) -> None:
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


def test_finalize_handler_uses_entity_results_when_present(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_finalize(**kwargs):  # type: ignore[no-untyped-def]
        captured.update(kwargs)
        return {"source": "dbc", "entities": kwargs["entity_results"]}

    monkeypatch.setenv("MESHFLOW_SOURCE", "dbc")
    monkeypatch.setattr("meshflow.ingest.orchestration_handlers.finalize_ingest_run", fake_finalize)

    entity_results = [{"Payload": {"status": "ok", "result": {"entity": "customers"}}}]
    finalize_handler(
        {
            "run_id": "20260730T120000Z",
            "entity_results": entity_results,
            "full_load": False,
        },
        None,
    )
    assert captured["entity_results"] == entity_results
