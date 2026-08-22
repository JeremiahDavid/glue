#!/usr/bin/env python3
"""Run a Business Central ingest locally or against S3."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap  # noqa: E402, F401

from hiveflow.cli import bc_ingest_main

if __name__ == "__main__":
    bc_ingest_main()
