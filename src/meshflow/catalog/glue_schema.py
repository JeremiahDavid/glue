from __future__ import annotations

import io
import logging
from typing import Any

from meshflow.project_config import catalog_table_name, glue_database_name, is_silver_only_catalog_entity
from meshflow.silver.settings import ConsolidateSettings
from meshflow.storage.paths import (
    legacy_raw_entity_parquet_key,
    legacy_silver_entity_parquet_key,
    raw_entity_parquet_key,
    raw_source_prefix,
    silver_entity_parquet_key,
    silver_entity_prefix,
)

logger = logging.getLogger(__name__)

PARQUET_INPUT_FORMAT = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
PARQUET_OUTPUT_FORMAT = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"
PARQUET_SERDE = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"


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

    payload = boto3.client("s3").get_object(Bucket=bucket, Key=key)["Body"].read()
    buffer = io.BytesIO(payload)
    schema = pq.read_schema(buffer)
    columns = [arrow_field_to_glue_column(field) for field in schema]
    if columns:
        return columns

    table = pq.read_table(buffer)
    return [arrow_field_to_glue_column(field) for field in table.schema]


def _parquet_storage_descriptor(*, bucket: str, source: str, entity: str, columns: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "Columns": columns,
        "Location": f"s3://{bucket}/{silver_entity_prefix(source, entity)}/",
        "InputFormat": PARQUET_INPUT_FORMAT,
        "OutputFormat": PARQUET_OUTPUT_FORMAT,
        "SerdeInfo": {
            "SerializationLibrary": PARQUET_SERDE,
        },
        "Compressed": True,
    }


def _silver_table_input(
    *,
    table_name: str,
    bucket: str,
    source: str,
    entity: str,
    columns: list[dict[str, str]],
) -> dict[str, Any]:
    return {
        "Name": table_name,
        "TableType": "EXTERNAL_TABLE",
        "Parameters": {
            "classification": "parquet",
            "EXTERNAL": "TRUE",
        },
        "StorageDescriptor": _parquet_storage_descriptor(
            bucket=bucket,
            source=source,
            entity=entity,
            columns=columns,
        ),
    }


def ensure_silver_entity_parquet(*, bucket: str, source: str, entity: str) -> str:
    """Ensure silver data lives under a directory prefix for Athena."""
    import boto3
    from botocore.exceptions import ClientError

    client = boto3.client("s3")
    target_key = silver_entity_parquet_key(source, entity)
    try:
        client.head_object(Bucket=bucket, Key=target_key)
        return target_key
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") not in {"404", "NoSuchKey", "NotFound"}:
            raise

    legacy_key = legacy_silver_entity_parquet_key(source, entity)
    try:
        client.head_object(Bucket=bucket, Key=legacy_key)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in {"404", "NoSuchKey", "NotFound"}:
            raise FileNotFoundError(f"Silver parquet not found for {source}/{entity}") from exc
        raise

    client.copy_object(
        Bucket=bucket,
        Key=target_key,
        CopySource={"Bucket": bucket, "Key": legacy_key},
    )
    logger.info("Migrated silver parquet from %s to %s", legacy_key, target_key)
    return target_key


def recreate_silver_glue_table(
    *,
    database_name: str,
    table_name: str,
    bucket: str,
    source: str,
    entity: str,
    columns: list[dict[str, str]],
    region: str | None = None,
) -> None:
    import boto3
    from botocore.exceptions import ClientError

    client = boto3.client("glue", region_name=region)
    try:
        client.delete_table(DatabaseName=database_name, Name=table_name)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") != "EntityNotFoundException":
            raise

    client.create_table(
        DatabaseName=database_name,
        TableInput=_silver_table_input(
            table_name=table_name,
            bucket=bucket,
            source=source,
            entity=entity,
            columns=columns,
        ),
    )


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
    parquet_key = ensure_silver_entity_parquet(
        bucket=settings.s3_bucket,
        source=settings.source,
        entity=entity_name,
    )
    columns = read_parquet_columns(bucket=settings.s3_bucket, key=parquet_key)
    if not columns:
        raise ValueError(
            f"No columns inferred from s3://{settings.s3_bucket}/{parquet_key}; "
            "re-run consolidate after ingest produces rows."
        )

    recreate_silver_glue_table(
        database_name=database_name,
        table_name=table_name,
        bucket=settings.s3_bucket,
        source=settings.source,
        entity=entity_name,
        columns=columns,
        region=region,
    )
    logger.info(
        "Recreated Glue table %s.%s with %s columns at s3://%s/%s/",
        database_name,
        table_name,
        len(columns),
        settings.s3_bucket,
        silver_entity_prefix(settings.source, entity_name),
    )
    return columns


