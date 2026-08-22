"""Tests for silver schema profile emission."""

from __future__ import annotations

from pathlib import Path

import pytest

from hiveflow.ingest.storage import write_parquet_local
from hiveflow.silver.schema_profile import build_silver_schema_profile
from hiveflow.silver.settings import ConsolidateSettings
from hiveflow.storage.paths import prefix_path, silver_stg_entity_prefix


@pytest.fixture
def settings(tmp_path: Path) -> ConsolidateSettings:
    return ConsolidateSettings(source="dbc", data_dir=tmp_path, s3_bucket=None)


def test_build_silver_schema_profile_reads_local_parquet(settings: ConsolidateSettings) -> None:
    out = prefix_path(settings.data_dir, silver_stg_entity_prefix(settings.source, "customers"))
    write_parquet_local(
        out,
        "data.parquet",
        [{"id": "c1", "displayName": "Acme"}],
    )
    profile = build_silver_schema_profile(
        settings,
        ["customers"],
        consolidated_at="2026-01-01T00:00:00Z",
    )
    assert profile["kind"] == "silver_schema_profile"
    assert profile["table_count"] == 1
    table = profile["tables"][0]
    assert table["silver_entity"] == "customers"
    assert table["glue_table"] == "silver_stg_dbc_customers"
    names = [col["name"] for col in table["columns"]]
    assert "displayName" in names
    assert table["columns"][names.index("displayName")]["origin"] == "api"


def test_build_silver_schema_profile_marks_unpack_columns(settings: ConsolidateSettings) -> None:
    out = prefix_path(settings.data_dir, silver_stg_entity_prefix(settings.source, "sales_invoice_lines"))
    write_parquet_local(
        out,
        "data.parquet",
        [{"id": "l1", "documentId": "h1", "header_id": "h1"}],
    )
    profile = build_silver_schema_profile(settings, ["sales_invoice_lines"])
    table = profile["tables"][0]
    origins = {col["name"]: col["origin"] for col in table["columns"]}
    assert origins["header_id"] == "unpack"
    assert origins["documentId"] == "api"
