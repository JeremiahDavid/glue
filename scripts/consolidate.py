"""Consolidate bronze parquet runs into single entity tables."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap  # noqa: E402, F401

from hiveflow.cli import consolidate_main

if __name__ == "__main__":
    consolidate_main()
