from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from meshflow.config import QBOSettings
from meshflow.ingest.storage import (
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
        key = f"{run_path}/{entity_name}/data.parquet"
        location = write_parquet_s3(settings, key, rows)
    else:
        location = write_parquet_local(Path(run_path) / entity_name, "data.parquet", rows)

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
    run_id: str | None = None,
) -> dict[str, Any]:
    selected_entities = entities or DEFAULT_ENTITIES
    if entity_name not in selected_entities:
        raise ValueError(
            f"Unknown entity '{entity_name}'. Choose from: {', '.join(sorted(selected_entities))}"
        )

    from meshflow.ingest.storage import resolve_run_path

    run_path = resolve_run_path(settings, run_id)

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
    from meshflow.ingest.storage import resolve_run_path

    run_path = resolve_run_path(settings)

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

    if settings.s3_bucket:
        from meshflow.project_config import resolve_ingest_s3_prefix, resolve_selection
        from meshflow.catalog.glue_schema import sync_raw_tables_for_entities
        from meshflow.silver.settings import ConsolidateSettings

        company, meshflow_environment = resolve_selection()
        entity_names = [str(item.get("entity", "")).strip() for item in results]
        entity_names = [name for name in entity_names if name]
        catalog_settings = ConsolidateSettings(
            source="qbo",
            data_dir=settings.data_dir,
            s3_bucket=settings.s3_bucket,
            raw_prefix=resolve_ingest_s3_prefix(
                company,
                meshflow_environment,
                source="qbo",
            ),
        )
        manifest["glue_catalog"] = {
            "raw": sync_raw_tables_for_entities(catalog_settings, entity_names)
        }

    return manifest
