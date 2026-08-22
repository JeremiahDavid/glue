"""Run the QuickBooks Web Connector SOAP server locally."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap  # noqa: E402, F401

from hiveflow.cli import qbd_soap_main

if __name__ == "__main__":
    qbd_soap_main()
