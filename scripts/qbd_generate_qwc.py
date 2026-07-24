"""Generate a QuickBooks Web Connector .qwc file from config/secrets."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap  # noqa: E402, F401

from meshflow.cli import qbd_generate_qwc_main

if __name__ == "__main__":
    qbd_generate_qwc_main()
