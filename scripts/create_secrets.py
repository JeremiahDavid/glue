"""Create HiveFlow QBO secrets in AWS Secrets Manager from a YAML file."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap  # noqa: E402, F401

from hiveflow.cli import create_secrets_main

if __name__ == "__main__":
    create_secrets_main()
