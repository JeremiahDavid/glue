from meshflow.ingest.storage import read_parquet_local, rows_to_parquet_bytes, write_parquet_local


def test_read_parquet_local_reads_buffered_bytes(tmp_path) -> None:
    rows = [{"ListID": "1", "Name": "Alpha"}]
    path = write_parquet_local(tmp_path, "customers.parquet", rows)
    assert read_parquet_local(tmp_path / "customers.parquet") == rows
    assert read_parquet_local(tmp_path / "missing.parquet") == []


def test_rows_to_parquet_bytes_roundtrip() -> None:
    import io

    import pyarrow.parquet as pq

    rows = [{"ListID": "1", "Name": "Alpha"}]
    table = pq.read_table(io.BytesIO(rows_to_parquet_bytes(rows)))
    assert table.to_pylist() == rows
