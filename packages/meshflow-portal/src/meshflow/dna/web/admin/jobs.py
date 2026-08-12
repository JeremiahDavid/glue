"""Invoke and monitor registered platform admin jobs."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from typing import Any

from meshflow.dna.web.admin.registry import AdminJob, get_admin_job


class UnknownAdminJob(Exception):
    def __init__(self, job_id: str) -> None:
        self.job_id = job_id
        super().__init__(f"Unknown admin job: {job_id}")


class AdminJobMisconfigured(Exception):
    def __init__(self, job_id: str, reason: str) -> None:
        self.job_id = job_id
        self.reason = reason
        super().__init__(f"Admin job {job_id} misconfigured: {reason}")


def _region() -> str:
    return (
        os.environ.get("AWS_REGION")
        or os.environ.get("AWS_DEFAULT_REGION")
        or "us-east-2"
    )


def _on_lambda() -> bool:
    return bool(os.environ.get("AWS_LAMBDA_FUNCTION_NAME", "").strip())


def enqueue_admin_job(
    job_id: str,
    *,
    payload_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Event-invoke the Lambda for a registered admin job."""
    job = get_admin_job(job_id)
    if job is None:
        raise UnknownAdminJob(job_id)

    function_name = job.function_name()
    if not function_name:
        raise AdminJobMisconfigured(job.id, f"env {job.function_env} is unset")

    payload = dict(job.default_payload)
    if payload_overrides:
        payload.update(payload_overrides)

    if not _on_lambda():
        return {
            "status": "dry_run",
            "job_id": job.id,
            "function_name": function_name,
            "payload": payload,
            "message": "Not running on Lambda — invoke skipped (dry run).",
        }

    import boto3

    client = boto3.client("lambda", region_name=_region())
    response = client.invoke(
        FunctionName=function_name,
        InvocationType="Event",
        Payload=json.dumps(payload, default=str).encode("utf-8"),
    )
    status_code = int(response.get("StatusCode") or 0)
    return {
        "status": "queued" if status_code in {202, 200} else "error",
        "job_id": job.id,
        "function_name": function_name,
        "payload": payload,
        "http_status": status_code,
        "queued_at": datetime.now(UTC).isoformat(),
        "follow_ons": list(job.follow_ons),
    }


def _recent_log_snippet(function_name: str) -> dict[str, Any]:
    """Best-effort last CloudWatch log lines for a Lambda function."""
    import boto3
    from botocore.exceptions import ClientError

    logs = boto3.client("logs", region_name=_region())
    log_group = f"/aws/lambda/{function_name}"
    try:
        streams = logs.describe_log_streams(
            logGroupName=log_group,
            orderBy="LastEventTime",
            descending=True,
            limit=1,
        )
    except ClientError as exc:
        code = str(exc.response.get("Error", {}).get("Code") or "")
        if code in {"ResourceNotFoundException", "AccessDeniedException"}:
            return {"available": False, "reason": code}
        return {"available": False, "reason": "describe_failed", "error": str(exc)}

    stream_list = streams.get("logStreams") or []
    if not stream_list:
        return {"available": False, "reason": "no_streams"}

    stream_name = str(stream_list[0].get("logStreamName") or "")
    if not stream_name:
        return {"available": False, "reason": "empty_stream"}

    try:
        events = logs.filter_log_events(
            logGroupName=log_group,
            logStreamNames=[stream_name],
            limit=20,
            interleaved=True,
        )
    except ClientError as exc:
        return {"available": False, "reason": "filter_failed", "error": str(exc)}

    messages = [
        str(event.get("message") or "").strip()
        for event in (events.get("events") or [])
        if str(event.get("message") or "").strip()
    ]
    if not messages:
        return {"available": False, "reason": "no_events", "stream": stream_name}

    # Prefer a JSON status line from our handlers when present.
    summary = messages[-1]
    for message in reversed(messages):
        if '"status"' in message or '"msg"' in message:
            summary = message
            break
    return {
        "available": True,
        "stream": stream_name,
        "summary": summary[:500],
        "event_count": len(messages),
    }


def admin_job_status(job_id: str) -> dict[str, Any]:
    """Return Lambda configuration + optional recent log summary for a job."""
    job = get_admin_job(job_id)
    if job is None:
        raise UnknownAdminJob(job_id)

    function_name = job.function_name()
    if not function_name:
        raise AdminJobMisconfigured(job.id, f"env {job.function_env} is unset")

    result: dict[str, Any] = {
        "job_id": job.id,
        "source": job.source,
        "title": job.title,
        "function_name": function_name,
        "checked_at": datetime.now(UTC).isoformat(),
    }

    if not _on_lambda():
        result.update(
            {
                "state": "local",
                "message": "Status checks require the admin Lambda runtime.",
                "logs": {"available": False, "reason": "local"},
            }
        )
        return result

    import boto3
    from botocore.exceptions import ClientError

    client = boto3.client("lambda", region_name=_region())
    try:
        config = client.get_function_configuration(FunctionName=function_name)
    except ClientError as exc:
        result.update(
            {
                "state": "unknown",
                "message": str(exc),
                "logs": {"available": False, "reason": "get_function_failed"},
            }
        )
        return result

    result.update(
        {
            "state": str(config.get("State") or "Unknown"),
            "last_update_status": str(config.get("LastUpdateStatus") or ""),
            "last_modified": str(config.get("LastModified") or ""),
            "timeout": config.get("Timeout"),
            "memory_size": config.get("MemorySize"),
        }
    )
    result["logs"] = _recent_log_snippet(function_name)
    if result["logs"].get("available"):
        result["message"] = result["logs"].get("summary") or "Recent log events available."
    else:
        reason = result["logs"].get("reason") or "unavailable"
        result["message"] = f"No recent log events ({reason})."
    return result


def admin_jobs_status_snapshot() -> dict[str, dict[str, Any]]:
    """Best-effort status map for every registered job (used by the dashboard)."""
    from meshflow.dna.web.admin.registry import registered_admin_jobs

    snapshot: dict[str, dict[str, Any]] = {}
    for job in registered_admin_jobs():
        try:
            snapshot[job.id] = admin_job_status(job.id)
        except Exception as exc:  # noqa: BLE001 — dashboard must stay up
            snapshot[job.id] = {
                "job_id": job.id,
                "state": "error",
                "message": str(exc),
            }
    return snapshot


def resolve_job_or_raise(job_id: str) -> AdminJob:
    job = get_admin_job(job_id)
    if job is None:
        raise UnknownAdminJob(job_id)
    return job
