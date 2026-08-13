from __future__ import annotations

from typing import Any

from meshflow.ingest.orchestration import (
    finalize_ingest_from_manifest,
    finalize_ingest_run,
    prepare_ingest_run,
)


def prepare_handler(event: dict[str, Any] | None, _context: Any) -> dict[str, Any]:
    """Step Functions entry: resolve entity list and shared run_id."""
    body = event or {}
    full_load = bool(body.get("full_load"))
    payload = prepare_ingest_run(full_load=full_load)
    result: dict[str, Any] = {"status": "ok", **payload}
    if "full_rebuild" in body:
        result["full_rebuild"] = bool(body.get("full_rebuild"))
    return result


def finalize_handler(event: dict[str, Any] | None, _context: Any) -> dict[str, Any]:
    """Step Functions entry: confirm bronze manifest after Glue ingest completes."""
    body = event or {}
    run_id = str(body.get("run_id", "")).strip()
    if not run_id:
        raise ValueError("run_id is required for ingest finalize")

    entity_results = body.get("entity_results", [])
    if entity_results and isinstance(entity_results, list):
        manifest = finalize_ingest_run(
            run_id=run_id,
            entity_results=entity_results,
            full_load=bool(body.get("full_load")),
        )
    else:
        manifest = finalize_ingest_from_manifest(run_id=run_id)
    from meshflow.project_config import resolve_ingest_connector

    connector = resolve_ingest_connector()
    result: dict[str, Any] = {
        "status": "ok",
        "connector": connector,
        "run_id": run_id,
        "manifest": manifest,
    }
    if "full_rebuild" in body:
        result["full_rebuild"] = bool(body.get("full_rebuild"))
    return result
