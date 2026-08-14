from meshflow.catalog.glue_schema import arrow_field_to_glue_column


def test_arrow_field_to_glue_column_maps_string() -> None:
    import pyarrow as pa

    field = pa.field("Name", pa.string())
    column = arrow_field_to_glue_column(field)
    assert column == {"Name": "Name", "Type": "string"}


def test_arrow_field_to_glue_column_maps_int64() -> None:
    import pyarrow as pa

    field = pa.field("Balance", pa.int64())
    column = arrow_field_to_glue_column(field)
    assert column == {"Name": "Balance", "Type": "bigint"}


def test_drop_unused_silver_tables_keeps_pack_entities() -> None:
    from unittest.mock import MagicMock, patch

    from meshflow.catalog.glue_schema import drop_unused_silver_tables

    pages = [
        {
            "TableList": [
                {"Name": "silver_dbc_customers"},
                {"Name": "silver_dbc_vendors"},
                {"Name": "silver_stg_dbc_vendors"},
                {"Name": "raw_dbc_customers"},
            ]
        }
    ]
    client = MagicMock()
    client.get_paginator.return_value.paginate.return_value = pages

    with patch("boto3.client", return_value=client):
        dropped = drop_unused_silver_tables(
            source="dbc",
            keep_entities={"customers"},
            company="POC",
            environment="dev",
        )

    assert dropped == ["silver_dbc_vendors"]
    client.delete_table.assert_called_once_with(
        DatabaseName="meshflow_poc_dev",
        Name="silver_dbc_vendors",
    )
