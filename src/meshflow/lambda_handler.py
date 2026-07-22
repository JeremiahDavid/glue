from __future__ import annotations

from typing import Any

from meshflow.config import load_qbo_settings
from meshflow.project_config import resolve_qbo_ingest_entities
from meshflow.qbo.client import QBOClient
from meshflow.qbo.ingest import ingest_all


def handler(event: dict[str, Any] | None, _context: Any) -> dict[str, Any]:
    """Lambda entry point: pull QBO entities and land raw Parquet in S3."""
    settings = load_qbo_settings()
    if not settings.s3_bucket:
        raise ValueError("MESHFLOW_S3_BUCKET must be set for Lambda ingest")

    entity_bundle, entities = resolve_qbo_ingest_entities()
    entity = (event or {}).get("entity")
    client = QBOClient.from_saved_tokens(settings)

    if entity:
        from meshflow.qbo.ingest import ingest_single

        if entity not in entities:
            raise ValueError(
                f"Unknown entity {entity!r}. Configured entities: {', '.join(sorted(entities))}"
            )
        result = ingest_single(client, settings, entity, entities=entities)
        return {"status": "ok", "mode": "single", "entity_bundle": entity_bundle, "result": result}

    manifest = ingest_all(client, settings, entities=entities, entity_bundle=entity_bundle)
    return {"status": "ok", "mode": "full", "entity_bundle": entity_bundle, "manifest": manifest}


def lambda_handler(event: dict[str, Any] | None, context: Any) -> dict[str, Any]:
    """AWS Lambda-compatible alias."""
    return handler(event, context)
