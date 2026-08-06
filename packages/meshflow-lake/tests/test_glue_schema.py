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