def raw_table_glue_parameters(
    *,
    bucket: str,
    source: str,
    entity: str,
    run_ids: list[str],
) -> dict[str, str]:
    prefix = raw_source_prefix(source)
    values = ",".join(run_ids)
    return {
        "classification": "parquet",
        "EXTERNAL": "TRUE",
        "projection.enabled": "true",
        "projection.run_id.type": "enum",
        "projection.run_id.values": values,
        "storage.location.template": f"s3://{bucket}/{prefix}/${{run_id}}/{entity}/",
    }


def _raw_storage_descriptor(
    *,
    bucket: str,
    source: str,
    columns: list[dict[str, str]],
) -> dict[str, Any]:
    return {
        "Columns": columns,
        "Location": f"s3://{bucket}/{raw_source_prefix(source)}/",
        "InputFormat": PARQUET_INPUT_FORMAT,
        "OutputFormat": PARQUET_OUTPUT_FORMAT,
        "SerdeInfo": {
            "SerializationLibrary": PARQUET_SERDE,
        },
        "Compressed": True,
    }


def _raw_table_input(
    *,
    table_name: str,
    bucket: str,
    source: str,
    entity: str,
    columns: list[dict[str, str]],
    run_ids: list[str],
) -> dict[str, Any]:
    return {
        "Name": table_name,
        "TableType": "EXTERNAL_TABLE",
        "PartitionKeys": [{"Name": "run_id", "Type": "string"}],
        "Parameters": raw_table_glue_parameters(
            bucket=bucket,
            source=source,
            entity=entity,
            run_ids=run_ids,
        ),
        "StorageDescriptor": _raw_storage_descriptor(
            bucket=bucket,
            source=source,
            columns=columns,
        ),
    }


def recreate_raw_glue_table(
    *,
    database_name: str,
    table_name: str,
    bucket: str,
    source: str,
    entity: str,
    columns: list[dict[str, str]],
    run_ids: list[str],
    region: str | None = None,
) -> None:
    import boto3
    from botocore.exceptions import ClientError

    client = boto3.client("glue", region_name=region)
    try:
        client.delete_table(DatabaseName=database_name, Name=table_name)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") != "EntityNotFoundException":
            raise

    client.create_table(
        DatabaseName=database_name,
        TableInput=_raw_table_input(
            table_name=table_name,
            bucket=bucket,
            source=source,
            entity=entity,
            columns=columns,
            run_ids=run_ids,
        ),
    )


def ensure_raw_entity_parquet(*, bucket: str, source: str, run_id: str, entity: str) -> str | None:
    import boto3
    from botocore.exceptions import ClientError

    client = boto3.client("s3")
    target_key = raw_entity_parquet_key(source, run_id, entity)
    try:
        client.head_object(Bucket=bucket, Key=target_key)
        return target_key
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") not in {"404", "NoSuchKey", "NotFound"}:
            raise

    legacy_key = legacy_raw_entity_parquet_key(source, run_id, entity)
    try:
        client.head_object(Bucket=bucket, Key=legacy_key)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in {"404", "NoSuchKey", "NotFound"}:
            return None
        raise

    client.copy_object(
        Bucket=bucket,
        Key=target_key,
        CopySource={"Bucket": bucket, "Key": legacy_key},
    )
    logger.info("Migrated raw parquet from %s to %s", legacy_key, target_key)
    return target_key


def _available_raw_run_ids(
    settings: ConsolidateSettings,
    entity_name: str,
    run_ids: list[str],
) -> list[str]:
    if not settings.s3_bucket:
        return run_ids

    available: list[str] = []
    for run_id in run_ids:
        if ensure_raw_entity_parquet(
            bucket=settings.s3_bucket,
            source=settings.source,
            run_id=run_id,
            entity=entity_name,
        ):
            available.append(run_id)
    return available


