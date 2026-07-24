from __future__ import annotations

import io
import logging
from typing import Any

from meshflow.project_config import catalog_table_name, glue_database_name
from meshflow.silver.settings import ConsolidateSettings
from meshflow.storage.paths import silver_source_prefix

logger = logging.getLogger(__name__)


def arrow_field_to_glue_column(field: Any) -> dict[str, str]:
    import pyarrow as pa

    field_type = field.type
    if pa.types.is_string(field_type) or pa.types.is_large_string(field_type):
        hive_type = "string"
    elif pa.types.is_int8(field_type) or pa.types.is_int16(field_type) or pa.types.is_int32(field_type):
        hive_type = "int"
    elif pa.types.is_int64(field_type):
        hive_type = "bigint"
    elif pa.types.is_float32(field_type) or pa.types.is_float64(field_type):
        hive_type = "double"
    elif pa.types.is_boolean(field_type):
        hive_type = "boolean"
    elif pa.types.is_timestamp(field_type):
        hive_type = "timestamp"
    elif pa.types.is_date(field_type):
        hive_type = "date"
    elif pa.types.is_decimal(field_type):
        hive_type = f"decimal({field_type.precision},{field_type.scale})"
    else:
        hive_type = "string"

    return {"Name": str(field.name), "Type": hive_type}


def read_parquet_columns(*, bucket: str, key: str) -> list[dict[str, str]]:
    import boto3
    import pyarrow.parquet as pq

    response = boto3.client("s3").get_object(Bucket=bucket, Key=key)
    schema = pq.read_schema(io.BytesIO(response["Body"].read()))
    return [arrow_field_to_glue_column(field) for field in schema]


def update_glue_table_columns(
    *,
    database_name: str,
    table_name: str,
    columns: list[dict[str, str]],
    region: str | None = None,
) -> None:
    import boto3

    client = boto3.client("glue", region_name=region)
    current = client.get_table(DatabaseName=database_name, Name=table_name)["Table"]
    storage_descriptor = dict(current["StorageDescriptor"])
    storage_descriptor["Columns"] = columns

    table_input = {
        "Name": current["Name"],
        "StorageDescriptor": storage_descriptor,
        "PartitionKeys": current.get("PartitionKeys", []),
        "TableType": current.get("TableType", "EXTERNAL_TABLE"),
        "Parameters": current.get("Parameters", {}),
    }
    client.update_table(DatabaseName=database_name, TableInput=table_input)


def sync_silver_table_schema(
    settings: ConsolidateSettings,
    entity_name: str,
    *,
    company: str | None = None,
    environment: str | None = None,
    region: str | None = None,
) -> list[dict[str, str]]:
    if not settings.s3_bucket:
        return []

    database_name = glue_database_name(company, environment)
    table_name = catalog_table_name("silver", settings.source, entity_name)
    key = f"{silver_source_prefix(settings.source)}/{entity_name}.parquet"
    columns = read_parquet_columns(bucket=settings.s3_bucket, key=key)
    if not columns:
        logger.warning("No columns found in %s for Glue table %s", key, table_name)
        return []

    update_glue_table_columns(
        database_name=database_name,
        table_name=table_name,
        columns=columns,
        region=region,
    )
    logger.info("Updated Glue schema for %s.%s (%s columns)", database_name, table_name, len(columns))
    return columns


def sync_raw_table_schema(
    settings: ConsolidateSettings,
    entity_name: str,
    *,
    run_id: str,
    company: str | None = None,
    environment: str | None = None,
    region: str | None = None,
) -> list[dict[str, str]]:
    if not settings.s3_bucket:
        return []

    from meshflow.storage.paths import raw_source_prefix

    database_name = glue_database_name(company, environment)
    table_name = catalog_table_name("raw", settings.source, entity_name)
    key = f"{raw_source_prefix(settings.source)}/{run_id}/{entity_name}.parquet"
    columns = read_parquet_columns(bucket=settings.s3_bucket, key=key)
    if not columns:
        return []

    update_glue_table_columns(
        database_name=database_name,
        table_name=table_name,
        columns=columns,
        region=region,
    )
    logger.info("Updated Glue schema for %s.%s (%s columns)", database_name, table_name, len(columns))
    return columns
