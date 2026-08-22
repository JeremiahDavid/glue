"""Company data lake path conventions and shared Parquet I/O."""

from meshflow.storage.paths import (
    DATA_LAYERS,
    gold_prefix,
    layer_source_prefix,
    legacy_silver_entity_parquet_key,
    prefix_path,
    raw_source_prefix,
    silver_entity_parquet_key,
    silver_entity_prefix,
    silver_source_prefix,
    silver_stg_entity_parquet_key,
    silver_stg_entity_prefix,
    silver_stg_source_prefix,
)
from meshflow.storage.parquet import (
    read_parquet_local,
    read_parquet_s3,
    write_parquet_local,
    write_parquet_s3,
)

__all__ = [
    "DATA_LAYERS",
    "gold_prefix",
    "layer_source_prefix",
    "legacy_silver_entity_parquet_key",
    "prefix_path",
    "raw_source_prefix",
    "read_parquet_local",
    "read_parquet_s3",
    "silver_entity_parquet_key",
    "silver_entity_prefix",
    "silver_source_prefix",
    "silver_stg_entity_parquet_key",
    "silver_stg_entity_prefix",
    "silver_stg_source_prefix",
    "write_parquet_local",
    "write_parquet_s3",
]
