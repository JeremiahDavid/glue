"""Pull raw QuickBooks Online entities to local JSON files."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap  # noqa: E402, F401

from hiveflow.cli import ingest_main

if __name__ == "__main__":
    ingest_main()
