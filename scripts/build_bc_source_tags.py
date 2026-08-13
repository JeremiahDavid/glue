#!/usr/bin/env python3
"""Build entity_property_tags.yaml from S3 entity_properties.yaml.

Reads s3://hiveflowai-source-documentation/{source}/entity_properties.yaml
(or a local YAML with --input) and publishes
s3://hiveflowai-source-documentation/{source}/entity_property_tags.yaml.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap  # noqa: E402, F401

from meshflow.dna.source_docs import (  # noqa: E402
    source_docs_bucket_name,
    source_docs_object_key,
    source_docs_tags_object_key,
)
from meshflow.dna.source_docs.tags import (  # noqa: E402
    build_entity_property_tags,
    run_source_docs_tags_job,
    tags_to_yaml,
    write_entity_property_tags,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default="dbc", help="Connector source key (default: dbc)")
    parser.add_argument(
        "--bucket",
        default="",
        help=f"S3 bucket (default: {source_docs_bucket_name()})",
    )
    parser.add_argument(
        "--properties-object-key",
        default="",
        help=f"Source properties key (default: {source_docs_object_key('dbc')})",
    )
    parser.add_argument(
        "--tags-object-key",
        default="",
        help=f"Output tags key (default: {source_docs_tags_object_key('dbc')})",
    )
    parser.add_argument(
        "--input",
        type=Path,
        help="Optional local entity_properties.yaml (skips S3 download)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional local tags YAML path (skips S3 upload when set)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build and summarize without writing S3/local output",
    )
    args = parser.parse_args()

    if args.input is not None or args.output is not None:
        if args.input is None:
            print("--input is required when using --output", file=sys.stderr)
            return 2
        catalog = yaml.safe_load(args.input.read_text(encoding="utf-8")) or {}
        payload = build_entity_property_tags(catalog, sourced_from=str(args.input))
        summary = {
            "entity_count": payload.get("entity_count"),
            "property_count": payload.get("property_count"),
            "tagged_property_count": payload.get("tagged_property_count"),
            "sourced_from": payload.get("sourced_from"),
        }
        print(json.dumps(summary, indent=2))
        if args.dry_run:
            return 0
        if args.output is not None:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(tags_to_yaml(payload), encoding="utf-8")
            print(f"Wrote {args.output}")
            return 0
        written = write_entity_property_tags(
            payload,
            bucket=args.bucket or None,
            object_key=args.tags_object_key or None,
        )
        print(json.dumps({"status": "published", "artifact": written}, indent=2, default=str))
        return 0

    result = run_source_docs_tags_job(
        source=args.source,
        bucket=args.bucket or None,
        properties_object_key=args.properties_object_key or None,
        tags_object_key=args.tags_object_key or None,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("status") in {"published", "dry_run", "built"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
