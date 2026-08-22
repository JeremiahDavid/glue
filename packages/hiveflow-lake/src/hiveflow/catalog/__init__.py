"""Sync Glue table columns from Parquet files for Athena queries."""

from hiveflow.catalog.glue_schema import (
    sync_raw_tables_for_entities,
    sync_silver_table_schema,
    sync_source_catalog,
)

__all__ = [
    "sync_raw_tables_for_entities",
    "sync_silver_table_schema",
    "sync_source_catalog",
]
