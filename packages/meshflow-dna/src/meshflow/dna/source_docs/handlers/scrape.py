from __future__ import annotations

from typing import Any


def _enqueue_follow_on(
    *,
    result: dict[str, Any],
    payload: dict[str, Any],
    function_env: str,
    skip_flag: str,
    unset_reason: str,
) -> dict[str, Any] | None:
    """Fire-and-forget invoke of a follow-on Lambda after a successful scrape publish."""
    import json
    import os

    if result.get("status") != "published":
        return None
    if bool(payload.get(skip_flag)):
        return {"skipped": True, "reason": skip_flag}

    function_name = os.getenv(function_env, "").strip()
    if not function_name:
        return {"skipped": True, "reason": unset_reason}

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


def _enqueue_relationships_job(result: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any] | None:
    return _enqueue_follow_on(
        result=result,
        payload=payload,
        function_env="MESHFLOW_SOURCE_DOCS_RELATIONSHIPS_FUNCTION",
        skip_flag="skip_relationships",
        unset_reason="relationships_function_unset",
    )


def _enqueue_tags_job(result: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any] | None:
    return _enqueue_follow_on(
        result=result,
        payload=payload,
        function_env="MESHFLOW_SOURCE_DOCS_TAGS_FUNCTION",
        skip_flag="skip_tags",
        unset_reason="tags_function_unset",
    )


def handler(event: dict[str, Any] | None, _context: Any) -> dict[str, Any]:
    """Lambda entry for biweekly Microsoft Learn source-documentation scrape."""
    import json

    from meshflow.dna.source_docs.scrape import run_source_docs_scrape_job

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
    relationships_enqueue = _enqueue_relationships_job(result, payload)
    if relationships_enqueue is not None:
        result = {**result, "relationships_enqueue": relationships_enqueue}
        print(
            json.dumps(
                {"msg": "source_docs_relationships_enqueued", **relationships_enqueue},
                default=str,
            )
        )
    tags_enqueue = _enqueue_tags_job(result, payload)
    if tags_enqueue is not None:
        result = {**result, "tags_enqueue": tags_enqueue}
        print(json.dumps({"msg": "source_docs_tags_enqueued", **tags_enqueue}, default=str))
    print(json.dumps({"msg": "source_docs_scrape_done", "result": result}, default=str))
    return result


def lambda_handler(event: dict[str, Any] | None, context: Any) -> dict[str, Any]:
    return handler(event, context)