def resolve_catalog_entity_names(source: str) -> list[str]:
    from meshflow.project_config import (
        get_environment_config,
        iter_catalog_entities,
        iter_configured_connectors,
        resolve_selection,
    )

    company, environment = resolve_selection()
    env_config = get_environment_config(company, environment)
    source_slug = source.strip().lower()
    connectors = [
        (connector, connector_cfg)
        for connector, connector_cfg in iter_configured_connectors(env_config)
        if connector == source_slug
    ]
    return [entity for connector, entity in iter_catalog_entities(connectors)]


def sync_raw_tables_for_entities(
    settings: ConsolidateSettings,
    entity_names: list[str],
    *,
    company: str | None = None,
    environment: str | None = None,
    region: str | None = None,
) -> list[dict[str, Any]]:
    """Refresh raw Glue tables after bronze ingest writes new run partitions."""
    if not settings.s3_bucket:
        return []

    results: list[dict[str, Any]] = []
    for entity_name in entity_names:
        try:
            columns, run_ids = sync_raw_table_schema(
                settings,
                entity_name,
                company=company,
                environment=environment,
                region=region,
            )
        except (FileNotFoundError, ValueError) as exc:
            logger.warning(
                "Raw catalog sync skipped for %s/%s: %s",
                settings.source,
                entity_name,
                exc,
            )
            results.append(
                {
                    "layer": "raw",
                    "entity": entity_name,
                    "status": "skipped",
                    "error": str(exc),
                }
            )
            continue

        results.append(
            {
                "layer": "raw",
                "entity": entity_name,
                "status": "synced",
                "glue_columns": len(columns),
                "run_ids": len(run_ids),
            }
        )
    return results


def sync_source_catalog(
    settings: ConsolidateSettings,
    entity_names: list[str] | None = None,
    *,
    company: str | None = None,
    environment: str | None = None,
    region: str | None = None,
    sync_silver: bool = True,
    sync_raw: bool = True,
) -> dict[str, Any]:
    """Recreate silver and raw Glue tables from Parquet for a connector source."""
    if not settings.s3_bucket:
        return {"silver": [], "raw": []}

    entities = entity_names or resolve_catalog_entity_names(settings.source)
    silver_results: list[dict[str, Any]] = []
    raw_results: list[dict[str, Any]] = []

    if sync_silver:
        for entity_name in entities:
            try:
                columns = sync_silver_table_schema(
                    settings,
                    entity_name,
                    company=company,
                    environment=environment,
                    region=region,
                )
            except (FileNotFoundError, ValueError) as exc:
                logger.warning(
                    "Silver catalog sync skipped for %s/%s: %s",
                    settings.source,
                    entity_name,
                    exc,
                )
                silver_results.append(
                    {
                        "entity": entity_name,
                        "status": "skipped",
                        "error": str(exc),
                    }
                )
                continue

            silver_results.append(
                {
                    "entity": entity_name,
                    "status": "synced",
                    "glue_columns": len(columns),
                }
            )

    if sync_raw:
        raw_entities = [
            entity_name
            for entity_name in entities
            if not is_silver_only_catalog_entity(settings.source, entity_name)
        ]
        raw_results = sync_raw_tables_for_entities(
            settings,
            raw_entities,
            company=company,
            environment=environment,
            region=region,
        )

    return {"silver": silver_results, "raw": raw_results}


def sync_raw_table_schema(
    settings: ConsolidateSettings,
    entity_name: str,
    *,
    company: str | None = None,
    environment: str | None = None,
    region: str | None = None,
) -> tuple[list[dict[str, str]], list[str]]:
    if not settings.s3_bucket:
        return [], []

    from meshflow.silver.store import list_bronze_runs

    database_name = glue_database_name(company, environment)
    table_name = catalog_table_name("raw", settings.source, entity_name)
    run_ids = _available_raw_run_ids(settings, entity_name, list_bronze_runs(settings))
    if not run_ids:
        raise FileNotFoundError(f"No bronze runs found for {settings.source}/{entity_name}")

    latest_run_id = run_ids[-1]
    parquet_key = raw_entity_parquet_key(settings.source, latest_run_id, entity_name)
    columns = read_parquet_columns(bucket=settings.s3_bucket, key=parquet_key)
    if not columns:
        raise ValueError(
            f"No columns inferred from s3://{settings.s3_bucket}/{parquet_key}; "
            "confirm the entity exists in the latest bronze run."
        )

    recreate_raw_glue_table(
        database_name=database_name,
        table_name=table_name,
        bucket=settings.s3_bucket,
        source=settings.source,
        entity=entity_name,
        columns=columns,
        run_ids=run_ids,
        region=region,
    )
    logger.info(
        "Recreated Glue table %s.%s with %s columns across %s bronze runs",
        database_name,
        table_name,
        len(columns),
        len(run_ids),
    )
    return columns, run_ids


