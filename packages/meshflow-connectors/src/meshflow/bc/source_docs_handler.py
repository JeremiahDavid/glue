from __future__ import annotations

from typing import Any


def _enqueue_relationships_job(result: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any] | None:
    """Fire-and-forget invoke of the relationships Lambda after a successful scrape publish."""
    import json
    import os

    if result.get("status") != "published":
        return None
    if bool(payload.get("skip_relationships")):
        return {"skipped": True, "reason": "skip_relationships"}

    function_name = os.getenv("MESHFLOW_SOURCE_DOCS_RELATIONSHIPS_FUNCTION", "").strip()
    if not function_name:
        return {"skipped": True, "reason": "relationships_function_unset"}

    import boto3

    artifact = result.get("artifact") if isinstance(result.get("artifact"), dict) else {}
    invoke_payload = {
        "source": result.get("source") or payload.get("source") or "dbc",
        "bucket": artifact.get("bucket") or payload.get("bucket") or None,
        "properties_object_key": artifact.get("key") or payload.get("object_key") or None,
    }
    client = boto3.client("lambda")
    response = client.invoke(
        FunctionName=function_name,
        InvocationType="Event",
        Payload=json.dumps(invoke_payload, default=str).encode("utf-8"),
    )
    return {
        "function_name": function_name,
        "status_code": int(response.get("StatusCode") or 0),
        "payload": invoke_payload,
    }


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
    follow_on = _enqueue_relationships_job(result, payload)
    if follow_on is not None:
        result = {**result, "relationships_enqueue": follow_on}
        print(json.dumps({"msg": "source_docs_relationships_enqueued", **follow_on}, default=str))
    print(json.dumps({"msg": "source_docs_scrape_done", "result": result}, default=str))
    return result


def lambda_handler(event: dict[str, Any] | None, context: Any) -> dict[str, Any]:
    return handler(event, context)
