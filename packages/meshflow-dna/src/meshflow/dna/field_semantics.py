"""Silver entity discovery helpers for DNA Catalog."""

from __future__ import annotations

import io
from typing import Any

from meshflow.dna.settings import DnaSettings
from meshflow.dna.store import read_silver_entity
from meshflow.storage.paths import (
    prefix_path,
    silver_entity_parquet_key,
    silver_entity_prefix,
)

_PREVIEW_LIMIT = 20


def list_silver_entities(settings: DnaSettings) -> list[str]:
    from meshflow.entity_registry import catalog_entity_names

    source = settings.source.strip().lower()
    connector = source
    try:
        names = catalog_entity_names(connector, {})
    except (ValueError, ImportError):
        names = []
    return sorted({name.strip().lower() for name in names if name.strip()})


def _parquet_schema_columns(settings: DnaSettings, entity: str) -> list[str]:
    import pyarrow.parquet as pq

    entity_name = entity.strip().lower()
    if settings.s3_bucket:
        import boto3

        key = silver_entity_parquet_key(settings.source, entity_name)
        payload = boto3.client("s3").get_object(Bucket=settings.s3_bucket, Key=key)["Body"].read()
        schema = pq.read_schema(io.BytesIO(payload))
        return [str(field.name) for field in schema]
    path = prefix_path(
        settings.data_dir,
        silver_entity_prefix(settings.source, entity_name),
        "data.parquet",
    )
    if not path.is_file():
        return []
    schema = pq.read_schema(path)
    return [str(field.name) for field in schema]


def discover_silver_columns(settings: DnaSettings, entity: str) -> list[str]:
    columns = _parquet_schema_columns(settings, entity)
    if columns:
        return columns
    rows = read_silver_entity(settings, entity)
    if not rows:
        return []
    keys: set[str] = set()
    for row in rows[:50]:
        if isinstance(row, dict):
            keys.update(row.keys())
    return sorted(keys)


def preview_silver_entity(
    settings: DnaSettings,
    entity: str,
    *,
    limit: int = _PREVIEW_LIMIT,
) -> list[dict[str, Any]]:
    rows = read_silver_entity(settings, entity)
    return rows[: max(1, limit)]
