#!/usr/bin/env python3
"""Scrape Microsoft Learn APV2 entity docs into connector profiling_rules.yaml."""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap  # noqa: E402, F401

from hiveflow.dna.bc_profiling_rules import (  # noqa: E402
    _MS_LEARN_BASE,
    _TOC_URL,
    build_profiling_rules_from_pages,
    load_toc_slugs_from_json,
    profiling_rules_path,
    slug_to_silver_entity,
)

_USER_AGENT = "HiveFlowBCProfiler/1.0 (+https://github.com/hiveflow)"


def _fetch(url: str, *, timeout: int = 60) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8")


def _fetch_entity_page(slug: str) -> str:
    url = f"{_MS_LEARN_BASE}/resources/{slug}"
    return _fetch(url)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=profiling_rules_path("dbc"),
        help="Output YAML path (default: connector_knowledge/dbc/profiling_rules.yaml)",
    )
    parser.add_argument(
        "--source",
        default="dbc",
        help="Connector source key (default: dbc)",
    )
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
        "--dry-run",
        action="store_true",
        help="Print summary without writing output file",
    )
    args = parser.parse_args()

    print(f"Fetching APV2 TOC from {_TOC_URL}")
    toc_text = _fetch(_TOC_URL)
    slugs = load_toc_slugs_from_json(toc_text)
    mapped = [slug for slug in slugs if slug_to_silver_entity(slug)]
    if args.limit > 0:
        mapped = mapped[: args.limit]
    print(f"Found {len(slugs)} APV2 resources; scraping {len(mapped)} mapped to HiveFlow silver tables")

    pages: dict[str, str] = {}
    failures: list[str] = []
    for index, slug in enumerate(mapped, start=1):
        silver = slug_to_silver_entity(slug)
        print(f"[{index}/{len(mapped)}] {slug} -> {silver}")
        try:
            pages[slug] = _fetch_entity_page(slug)
        except urllib.error.HTTPError as exc:
            failures.append(f"{slug}: HTTP {exc.code}")
            print(f"  WARN: HTTP {exc.code} for {slug}")
        except urllib.error.URLError as exc:
            failures.append(f"{slug}: {exc}")
            print(f"  WARN: {exc}")
        if index < len(mapped):
            time.sleep(max(0.0, args.delay))

    rules = build_profiling_rules_from_pages(pages)
    rules["source"] = args.source.strip().lower()
    rules["scrape_failures"] = failures

    summary = {
        "entities": rules.get("entity_count"),
        "relationships": len(rules.get("relationships") or []),
        "column_hints": len(rules.get("column_hints") or {}),
        "failures": len(failures),
    }
    print(json.dumps(summary, indent=2))

    if args.dry_run:
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        yaml.safe_dump(rules, sort_keys=False, allow_unicode=True, width=120),
        encoding="utf-8",
    )
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
