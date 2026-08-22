"""Sync Glue/Athena table schemas from existing silver Parquet files."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap  # noqa: E402, F401

from hiveflow.cli import sync_athena_catalog_main

if __name__ == "__main__":
    sync_athena_catalog_main()