def _dna_storage_descriptor(
    *,
    bucket: str,
    output_id: str,
    columns: list[dict[str, str]],
) -> dict[str, Any]:
    from meshflow.storage.paths import gold_dna_entity_prefix

    return {
        "Columns": columns,
        "Location": f"s3://{bucket}/{gold_dna_entity_prefix(output_id)}/",
        "InputFormat": PARQUET_INPUT_FORMAT,
        "OutputFormat": PARQUET_OUTPUT_FORMAT,
        "SerdeInfo": {
            "SerializationLibrary": PARQUET_SERDE,
        },
        "Compressed": True,
    }


def recreate_dna_glue_table(
    *,
    database_name: str,
    table_name: str,
    bucket: str,
    output_id: str,
    columns: list[dict[str, str]],
    region: str | None = None,
) -> None:
    import boto3
    from botocore.exceptions import ClientError

    client = boto3.client("glue", region_name=region)
    try:
        client.delete_table(DatabaseName=database_name, Name=table_name)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") != "EntityNotFoundException":
            raise

    client.create_table(
        DatabaseName=database_name,
        TableInput={
            "Name": table_name,
            "TableType": "EXTERNAL_TABLE",
            "Parameters": {
                "classification": "parquet",
                "EXTERNAL": "TRUE",
            },
            "StorageDescriptor": _dna_storage_descriptor(
                bucket=bucket,
                output_id=output_id,
                columns=columns,
            ),
        },
    )


def sync_dna_output_schema(
    *,
    bucket: str,
    output_id: str,
    company: str | None = None,
    environment: str | None = None,
    region: str | None = None,
) -> list[dict[str, str]]:
    from meshflow.project_config import dna_catalog_table_name
    from meshflow.storage.paths import gold_dna_entity_parquet_key

    database_name = glue_database_name(company, environment)
    table_name = dna_catalog_table_name(output_id)
    parquet_key = gold_dna_entity_parquet_key(output_id)
    columns = read_parquet_columns(bucket=bucket, key=parquet_key)
    if not columns:
        raise ValueError(
            f"No columns inferred from s3://{bucket}/{parquet_key}; "
            "run DNA publish before catalog sync."
        )
    recreate_dna_glue_table(
        database_name=database_name,
        table_name=table_name,
        bucket=bucket,
        output_id=output_id,
        columns=columns,
        region=region,
    )
    logger.info(
        "Recreated Glue table %s.%s with %s columns at s3://%s/",
        database_name,
        table_name,
        len(columns),
        bucket,
        parquet_key.rsplit("/", 1)[0],
    )
    return columns


def sync_dna_catalog(
    *,
    bucket: str,
    output_ids: list[str] | None = None,
    company: str | None = None,
    environment: str | None = None,
    region: str | None = None,
) -> list[dict[str, Any]]:
    from meshflow.project_config import iter_dna_catalog_outputs

    results: list[dict[str, Any]] = []
    for output_id in iter_dna_catalog_outputs(output_ids):
        try:
            columns = sync_dna_output_schema(
                bucket=bucket,
                output_id=output_id,
                company=company,
                environment=environment,
                region=region,
            )
        except (FileNotFoundError, ValueError) as exc:
            logger.warning("DNA catalog sync skipped for %s: %s", output_id, exc)
            results.append(
                {
                    "output_id": output_id,
                    "status": "skipped",
                    "error": str(exc),
                }
            )
            continue
        results.append(
            {
                "output_id": output_id,
                "status": "synced",
                "glue_columns": len(columns),
            }
        )
    return results
