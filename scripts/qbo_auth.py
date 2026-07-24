"""Connect QuickBooks Online via OAuth and save tokens locally."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap  # noqa: E402, F401

from meshflow.cli import auth_main

if __name__ == "__main__":
    auth_main()
