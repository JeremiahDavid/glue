"""Invoke and monitor registered platform admin jobs."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from hiveflow.compat import UTC
from typing import Any
from urllib.parse import quote

from hiveflow.dna.web.admin.registry import AdminJob, get_admin_job


class UnknownAdminJob(Exception):
    def __init__(self, job_id: str) -> None:
        self.job_id = job_id
        super().__init__(f"Unknown admin job: {job_id}")


class AdminJobMisconfigured(Exception):
    def __init__(self, job_id: str, reason: str) -> None:
        self.job_id = job_id
        self.reason = reason
        super().__init__(f"Admin job {job_id} misconfigured: {reason}")


_START_RE = re.compile(r"^START RequestId:\s*([0-9a-fA-F-]+)")
_END_RE = re.compile(r"^END RequestId:\s*([0-9a-fA-F-]+)")
_REPORT_RE = re.compile(
    r"^REPORT RequestId:\s*([0-9a-fA-F-]+)\s+Duration:\s*([\d.]+)\s*ms",
    re.IGNORECASE,
)


def _region() -> str:
    return (
        os.environ.get("AWS_REGION")
        or os.environ.get("AWS_DEFAULT_REGION")
        or "us-east-2"
    )


def _on_lambda() -> bool:
    return bool(os.environ.get("AWS_LAMBDA_FUNCTION_NAME", "").strip())


def lambda_console_url(function_name: str) -> str:
    """AWS console deep-link for a Lambda function."""
    region = _region()
    encoded = quote(function_name, safe="")
    return (
        f"https://{region}.console.aws.amazon.com/lambda/home"
        f"?region={region}#/functions/{encoded}"
    )


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
            "console_url": lambda_console_url(function_name),
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
        "console_url": lambda_console_url(function_name),
    }


def _parse_json_log(message: str) -> dict[str, Any] | None:
    text = message.strip()
    if not text.startswith("{"):
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _human_duration(duration_ms: float | None) -> str:
    if duration_ms is None:
        return ""
    seconds = duration_ms / 1000.0
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = int(seconds // 60)
    rem = seconds - (minutes * 60)
    return f"{minutes}m {rem:.0f}s"


def _infer_run_from_messages(messages: list[str]) -> dict[str, Any]:
    """Derive run state from recent CloudWatch log lines (oldest → newest)."""
    last_start: str | None = None
    last_end: str | None = None
    duration_ms: float | None = None
    handler_start = False
    handler_done: dict[str, Any] | None = None
    failed = False
    failure_reason = ""

    for message in messages:
        start_match = _START_RE.match(message)
        if start_match:
            last_start = start_match.group(1)
            last_end = None
            duration_ms = None
            handler_start = False
            handler_done = None
            failed = False
            failure_reason = ""
            continue

        end_match = _END_RE.match(message)
        if end_match:
            last_end = end_match.group(1)
            continue

        report_match = _REPORT_RE.match(message)
        if report_match:
            last_end = report_match.group(1)
            try:
                duration_ms = float(report_match.group(2))
            except ValueError:
                duration_ms = None
            if "Status: error" in message or "Task timed out" in message:
                failed = True
                failure_reason = "Lambda reported an error"
            continue

        payload = _parse_json_log(message)
        if payload is not None:
            msg = str(payload.get("msg") or "")
            if msg.endswith("_start"):
                handler_start = True
            elif msg.endswith("_done") or msg.endswith("_published"):
                handler_done = payload
                result = payload.get("result") if isinstance(payload.get("result"), dict) else payload
                status = str(result.get("status") or "").strip().lower()
                if status in {"failed", "error"}:
                    failed = True
                    failure_reason = status or "handler reported failure"
            continue

        lowered = message.lower()
        if (
            "traceback (most recent call last)" in lowered
            or message.startswith("[ERROR]")
            or "task timed out after" in lowered
            or "runtime.exiterror" in lowered
        ):
            failed = True
            failure_reason = message[:160]

    if not last_start and not handler_start and not handler_done:
        return {
            "available": True,
            "run_state": "idle",
            "summary": "No recent invocations",
        }

    in_flight = bool(last_start) and (last_end is None or last_end != last_start)
    if in_flight and not failed:
        return {
            "available": True,
            "run_state": "running",
            "request_id": last_start,
            "summary": "Running",
        }

    if failed:
        return {
            "available": True,
            "run_state": "failed",
            "request_id": last_start or last_end,
            "duration_ms": duration_ms,
            "summary": failure_reason or "Failed",
        }

    result_status = ""
    if handler_done is not None:
        result = (
            handler_done.get("result")
            if isinstance(handler_done.get("result"), dict)
            else handler_done
        )
        result_status = str(result.get("status") or "").strip().lower()

    duration_label = _human_duration(duration_ms)
    if result_status:
        summary = f"Completed ({result_status})"
    else:
        summary = "Completed"
    if duration_label:
        summary = f"{summary} · {duration_label}"

    return {
        "available": True,
        "run_state": "completed",
        "request_id": last_end or last_start,
        "duration_ms": duration_ms,
        "result_status": result_status or None,
        "summary": summary,
    }


def _recent_run_status(function_name: str) -> dict[str, Any]:
    """Best-effort last-run status from the newest CloudWatch log stream."""
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
            return {"available": False, "reason": code, "run_state": "unknown"}
        return {
            "available": False,
            "reason": "describe_failed",
            "error": str(exc),
            "run_state": "unknown",
        }

    stream_list = streams.get("logStreams") or []
    if not stream_list:
        return {"available": False, "reason": "no_streams", "run_state": "idle"}

    stream_name = str(stream_list[0].get("logStreamName") or "")
    if not stream_name:
        return {"available": False, "reason": "empty_stream", "run_state": "idle"}

    try:
        events_response = logs.get_log_events(
            logGroupName=log_group,
            logStreamName=stream_name,
            limit=80,
            startFromHead=False,
        )
    except ClientError as exc:
        return {
            "available": False,
            "reason": "get_events_failed",
            "error": str(exc),
            "run_state": "unknown",
            "stream": stream_name,
        }

    messages = [
        str(event.get("message") or "").strip()
        for event in (events_response.get("events") or [])
        if str(event.get("message") or "").strip()
    ]
    if not messages:
        return {
            "available": False,
            "reason": "no_events",
            "run_state": "idle",
            "stream": stream_name,
        }

    inferred = _infer_run_from_messages(messages)
    inferred["stream"] = stream_name
    inferred["event_count"] = len(messages)
    return inferred


def admin_job_status(job_id: str) -> dict[str, Any]:
    """Return run state derived from recent Lambda logs (+ console link)."""
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
        "console_url": lambda_console_url(function_name),
        "checked_at": datetime.now(UTC).isoformat(),
    }

    if not _on_lambda():
        result.update(
            {
                "state": "local",
                "run_state": "local",
                "summary": "Status checks require the admin Lambda runtime.",
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
                "run_state": "unknown",
                "summary": str(exc),
                "logs": {"available": False, "reason": "get_function_failed"},
            }
        )
        return result

    result.update(
        {
            "lambda_state": str(config.get("State") or "Unknown"),
            "last_update_status": str(config.get("LastUpdateStatus") or ""),
            "last_modified": str(config.get("LastModified") or ""),
            "timeout": config.get("Timeout"),
            "memory_size": config.get("MemorySize"),
        }
    )
    logs = _recent_run_status(function_name)
    result["logs"] = logs
    run_state = str(logs.get("run_state") or "unknown")
    result["run_state"] = run_state
    result["state"] = run_state
    result["summary"] = str(logs.get("summary") or "")
    if logs.get("duration_ms") is not None:
        result["duration_ms"] = logs.get("duration_ms")
    if logs.get("request_id"):
        result["request_id"] = logs.get("request_id")
    if logs.get("result_status"):
        result["result_status"] = logs.get("result_status")
    return result


def admin_jobs_status_snapshot() -> dict[str, dict[str, Any]]:
    """Best-effort status map for every registered job (used by the dashboard)."""
    from hiveflow.dna.web.admin.registry import registered_admin_jobs

    snapshot: dict[str, dict[str, Any]] = {}
    for job in registered_admin_jobs():
        try:
            snapshot[job.id] = admin_job_status(job.id)
        except Exception as exc:  # noqa: BLE001 — dashboard must stay up
            snapshot[job.id] = {
                "job_id": job.id,
                "state": "error",
                "run_state": "error",
                "summary": str(exc),
            }
    return snapshot


def resolve_job_or_raise(job_id: str) -> AdminJob:
    job = get_admin_job(job_id)
    if job is None:
        raise UnknownAdminJob(job_id)
    return job
