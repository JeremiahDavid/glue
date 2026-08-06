from __future__ import annotations

from typing import Any

import httpx

from meshflow.config import load_qbo_settings
from meshflow.project_config import resolve_ingest_connector, resolve_qbo_ingest_entities
from meshflow.qbo.client import QBOClient
from meshflow.qbo.ingest import ingest_all


def handler(event: dict[str, Any] | None, _context: Any) -> dict[str, Any]:
    """Lambda entry point: pull QBO entities and land raw Parquet in S3."""
    settings = load_qbo_settings()
    if not settings.s3_bucket:
        raise ValueError("MESHFLOW_S3_BUCKET must be set for Lambda ingest")

    entity_bundle, entities = resolve_qbo_ingest_entities()
    body = event or {}
    entity = body.get("entity")
    run_id = str(body.get("run_id", "")).strip() or None
    connector = resolve_ingest_connector()
    client = QBOClient.from_saved_tokens(settings)

    if entity:
        from meshflow.qbo.ingest import ingest_single

        if entity not in entities:
            raise ValueError(
                f"Unknown entity {entity!r}. Configured entities: {', '.join(sorted(entities))}"
            )
        try:
            result = ingest_single(
                client,
                settings,
                entity,
                entities=entities,
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

    manifest = ingest_all(client, settings, entities=entities, entity_bundle=entity_bundle)
    return {"status": "ok", "mode": "full", "entity_bundle": entity_bundle, "manifest": manifest}
