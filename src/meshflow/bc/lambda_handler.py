from __future__ import annotations

from typing import Any

from meshflow.bc.client import BCClient
from meshflow.bc.ingest import ingest_all, ingest_single
from meshflow.config import load_bc_settings
from meshflow.project_config import resolve_bc_ingest_entities


def handler(event: dict[str, Any] | None, _context: Any) -> dict[str, Any]:
    """Lambda entry point: pull BC entities and land raw Parquet in S3."""
    settings = load_bc_settings()
    if not settings.s3_bucket:
        raise ValueError("MESHFLOW_S3_BUCKET must be set for Lambda ingest")

    entity_bundle, specs = resolve_bc_ingest_entities()
    entity = (event or {}).get("entity")
    incremental = not bool((event or {}).get("full_load"))
    client = BCClient.from_settings(settings)

    if entity:
        if entity not in {spec.output_name for spec in specs}:
            available = ", ".join(sorted(spec.output_name for spec in specs))
            raise ValueError(f"Unknown entity {entity!r}. Configured entities: {available}")
        result = ingest_single(
            client,
            settings,
            entity,
            specs=specs,
            incremental=incremental,
        )
        return {"status": "ok", "mode": "single", "entity_bundle": entity_bundle, "result": result}

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
