"""Back-compat re-exports — prefer ``meshflow.storage.parquet``."""

from meshflow.storage.parquet import (
    IngestDestination,
    LakeDestination,
    local_run_dir,
    normalize_row_for_parquet,
    read_json_local,
    read_json_s3,
    read_parquet_local,
    read_parquet_s3,
    resolve_run_path,
    rows_to_parquet_bytes,
    run_stamp,
    s3_run_prefix,
    write_json_local,
    write_json_s3,
    write_parquet_local,
    write_parquet_s3,
)

__all__ = [
    "IngestDestination",
    "LakeDestination",
    "local_run_dir",
    "normalize_row_for_parquet",
    "read_json_local",
    "read_json_s3",
    "read_parquet_local",
    "read_parquet_s3",
    "resolve_run_path",
    "rows_to_parquet_bytes",
    "run_stamp",
    "s3_run_prefix",
    "write_json_local",
    "write_json_s3",
    "write_parquet_local",
    "write_parquet_s3",
]
