from __future__ import annotations

from unittest.mock import patch

from meshflow.catalog.glue_schema import sync_source_catalog
from meshflow.silver.settings import ConsolidateSettings


def test_sync_source_catalog_skips_when_no_bucket() -> None:
    settings = ConsolidateSettings(source="qbd", data_dir=__import__("pathlib").Path("."))
    assert sync_source_catalog(settings) == {"silver": [], "raw": []}


def test_sync_source_catalog_calls_silver_and_raw() -> None:
    settings = ConsolidateSettings(
        source="qbd",
        data_dir=__import__("pathlib").Path("."),
        s3_bucket="meshflow-poc-123-us-east-2",
        raw_prefix="raw/qbd",
    )
    with (
        patch(
            "meshflow.catalog.glue_schema.resolve_catalog_entity_names",
            return_value=["customers", "invoices"],
        ),
        patch(
            "meshflow.catalog.glue_schema.sync_silver_table_schema",
            side_effect=lambda _settings, entity, **_kwargs: [{"Name": "id", "Type": "string"}],
        ) as silver_sync,
        patch(
            "meshflow.catalog.glue_schema.sync_raw_tables_for_entities",
            return_value=[{"layer": "raw", "entity": "customers", "status": "synced"}],
        ) as raw_sync,
    ):
        result = sync_source_catalog(settings)

    assert silver_sync.call_count == 2
    raw_sync.assert_called_once_with(
        settings,
        ["customers", "invoices"],
        company=None,
        environment=None,
        region=None,
    )
    assert len(result["silver"]) == 2
    assert result["raw"][0]["status"] == "synced"
