from __future__ import annotations

from typing import Any

import httpx

from meshflow.bc.client import BCClient
from meshflow.bc.ingest import ingest_all, ingest_single
from meshflow.config import load_bc_settings
from meshflow.project_config import resolve_bc_ingest_entities, resolve_ingest_connector


def handler(event: dict[str, Any] | None, _context: Any) -> dict[str, Any]:
    """Lambda entry point: pull BC entities and land raw Parquet in S3."""
    settings = load_bc_settings()
    if not settings.s3_bucket:
        raise ValueError("MESHFLOW_S3_BUCKET must be set for Lambda ingest")

    entity_bundle, specs = resolve_bc_ingest_entities()
    body = event or {}
    entity = body.get("entity")
    run_id = str(body.get("run_id", "")).strip() or None
    incremental = not bool(body.get("full_load"))
    connector = resolve_ingest_connector()
    client = BCClient.from_settings(settings)

    if entity:
        if entity not in {spec.output_name for spec in specs}:
            available = ", ".join(sorted(spec.output_name for spec in specs))
            raise ValueError(f"Unknown entity {entity!r}. Configured entities: {available}")
        try:
            result = ingest_single(
                client,
                settings,
                entity,
                specs=specs,
                incremental=incremental,
                run_id=run_id,
            )
        except httpx.HTTPStatusError as exc:
            return {
                "status": "failed",
                "mode": "single",
                "entity": entity,
                "connector": connector,
                "error": str(exc),
                "http_status": exc.response.status_code,
            }
        return {
            "status": "ok",
            "mode": "single",
            "entity": entity,
            "connector": connector,
            "entity_bundle": entity_bundle,
            "result": result,
        }

    manifest = ingest_all(
        client,
        settings,
        specs=specs,
        entity_bundle=entity_bundle,
        incremental=incremental,
    )
    return {"status": "ok", "mode": "full", "entity_bundle": entity_bundle, "manifest": manifest}


def lambda_handler(event: dict[str, Any] | None, context: Any) -> dict[str, Any]:
    return handler(event, context)
