#!/usr/bin/env python3
"""Scrape Microsoft Learn APV2 Properties tables into global source documentation.

Owned by meshflow-dna. Writes YAML to
s3://hiveflowai-source-documentation/{source}/entity_properties.yaml
(or a local path with --output).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap  # noqa: E402, F401

from meshflow.dna.source_docs import (  # noqa: E402
    build_source_properties_catalog,
    catalog_to_yaml,
    run_source_docs_scrape_job,
    scrape_ms_learn_entity_pages,
    source_docs_bucket_name,
    source_docs_object_key,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default="dbc", help="Connector source key (default: dbc)")
    parser.add_argument(
        "--delay",
        type=float,
        default=0.35,
        help="Seconds between Microsoft Learn requests (default: 0.35)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Max entities to fetch (0 = all mapped entities)",
    )
    parser.add_argument(
        "--bucket",
        default="",
        help=f"S3 bucket (default: {source_docs_bucket_name()})",
    )
    parser.add_argument(
        "--object-key",
        default="",
        help=f"S3 object key (default: {source_docs_object_key('dbc')})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional local YAML path (skips S3 upload when set)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scrape and summarize without writing S3/local output",
    )
    args = parser.parse_args()

    if args.output is not None:
        pages, mapped, failures = scrape_ms_learn_entity_pages(
            delay_seconds=args.delay,
            limit=args.limit,
        )
        catalog = build_source_properties_catalog(pages, source=args.source, failures=failures)
        summary = {
            "mapped_slug_count": len(mapped),
            "entity_count": catalog.get("entity_count"),
            "property_count": catalog.get("property_count"),
            "failure_count": len(failures),
        }
        print(json.dumps(summary, indent=2))
        if args.dry_run:
            return 0
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(catalog_to_yaml(catalog), encoding="utf-8")
        print(f"Wrote {args.output}")
        return 0

    result = run_source_docs_scrape_job(
        source=args.source,
        delay_seconds=args.delay,
        limit=args.limit,
        bucket=args.bucket or None,
        object_key=args.object_key or None,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("status") in {"published", "dry_run", "scraped"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
