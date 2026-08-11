#!/usr/bin/env python3
"""Merge global BC source docs with client overlays into gold YAML.

Reads global catalogs from s3://hiveflowai-source-documentation/dbc/ and client
overlays from governance/source_semantic_reference/dbc/ in the company lake
bucket, then writes gold files under .../dbc/gold/.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap  # noqa: E402, F401

from meshflow.bc.source_docs import source_docs_bucket_name  # noqa: E402
from meshflow.bc.source_docs_gold import (  # noqa: E402
    client_data_bucket_name,
    run_source_docs_gold_job,
)
from meshflow.bc.source_docs_schema import SCHEMA_ARTIFACT_NAMES  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default="dbc", help="Connector source key (default: dbc)")
    parser.add_argument(
        "--client-bucket",
        default="",
        help=f"Company lake bucket (default: MESHFLOW_S3_BUCKET / {client_data_bucket_name() or 'unset'})",
    )
    parser.add_argument(
        "--global-bucket",
        default="",
        help=f"Global docs bucket (default: {source_docs_bucket_name()})",
    )
    parser.add_argument(
        "--artifacts",
        nargs="*",
        choices=list(SCHEMA_ARTIFACT_NAMES),
        help="Subset of artifacts to merge (default: all)",
    )
    parser.add_argument(
        "--publish-schemas",
        action="store_true",
        help="Also upload JSON schemas to the global docs bucket",
    )
    parser.add_argument(
        "--seed-missing-overlays",
        action="store_true",
        help="Write empty overlay stubs when client overlays are missing",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and merge without writing S3 objects",
    )
    args = parser.parse_args()

    result = run_source_docs_gold_job(
        source=args.source,
        client_bucket=args.client_bucket or None,
        global_bucket=args.global_bucket or None,
        artifacts=list(args.artifacts) if args.artifacts else None,
        publish_schemas=bool(args.publish_schemas),
        dry_run=bool(args.dry_run),
        seed_missing_overlays=bool(args.seed_missing_overlays),
    )
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("status") in {"published", "dry_run"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
