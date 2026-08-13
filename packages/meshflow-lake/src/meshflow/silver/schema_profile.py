"""Build and publish silver schema profiles from consolidated parquet."""

from __future__ import annotations

from datetime import datetime
from meshflow.compat import UTC
from typing import Any

from meshflow.project_config import catalog_table_name
from meshflow.silver.settings import ConsolidateSettings
from meshflow.storage.paths import (
    governance_source_semantic_latest_profile_key,
    prefix_path,
    silver_entity_parquet_key,
    silver_entity_prefix,
)

PROFILE_KIND = "silver_schema_profile"

# entity -> {column: origin} for columns not inferable from API alone
_STATIC_COLUMN_ORIGINS: dict[str, dict[str, dict[str, str]]] = {
    "dbc": {
        "sales_quote_lines": {"header_id": "unpack", "header_number": "unpack"},
        "sales_order_lines": {"header_id": "unpack", "header_number": "unpack"},
        "sales_shipment_lines": {"header_id": "unpack", "header_number": "unpack"},
        "sales_invoice_lines": {"header_id": "unpack", "header_number": "unpack"},
        "sales_credit_memo_lines": {"header_id": "unpack", "header_number": "unpack"},
        "purchase_order_lines": {"header_id": "unpack", "header_number": "unpack"},
        "purchase_receipt_lines": {"header_id": "unpack", "header_number": "unpack"},
        "purchase_invoice_lines": {"header_id": "unpack", "header_number": "unpack"},
        "purchase_credit_memo_lines": {"header_id": "unpack", "header_number": "unpack"},
    },
    "qbd": {
        "invoice_lines": {
            "customer_list_id": "unpack",
            "customer_full_name": "unpack",
        },
    },
}


def _utcnow() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_local_parquet_columns(path) -> list[dict[str, str]]:
    import pyarrow.parquet as pq

    from meshflow.catalog.glue_schema import arrow_field_to_glue_column

    if not path.is_file():
        return []
    schema = pq.read_schema(path)
    return [arrow_field_to_glue_column(field) for field in schema]


def _read_entity_columns(settings: ConsolidateSettings, entity: str) -> list[dict[str, str]]:
    entity_name = entity.strip().lower()
    if settings.s3_bucket:
        from meshflow.catalog.glue_schema import read_parquet_columns

        key = silver_entity_parquet_key(settings.source, entity_name)
        return read_parquet_columns(bucket=settings.s3_bucket, key=key)
    path = prefix_path(
        settings.data_dir,
        silver_entity_prefix(settings.source, entity_name),
        "data.parquet",
    )
    return _read_local_parquet_columns(path)


def _key_derivation_columns(source: str) -> dict[str, dict[str, str]]:
    from meshflow.silver.key_derivation import load_entity_key_configs

    origins: dict[str, dict[str, str]] = {}
    for entity, config in load_entity_key_configs(source).items():
        derivation = config.get("key_derivation") or {}
        output_column = str(derivation.get("output_column") or "_row_key").strip()
        if output_column:
            origins.setdefault(entity, {})[output_column] = "key_derivation"
    return origins


def _column_origin(source: str, entity: str, column_name: str) -> str:
    entity_key = entity.strip().lower()
    column_key = column_name.strip()
    static = _STATIC_COLUMN_ORIGINS.get(source.strip().lower(), {}).get(entity_key, {})
    if column_key in static:
        return static[column_key]
    key_derivation = _key_derivation_columns(source).get(entity_key, {})
    if column_key in key_derivation:
        return key_derivation[column_key]
    return "api"


def _entity_row_count(entity_results: list[dict[str, Any]], entity: str) -> int | None:
    wanted = entity.strip().lower()
    for item in entity_results:
        if not isinstance(item, dict):
            continue
        if str(item.get("entity") or "").strip().lower() == wanted:
            count = item.get("row_count")
            if isinstance(count, int):
                return count
    return None


def build_silver_schema_profile(
    settings: ConsolidateSettings,
    entities: list[str],
    *,
    consolidated_at: str | None = None,
    silver_sql_pack_version: str | None = None,
    entity_results: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Snapshot silver table/column names from parquet after consolidate + silver SQL."""
    source = settings.source.strip().lower()
    tables: list[dict[str, Any]] = []
    for raw_entity in sorted({name.strip().lower() for name in entities if name.strip()}):
        columns_raw = _read_entity_columns(settings, raw_entity)
        if not columns_raw:
            continue
        columns: list[dict[str, str]] = []
        for col in columns_raw:
            name = str(col.get("Name") or "").strip()
            if not name:
                continue
            columns.append(
                {
                    "name": name,
                    "type": str(col.get("Type") or "string").strip() or "string",
                    "origin": _column_origin(source, raw_entity, name),
                }
            )
        if not columns:
            continue
        tables.append(
            {
                "silver_entity": raw_entity,
                "glue_table": catalog_table_name("silver", source, raw_entity),
                "in_silver": True,
                "row_count": _entity_row_count(entity_results or [], raw_entity),
                "columns": columns,
            }
        )

    profile: dict[str, Any] = {
        "source": source,
        "kind": PROFILE_KIND,
        "description": "Silver layer column catalog emitted by consolidate + silver SQL replay.",
        "generated_at": _utcnow(),
        "consolidated_at": consolidated_at or _utcnow(),
        "table_count": len(tables),
        "tables": tables,
    }
    if silver_sql_pack_version:
        profile["silver_sql_pack_version"] = silver_sql_pack_version
    return profile


def write_silver_schema_profile(
    bucket: str,
    source: str,
    profile: dict[str, Any],
) -> str:
    import boto3
    import yaml

    key = governance_source_semantic_latest_profile_key(source)
    body = yaml.safe_dump(profile, sort_keys=False, allow_unicode=True)
    boto3.client("s3").put_object(
        Bucket=bucket,
        Key=key,
        Body=body.encode("utf-8"),
        ContentType="application/yaml",
    )
    return key


def load_silver_schema_profile_from_bytes(payload: bytes) -> dict[str, Any] | None:
    import yaml

    data = yaml.safe_load(payload.decode("utf-8"))
    if not isinstance(data, dict):
        return None
    if str(data.get("kind") or "") != PROFILE_KIND:
        return None
    return data
