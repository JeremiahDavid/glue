from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from meshflow.silver.key_derivation import apply_key_derivation_to_row, entity_key_config
from meshflow.silver.keys import row_merge_key
from meshflow.silver.settings import ConsolidateSettings
from meshflow.silver.store import (
    list_bronze_runs,
    read_consolidated_entity,
    read_consolidation_state,
    read_entity_rows,
    read_run_manifest,
    write_consolidated_entity,
    write_consolidated_manifest,
    write_consolidation_state,
)

logger = logging.getLogger(__name__)


def upsert_rows(
    existing: dict[str, dict[str, Any]],
    new_rows: list[dict[str, Any]],
    entity_name: str,
    *,
    source: str | None = None,
) -> int:
    applied = 0
    for row in new_rows:
        merge_key = row_merge_key(row, entity_name, source=source)
        if merge_key is None:
            continue
        existing[merge_key] = row
        applied += 1
    return applied


def consolidate_source(
    settings: ConsolidateSettings,
    *,
    full_rebuild: bool = False,
) -> dict[str, Any]:
    """Merge append-only bronze runs into one parquet table per entity."""
    bronze_runs = list_bronze_runs(settings)
    if full_rebuild:
        state = {"processed_runs": []}
        entity_tables: dict[str, dict[str, dict[str, Any]]] = {}
    else:
        state = read_consolidation_state(settings)
        processed = set(state.get("processed_runs", []))
        entity_tables = _load_existing_tables(settings, bronze_runs, processed)

    processed_runs = list(state.get("processed_runs", []))
    processed_set = set(processed_runs)
    pending_runs = [run_id for run_id in bronze_runs if run_id not in processed_set]

    entity_bundle: str | None = None
    source_metadata: dict[str, Any] = {}
    run_stats: list[dict[str, Any]] = []

    for run_id in pending_runs:
        manifest = read_run_manifest(settings, run_id)
        if manifest is None:
            logger.warning("Skipping run %s with no manifest.json", run_id)
            processed_runs.append(run_id)
            continue

        entity_bundle = str(manifest.get("entity_bundle") or entity_bundle or "")
        source_metadata.update(
            {
                key: manifest[key]
                for key in ("company_name", "company_file", "realm_id", "environment")
                if manifest.get(key) not in (None, "")
            }
        )

        run_applied = 0
        for entity_info in manifest.get("entities", []):
            if not isinstance(entity_info, dict):
                continue
            entity_name = str(entity_info.get("entity", "")).strip()
            if not entity_name:
                continue
            rows = read_entity_rows(settings, run_id, entity_name)
            key_config = entity_key_config(settings.source, entity_name)
            if key_config:
                rows = [apply_key_derivation_to_row(row, key_config) for row in rows]
            table = entity_tables.setdefault(entity_name, {})
            run_applied += upsert_rows(table, rows, entity_name, source=settings.source)

        run_stats.append({"run_id": run_id, "rows_applied": run_applied})
        processed_runs.append(run_id)
        logger.info("Consolidated bronze run %s (%s row upserts)", run_id, run_applied)

    entity_results: list[dict[str, Any]] = []
    for entity_name in sorted(entity_tables):
        rows = list(entity_tables[entity_name].values())
        entity_results.extend(_write_silver_entity(settings, entity_name, rows))

    consolidated_at = datetime.now(UTC).isoformat()
    manifest = {
        "layer": "silver",
        "source": settings.source,
        "entity_bundle": entity_bundle,
        "consolidated_at": consolidated_at,
        "bronze_run_count": len(bronze_runs),
        "processed_run_count": len(processed_runs),
        "runs_applied_this_execution": run_stats,
        "entities": entity_results,
        **source_metadata,
    }
    manifest_path = write_consolidated_manifest(settings, manifest)
    manifest["manifest_path"] = manifest_path
    manifest["silver_prefix"] = settings.silver_prefix

    if settings.s3_bucket:
        from meshflow.catalog.glue_schema import sync_source_catalog

        manifest["glue_catalog"] = sync_source_catalog(settings)

    write_consolidation_state(
        settings,
        {
            "processed_runs": processed_runs,
            "updated_at": consolidated_at,
            "source": settings.source,
        },
    )
    return manifest


def _write_silver_entity(
    settings: ConsolidateSettings,
    entity_name: str,
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    from meshflow.silver.key_derivation import apply_key_derivation_to_rows, entity_key_config

    key_config = entity_key_config(settings.source, entity_name)
    if key_config:
        rows = apply_key_derivation_to_rows(rows, key_config)

    if settings.source == "qbd" and entity_name == "invoices":
        from meshflow.silver.unpack.qbd_invoices import unpack_qbd_invoices

        headers, lines = unpack_qbd_invoices(rows)
        results = [
            {
                "entity": "invoices",
                "format": "parquet",
                "row_count": len(headers),
                "path": write_consolidated_entity(settings, "invoices", headers),
                "unpack": "header",
            },
            {
                "entity": "invoice_lines",
                "format": "parquet",
                "row_count": len(lines),
                "path": write_consolidated_entity(settings, "invoice_lines", lines),
                "unpack": "lines",
            },
        ]
        logger.info(
            "Unpacked QBD invoices into %s headers and %s line rows",
            len(headers),
            len(lines),
        )
        return results

    if settings.source == "dbc":
        from meshflow.silver.unpack.dbc_documents import (
            DBC_DOCUMENT_ENTITIES,
            unpack_dbc_document_entity,
        )

        if entity_name in DBC_DOCUMENT_ENTITIES:
            headers, lines, line_entity = unpack_dbc_document_entity(entity_name, rows)
            results = [
                {
                    "entity": entity_name,
                    "format": "parquet",
                    "row_count": len(headers),
                    "path": write_consolidated_entity(settings, entity_name, headers),
                    "unpack": "header",
                },
                {
                    "entity": line_entity,
                    "format": "parquet",
                    "row_count": len(lines),
                    "path": write_consolidated_entity(settings, line_entity, lines),
                    "unpack": "lines",
                },
            ]
            logger.info(
                "Unpacked DBC %s into %s headers and %s %s rows",
                entity_name,
                len(headers),
                len(lines),
                line_entity,
            )
            return results

    return [
        {
            "entity": entity_name,
            "format": "parquet",
            "row_count": len(rows),
            "path": write_consolidated_entity(settings, entity_name, rows),
        }
    ]


def _load_existing_tables(
    settings: ConsolidateSettings,
    bronze_runs: list[str],
    processed_runs: set[str],
) -> dict[str, dict[str, dict[str, Any]]]:
    entity_names: set[str] = set()
    for run_id in processed_runs:
        if run_id not in bronze_runs:
            continue
        manifest = read_run_manifest(settings, run_id)
        if manifest is None:
            continue
        for entity_info in manifest.get("entities", []):
            if isinstance(entity_info, dict) and entity_info.get("entity"):
                entity_names.add(str(entity_info["entity"]))

    tables: dict[str, dict[str, dict[str, Any]]] = {}
    for entity_name in entity_names:
        rows = read_consolidated_entity(settings, entity_name)
        table: dict[str, dict[str, Any]] = {}
        upsert_rows(table, rows, entity_name, source=settings.source)
        tables[entity_name] = table
    return tables
