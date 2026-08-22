#!/usr/bin/env python3
"""Publish BC source-docs JSON schemas to the global documentation bucket.

Uploads in-package schemas to:
s3://hiveflowai-source-documentation/{source}/schemas/
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap  # noqa: E402, F401

from hiveflow.dna.source_docs import source_docs_bucket_name  # noqa: E402
from hiveflow.dna.source_docs.schema import publish_source_docs_schemas  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default="dbc")
    parser.add_argument(
        "--bucket",
        default="",
        help=f"S3 bucket (default: {source_docs_bucket_name()})",
    )
    args = parser.parse_args()
    result = publish_source_docs_schemas(
        bucket=args.bucket or None,
        source=args.source,
    )
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
