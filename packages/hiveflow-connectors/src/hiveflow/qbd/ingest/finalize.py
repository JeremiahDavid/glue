from __future__ import annotations

from datetime import datetime
from meshflow.compat import UTC
from typing import Any

from meshflow.config import QBDSettings
from meshflow.ingest.storage import (
    local_run_dir,
    s3_run_prefix,
    write_json_local,
    write_json_s3,
    write_parquet_local,
    write_parquet_s3,
)
from meshflow.qbd.entities import output_specs
from meshflow.qbd.models import SyncRun
from meshflow.qbd.qbxml.parsers import is_open_invoice


def _rows_for_output(
    spec_output_name: str,
    *,
    derived_from: str | None,
    accumulated_records: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    if derived_from:
        source_rows = accumulated_records.get(derived_from, [])
        if spec_output_name == "open_invoices":
            return [row for row in source_rows if is_open_invoice(row)]
        return list(source_rows)
    return list(accumulated_records.get(spec_output_name, []))


def finalize_sync_run(
    settings: QBDSettings,
    sync_run: SyncRun,
    accumulated_records: dict[str, list[dict[str, Any]]],
    *,
    company_name: str | None = None,
    company_file: str | None = None,
) -> dict[str, Any]:
    run_path = s3_run_prefix(settings) if settings.s3_bucket else local_run_dir(settings)
    entity_results: list[dict[str, Any]] = []

    for spec in output_specs(sync_run.entity_bundle):
        rows = _rows_for_output(
            spec.output_name,
            derived_from=spec.derived_from,
            accumulated_records=accumulated_records,
        )
        ingested_at = datetime.now(UTC).isoformat()
        if settings.s3_bucket:
            key = f"{run_path}/{spec.output_name}/data.parquet"
            location = write_parquet_s3(settings, key, rows)
        else:
            location = write_parquet_local(run_path / spec.output_name, "data.parquet", rows)

        entity_results.append(
            {
                "entity": spec.output_name,
                "format": "parquet",
                "entity_type": spec.entity_type.value,
                "derived_from": spec.derived_from,
                "row_count": len(rows),
                "ingested_at": ingested_at,
                "path": location,
            }
        )

    manifest = {
        "source": "qbd",
        "entity_bundle": sync_run.entity_bundle,
        "sync_run_id": str(sync_run.id),
        "company_name": company_name,
        "company_file": company_file,
        "environment": settings.environment,
        "ingested_at": datetime.now(UTC).isoformat(),
        "entities": entity_results,
    }

    if settings.s3_bucket:
        manifest_key = f"{run_path}/manifest.json"
        manifest_path = write_json_s3(settings, manifest_key, manifest)
    else:
        manifest_path = write_json_local(run_path, "manifest.json", manifest)

    manifest["manifest_path"] = manifest_path
    manifest["run_path"] = str(run_path)

    if settings.s3_bucket:
        from meshflow.project_config import resolve_ingest_s3_prefix, resolve_selection
        from meshflow.catalog.glue_schema import sync_raw_tables_for_entities
        from meshflow.silver.settings import ConsolidateSettings

        company, meshflow_environment = resolve_selection()
        entity_names = [str(item.get("entity", "")).strip() for item in entity_results]
        entity_names = [name for name in entity_names if name]
        catalog_settings = ConsolidateSettings(
            source="qbd",
            data_dir=settings.data_dir,
            s3_bucket=settings.s3_bucket,
            raw_prefix=resolve_ingest_s3_prefix(
                company,
                meshflow_environment,
                source="qbd",
            ),
        )
        manifest["glue_catalog"] = {
            "raw": sync_raw_tables_for_entities(catalog_settings, entity_names)
        }

    return manifest
