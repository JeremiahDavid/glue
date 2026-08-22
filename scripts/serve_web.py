"""Run the HiveFlowAI web UI locally for development.

Loads optional settings from .env at the repo root.

By default enables dev mode (auto-reload, no static caching). Portal auth:

  Cognito: HIVEFLOW_COGNITO_USER_POOL_ID, HIVEFLOW_COGNITO_CLIENT_ID, HIVEFLOW_COGNITO_REGION
  Local:   HIVEFLOW_PORTAL_USERNAME, HIVEFLOW_PORTAL_PASSWORD, HIVEFLOW_PORTAL_CLIENT_ID

Reporting/governance data is read from the S3 data bucket in config.yaml when AWS credentials
are configured. Use --local-data to read from HIVEFLOW_DATA_DIR instead (default: data/).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap  # noqa: E402, F401

_ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv(_ROOT / ".env")

    parser = argparse.ArgumentParser(description="Run HiveFlowAI web UI locally")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8080, help="Port (default: 8080)")
    parser.add_argument(
        "--config",
        default=str(_ROOT / "config.yaml"),
        help="Path to config.yaml (default: repo root config.yaml)",
    )
    parser.add_argument(
        "--local-data",
        action="store_true",
        help="Read governance/reporting from data/ instead of S3",
    )
    parser.add_argument(
        "--no-reload",
        action="store_true",
        help="Disable auto-reload when Python files change",
    )
    args, extra = parser.parse_known_args()

    os.environ.setdefault("HIVEFLOW_DEV", "1")
    if args.local_data:
        os.environ["HIVEFLOW_LOCAL_DATA"] = "1"
        print(f"Local data mode — reading from {os.getenv('HIVEFLOW_DATA_DIR', 'data')}/")
    else:
        print("S3 data mode — governance/reporting loaded from the configured data bucket.")

    sys.argv = [
        "serve_web.py",
        "serve",
        "--host",
        args.host,
        "--port",
        str(args.port),
        "--config",
        args.config,
        *extra,
    ]

    from hiveflow.cli import dna_main

    if args.no_reload:
        os.environ.pop("HIVEFLOW_DEV", None)

    dna_main()


if __name__ == "__main__":
    main()
