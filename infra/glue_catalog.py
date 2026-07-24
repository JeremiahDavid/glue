from __future__ import annotations

from typing import Any

from meshflow.project_config import catalog_table_name
from meshflow.storage.paths import raw_source_prefix, silver_source_prefix

PARQUET_INPUT_FORMAT = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
PARQUET_OUTPUT_FORMAT = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"
PARQUET_SERDE = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
RUN_ID_PROJECTION_REGEX = r"\d{8}T\d{6}Z"


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


def silver_table_props(
    *,
    bucket_name: str,
    source: str,
    entity: str,
) -> dict[str, Any]:
    prefix = silver_source_prefix(source)
    table_name = catalog_table_name("silver", source, entity)
    return {
        "name": table_name,
        "table_type": "EXTERNAL_TABLE",
        "parameters": {
            "classification": "parquet",
            "EXTERNAL": "TRUE",
        },
        "storage_descriptor": _parquet_storage_descriptor(
            location=f"s3://{bucket_name}/{prefix}/{entity}.parquet",
        ),
    }


def raw_table_props(
    *,
    bucket_name: str,
    source: str,
    entity: str,
) -> dict[str, Any]:
    prefix = raw_source_prefix(source)
    table_name = catalog_table_name("raw", source, entity)
    return {
        "name": table_name,
        "table_type": "EXTERNAL_TABLE",
        "partition_keys": [{"name": "run_id", "type": "string"}],
        "parameters": {
            "classification": "parquet",
            "EXTERNAL": "TRUE",
            "projection.enabled": "true",
            "projection.run_id.type": "regex",
            "projection.run_id.regex": RUN_ID_PROJECTION_REGEX,
            "storage.location.template": (
                f"s3://{bucket_name}/{prefix}/${{run_id}}/{entity}.parquet"
            ),
        },
        "storage_descriptor": _parquet_storage_descriptor(
            location=f"s3://{bucket_name}/{prefix}/",
        ),
    }


def sample_validation_queries(database_name: str, entities: list[tuple[str, str]]) -> list[str]:
    queries: list[str] = []
    for source, entity in entities:
        silver_table = catalog_table_name("silver", source, entity)
        raw_table = catalog_table_name("raw", source, entity)
        queries.append(
            f"SELECT COUNT(*) AS row_count FROM {database_name}.{silver_table};"
        )
        queries.append(
            "SELECT run_id, COUNT(*) AS row_count "
            f"FROM {database_name}.{raw_table} "
            "GROUP BY run_id ORDER BY run_id DESC LIMIT 10;"
        )
    return queries
