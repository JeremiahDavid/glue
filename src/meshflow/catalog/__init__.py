"""Sync Glue table columns from Parquet files for Athena queries."""

from meshflow.catalog.glue_schema import sync_silver_table_schema

__all__ = ["sync_silver_table_schema"]
