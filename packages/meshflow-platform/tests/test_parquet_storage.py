from meshflow.ingest.storage import read_parquet_local, rows_to_parquet_bytes, write_parquet_local


def test_read_parquet_local_reads_buffered_bytes(tmp_path) -> None:
    rows = [{"ListID": "1", "Name": "Alpha"}]
    path = write_parquet_local(tmp_path, "customers.parquet", rows)
    assert read_parquet_local(tmp_path / "customers.parquet") == rows
    assert read_parquet_local(tmp_path / "missing.parquet") == []


def test_rows_to_parquet_bytes_roundtrip() -> None:
    import io
    import json

    import pyarrow.parquet as pq

    rows = [{"ListID": "1", "Name": "Alpha"}]
    table = pq.read_table(io.BytesIO(rows_to_parquet_bytes(rows)))
    assert table.to_pylist() == rows


def test_rows_to_parquet_bytes_serializes_nested_values() -> None:
    import io
    import json

    import pyarrow.parquet as pq

    rows = [{"id": "1", "meta": {"a": 1}, "tags": ["x"]}]
    table = pq.read_table(io.BytesIO(rows_to_parquet_bytes(rows)))
    assert table.to_pylist() == [
        {"id": "1", "meta": json.dumps({"a": 1}), "tags": json.dumps(["x"])}
    ]
