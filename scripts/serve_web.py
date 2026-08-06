"""Run the HiveFlowAI web UI locally for development.

Loads optional settings from .env at the repo root.

Portal auth (pick one):
  Cognito: HIVEFLOW_COGNITO_USER_POOL_ID, HIVEFLOW_COGNITO_CLIENT_ID, HIVEFLOW_COGNITO_REGION
  Local:   HIVEFLOW_PORTAL_USERNAME, HIVEFLOW_PORTAL_PASSWORD, HIVEFLOW_PORTAL_CLIENT_ID

Reporting data uses the S3 data bucket from config.yaml when AWS credentials are configured.
"""

from __future__ import annotations

import argparse
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
    args, extra = parser.parse_known_args()

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

    from meshflow.cli import dna_main

    dna_main()


if __name__ == "__main__":
    main()
