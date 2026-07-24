from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from meshflow.config import QBOSettings
from meshflow.ingest.storage import (
    local_run_dir,
    s3_run_prefix,
    write_json_local,
    write_json_s3,
    write_parquet_local,
    write_parquet_s3,
)
from meshflow.qbo.client import QBOClient
from meshflow.qbo.entities import DEFAULT_ENTITIES, DEFAULT_ENTITY_BUNDLE


def ingest_entity(
    client: QBOClient,
    *,
    entity_name: str,
    query: str,
    settings: QBOSettings,
    run_path: Path | str,
) -> dict[str, Any]:
    rows = client.query(query)
    ingested_at = datetime.now(UTC).isoformat()

    if settings.s3_bucket:
        key = f"{run_path}/{entity_name}.parquet"
        location = write_parquet_s3(settings, key, rows)
    else:
        location = write_parquet_local(Path(run_path), f"{entity_name}.parquet", rows)

    return {
        "entity": entity_name,
        "format": "parquet",
        "query": query,
        "row_count": len(rows),
        "ingested_at": ingested_at,
        "path": location,
    }


def ingest_single(
    client: QBOClient,
    settings: QBOSettings,
    entity_name: str,
    *,
    entities: dict[str, str] | None = None,
) -> dict[str, Any]:
    selected_entities = entities or DEFAULT_ENTITIES
    if entity_name not in selected_entities:
        raise ValueError(
            f"Unknown entity '{entity_name}'. Choose from: {', '.join(sorted(selected_entities))}"
        )

    run_path: Path | str
    if settings.s3_bucket:
        run_path = s3_run_prefix(settings)
    else:
        run_path = local_run_dir(settings, "qbo")

    return ingest_entity(
        client,
        entity_name=entity_name,
        query=selected_entities[entity_name],
        settings=settings,
        run_path=run_path,
    )


def ingest_all(
    client: QBOClient,
    settings: QBOSettings,
    *,
    entities: dict[str, str] | None = None,
    entity_bundle: str | None = None,
) -> dict[str, Any]:
    selected_entities = entities or DEFAULT_ENTITIES
    if settings.s3_bucket:
        run_path = s3_run_prefix(settings)
    else:
        run_path = local_run_dir(settings, "qbo")

    company = client.company_info()
    results = []
    for entity_name, query in selected_entities.items():
        results.append(
            ingest_entity(
                client,
                entity_name=entity_name,
                query=query,
                settings=settings,
                run_path=run_path,
            )
        )

    manifest = {
        "source": "qbo",
        "entity_bundle": entity_bundle or DEFAULT_ENTITY_BUNDLE,
        "realm_id": client.tokens.realm_id,
        "company_name": company.get("CompanyName"),
        "environment": settings.environment,
        "ingested_at": datetime.now(UTC).isoformat(),
        "entities": results,
    }

    if settings.s3_bucket:
        manifest_key = f"{run_path}/manifest.json"
        manifest_path = write_json_s3(settings, manifest_key, manifest)
    else:
        manifest_path = write_json_local(Path(run_path), "manifest.json", manifest)

    manifest["manifest_path"] = manifest_path
    return manifest
