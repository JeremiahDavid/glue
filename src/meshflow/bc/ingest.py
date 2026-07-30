from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from meshflow.bc.client import BCClient
from meshflow.bc.entities import BCEntitySpec, DEFAULT_ENTITY_BUNDLE
from meshflow.bc.token_store import load_watermarks, save_watermarks
from meshflow.config import BCSettings
from meshflow.ingest.storage import (
    write_json_local,
    write_json_s3,
    write_parquet_local,
    write_parquet_s3,
)


def _connector_source(settings: BCSettings) -> str:
    prefix = settings.s3_prefix.strip("/")
    if prefix.startswith("raw/"):
        slug = prefix.removeprefix("raw/").split("/", 1)[0]
        return slug or "dbc"
    return prefix or "dbc"


def _max_modified(rows: list[dict[str, Any]], field: str | None) -> str | None:
    if not field:
        return None
    values = [str(row.get(field, "")).strip() for row in rows if row.get(field) not in (None, "")]
    return max(values) if values else None


def _write_entity_rows(
    settings: BCSettings,
    *,
    entity_name: str,
    rows: list[dict[str, Any]],
    run_path: Path | str,
) -> str:
    if settings.s3_bucket:
        key = f"{run_path}/{entity_name}/data.parquet"
        return write_parquet_s3(settings, key, rows)
    return write_parquet_local(Path(run_path) / entity_name, "data.parquet", rows)


def ingest_entity(
    client: BCClient,
    settings: BCSettings,
    spec: BCEntitySpec,
    *,
    run_path: Path | str,
    watermark: str | None = None,
) -> dict[str, Any]:
    rows = client.list_entity_rows(spec, watermark=watermark)
    ingested_at = datetime.now(UTC).isoformat()
    location = _write_entity_rows(settings, entity_name=spec.output_name, rows=rows, run_path=run_path)
    return {
        "entity": spec.output_name,
        "format": "parquet",
        "resource": spec.resource,
        "row_count": len(rows),
        "ingested_at": ingested_at,
        "path": location,
        "watermark_from": watermark,
        "watermark_to": _max_modified(rows, spec.incremental_field),
        "incremental_field": spec.incremental_field,
    }


def ingest_all(
    client: BCClient,
    settings: BCSettings,
    *,
    specs: list[BCEntitySpec] | None = None,
    entity_bundle: str | None = None,
    incremental: bool = True,
) -> dict[str, Any]:
    selected_specs = specs or []
    if not selected_specs:
        raise ValueError("At least one BC entity spec is required")

    from meshflow.ingest.storage import resolve_run_path

    run_path = resolve_run_path(settings)

    watermarks = load_watermarks(settings) if incremental else {}
    updated_watermarks = dict(watermarks)
    results: list[dict[str, Any]] = []

    for spec in selected_specs:
        entity_incremental = incremental and spec.incremental_field is not None
        watermark = watermarks.get(spec.output_name) if entity_incremental else None
        try:
            result = ingest_entity(
                client,
                settings,
                spec,
                run_path=run_path,
                watermark=watermark,
            )
        except httpx.HTTPStatusError as exc:
            result = {
                "entity": spec.output_name,
                "resource": spec.resource,
                "status": "failed",
                "error": str(exc),
                "http_status": exc.response.status_code,
            }
        results.append(result)
        if entity_incremental and result.get("watermark_to"):
            updated_watermarks[spec.output_name] = str(result["watermark_to"])

    company = client.company()
    source = _connector_source(settings)
    manifest = {
        "source": source,
        "entity_bundle": entity_bundle or DEFAULT_ENTITY_BUNDLE,
        "company_id": settings.company_id,
        "company_name": company.get("displayName") or company.get("name"),
        "bc_environment": settings.environment_name,
        "environment": settings.environment,
        "ingested_at": datetime.now(UTC).isoformat(),
        "entities": results,
        "ingest_summary": {
            "succeeded": sum(1 for item in results if item.get("status") != "failed"),
            "failed": sum(1 for item in results if item.get("status") == "failed"),
            "total": len(results),
        },
    }

    if settings.s3_bucket:
        manifest_key = f"{run_path}/manifest.json"
        manifest_path = write_json_s3(settings, manifest_key, manifest)
    else:
        manifest_path = write_json_local(Path(run_path), "manifest.json", manifest)

    manifest["manifest_path"] = manifest_path

    if incremental and updated_watermarks != watermarks:
        save_watermarks(settings, updated_watermarks)

    if settings.s3_bucket:
        from meshflow.project_config import resolve_ingest_s3_prefix, resolve_selection
        from meshflow.catalog.glue_schema import sync_raw_tables_for_entities
        from meshflow.silver.settings import ConsolidateSettings

        company_name, meshflow_environment = resolve_selection()
        entity_names = [
            str(item.get("entity", "")).strip()
            for item in results
            if item.get("entity") and item.get("status") != "failed"
        ]
        catalog_settings = ConsolidateSettings(
            source=source,
            data_dir=settings.data_dir,
            s3_bucket=settings.s3_bucket,
            raw_prefix=resolve_ingest_s3_prefix(
                company_name,
                meshflow_environment,
                source=source,
            ),
        )
        manifest["glue_catalog"] = {
            "raw": sync_raw_tables_for_entities(catalog_settings, entity_names)
        }

    return manifest


def ingest_single(
    client: BCClient,
    settings: BCSettings,
    entity_name: str,
    *,
    specs: list[BCEntitySpec],
    incremental: bool = True,
    run_id: str | None = None,
) -> dict[str, Any]:
    selected = next((spec for spec in specs if spec.output_name == entity_name), None)
    if selected is None:
        available = ", ".join(sorted(spec.output_name for spec in specs))
        raise ValueError(f"Unknown entity {entity_name!r}. Available: {available}")

    from meshflow.ingest.storage import resolve_run_path

    run_path = resolve_run_path(settings, run_id)

    watermark = load_watermarks(settings).get(entity_name) if incremental else None
    return ingest_entity(
        client,
        settings,
        selected,
        run_path=run_path,
        watermark=watermark,
    )
