from __future__ import annotations

from typing import Any

from hiveflow.project_config import catalog_table_name
from hiveflow.storage.paths import raw_source_prefix, silver_entity_prefix, silver_stg_entity_prefix

PARQUET_INPUT_FORMAT = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
PARQUET_OUTPUT_FORMAT = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"
PARQUET_SERDE = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
RAW_PROJECTION_PLACEHOLDER = "__bootstrap__"


def _parquet_storage_descriptor(*, location: str) -> dict[str, Any]:
    return {
        "columns": [],
        "location": location,
        "input_format": PARQUET_INPUT_FORMAT,
        "output_format": PARQUET_OUTPUT_FORMAT,
        "serde_info": {
            "serialization_library": PARQUET_SERDE,
        },
        "compressed": True,
    }


def raw_table_parameters(
    *,
    bucket_name: str,
    source: str,
    entity: str,
    run_ids: list[str],
) -> dict[str, str]:
    prefix = raw_source_prefix(source)
    values = ",".join(run_ids) if run_ids else RAW_PROJECTION_PLACEHOLDER
    return {
        "classification": "parquet",
        "EXTERNAL": "TRUE",
        "projection.enabled": "true",
        "projection.run_id.type": "enum",
        "projection.run_id.values": values,
        "storage.location.template": f"s3://{bucket_name}/{prefix}/${{run_id}}/{entity}/",
    }


def raw_table_props(
    *,
    bucket_name: str,
    source: str,
    entity: str,
    run_ids: list[str] | None = None,
) -> dict[str, Any]:
    prefix = raw_source_prefix(source)
    table_name = catalog_table_name("raw", source, entity)
    return {
        "name": table_name,
        "table_type": "EXTERNAL_TABLE",
        "partition_keys": [{"name": "run_id", "type": "string"}],
        "parameters": raw_table_parameters(
            bucket_name=bucket_name,
            source=source,
            entity=entity,
            run_ids=run_ids or [RAW_PROJECTION_PLACEHOLDER],
        ),
        "storage_descriptor": _parquet_storage_descriptor(
            location=f"s3://{bucket_name}/{prefix}/",
        ),
    }


def silver_stg_table_props(
    *,
    bucket_name: str,
    source: str,
    entity: str,
) -> dict[str, Any]:
    table_name = catalog_table_name("silver_stg", source, entity)
    return {
        "name": table_name,
        "table_type": "EXTERNAL_TABLE",
        "parameters": {
            "classification": "parquet",
            "EXTERNAL": "TRUE",
        },
        "storage_descriptor": _parquet_storage_descriptor(
            location=f"s3://{bucket_name}/{silver_stg_entity_prefix(source, entity)}/",
        ),
    }


def silver_table_props(
    *,
    bucket_name: str,
    source: str,
    entity: str,
) -> dict[str, Any]:
    table_name = catalog_table_name("silver", source, entity)
    return {
        "name": table_name,
        "table_type": "EXTERNAL_TABLE",
        "parameters": {
            "classification": "parquet",
            "EXTERNAL": "TRUE",
        },
        "storage_descriptor": _parquet_storage_descriptor(
            location=f"s3://{bucket_name}/{silver_entity_prefix(source, entity)}/",
        ),
    }


def sample_validation_queries(database_name: str, entities: list[tuple[str, str]]) -> list[str]:
    from hiveflow.project_config import is_silver_only_catalog_entity

    queries: list[str] = []
    for source, entity in entities:
        silver_stg_table = catalog_table_name("silver_stg", source, entity)
        queries.append(
            f"SELECT COUNT(*) AS row_count FROM {database_name}.{silver_stg_table};"
        )
        silver_table = catalog_table_name("silver", source, entity)
        queries.append(
            f"SELECT COUNT(*) AS row_count FROM {database_name}.{silver_table};"
        )
        if is_silver_only_catalog_entity(source, entity):
            continue
        raw_table = catalog_table_name("raw", source, entity)
        queries.append(
            "SELECT run_id, COUNT(*) AS row_count "
            f"FROM {database_name}.{raw_table} "
            "GROUP BY run_id ORDER BY run_id DESC LIMIT 10;"
        )
    return queries
