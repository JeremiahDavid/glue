from __future__ import annotations

from typing import Any


def handler(event: dict[str, Any] | None, _context: Any) -> dict[str, Any]:
    """Lambda entry for biweekly Microsoft Learn source-documentation scrape."""
    import json

    from meshflow.bc.source_docs import run_source_docs_scrape_job

    payload = event or {}
    source = str(payload.get("source") or "dbc").strip().lower() or "dbc"
    delay_raw = payload.get("delay_seconds", 0.35)
    try:
        delay_seconds = float(delay_raw)
    except (TypeError, ValueError):
        delay_seconds = 0.35
    limit_raw = payload.get("limit", 0)
    try:
        limit = int(limit_raw)
    except (TypeError, ValueError):
        limit = 0
    dry_run = bool(payload.get("dry_run"))
    bucket = str(payload.get("bucket") or "").strip() or None
    object_key = str(payload.get("object_key") or "").strip() or None

    print(
        json.dumps(
            {
                "msg": "source_docs_scrape_start",
                "source": source,
                "limit": limit,
                "dry_run": dry_run,
            }
        )
    )
    result = run_source_docs_scrape_job(
        source=source,
        delay_seconds=delay_seconds,
        limit=limit,
        bucket=bucket,
        object_key=object_key,
        dry_run=dry_run,
    )
    print(json.dumps({"msg": "source_docs_scrape_done", "result": result}, default=str))
    return result


def lambda_handler(event: dict[str, Any] | None, context: Any) -> dict[str, Any]:
    return handler(event, context)
