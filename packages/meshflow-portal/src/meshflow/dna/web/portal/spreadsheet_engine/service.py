"""Spreadsheet Engine portal service — uploads, pipeline kickoff, chat, approvals."""

from __future__ import annotations

import json
import os
from typing import Any

from meshflow.dna.settings import DnaSettings
from meshflow.dna.web.portal.governance_helpers.bedrock_usage import (
    BedrockBudgetExceeded,
    usage_summary,
)
from meshflow.process_config import Process, step_function_name_for_process


def _on_lambda() -> bool:
    return bool(os.environ.get("AWS_LAMBDA_FUNCTION_NAME", "").strip())


def _state_machine_arn(*, company: str, environment: str) -> str:
    explicit = os.getenv("MESHFLOW_SPREADSHEET_STATE_MACHINE_ARN", "").strip()
    if explicit:
        return explicit
    name = step_function_name_for_process(company, environment, "all", Process.SPREADSHEET_ANALYZE)
    region = (
        os.getenv("AWS_REGION")
        or os.getenv("AWS_DEFAULT_REGION")
        or os.getenv("MESHFLOW_AWS_REGION")
        or "us-east-2"
    )
    import boto3

    account = boto3.client("sts").get_caller_identity()["Account"]
    return f"arn:aws:states:{region}:{account}:stateMachine:{name}"


def _configure_jobs_env(settings: DnaSettings) -> None:
    if settings.s3_bucket:
        os.environ.setdefault("MESHFLOW_S3_BUCKET", settings.s3_bucket)
    if settings.data_dir:
        os.environ.setdefault("MESHFLOW_DATA_DIR", str(settings.data_dir))


def start_upload(
    settings: DnaSettings,
    *,
    filename: str,
    body: bytes,
    username: str = "",
) -> dict[str, Any]:
    from meshflow.spreadsheet.jobs import create_job, store_upload

    _configure_jobs_env(settings)
    job = create_job(filename=filename, username=username)
    store_upload(job["job_id"], filename=filename, body=body)
    return job


def enqueue_analysis(
    settings: DnaSettings,
    *,
    job_id: str,
    company: str,
    environment: str,
) -> dict[str, Any]:
    from meshflow.spreadsheet.jobs import load_job, run_pipeline, save_job

    _configure_jobs_env(settings)
    job = load_job(job_id)
    if not job:
        raise ValueError(f"Unknown job {job_id!r}")

    payload = {"job_id": job_id}
    if _on_lambda():
        import boto3

        region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-2"
        client = boto3.client("stepfunctions", region_name=region)
        response = client.start_execution(
            stateMachineArn=_state_machine_arn(company=company, environment=environment),
            input=json.dumps(payload),
        )
        job["status"] = "running"
        job["execution_arn"] = response.get("executionArn", "")
        save_job(job)
        return {
            "status": "enqueued",
            "job_id": job_id,
            "execution_arn": job.get("execution_arn"),
        }

    job = run_pipeline(job_id)
    return {"status": job.get("status", "ready"), "job_id": job_id, "job": job}


def job_status(
    settings: DnaSettings,
    *,
    job_id: str,
    company: str,
    environment: str,
) -> dict[str, Any]:
    from meshflow.spreadsheet.jobs import load_job, load_report, save_job

    _configure_jobs_env(settings)
    job = load_job(job_id)
    if not job:
        return {"status": "missing", "job_id": job_id}
    execution_arn = str(job.get("execution_arn") or "")
    if execution_arn and job.get("status") not in {"ready", "error"}:
        import boto3

        region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-2"
        client = boto3.client("stepfunctions", region_name=region)
        try:
            execution = client.describe_execution(executionArn=execution_arn)
            sf_status = str(execution.get("status") or "")
            if sf_status == "SUCCEEDED":
                job["status"] = "ready"
            elif sf_status in {"FAILED", "TIMED_OUT", "ABORTED"}:
                job["status"] = "error"
                job["error"] = str(execution.get("cause") or execution.get("error") or sf_status)
            save_job(job)
        except Exception:  # noqa: BLE001
            pass
    report = load_report(job_id)
    return {
        "status": job.get("status"),
        "job_id": job_id,
        "job": job,
        "report": report,
        "table_count": (report or {}).get("table_count", 0),
    }


def list_recent_jobs(settings: DnaSettings, *, limit: int = 10) -> list[dict[str, Any]]:
    from meshflow.spreadsheet.jobs import list_jobs

    _configure_jobs_env(settings)
    return list_jobs(limit=limit)


def approve_table(
    settings: DnaSettings,
    *,
    job_id: str,
    table_id: str,
    username: str = "",
) -> dict[str, Any]:
    from meshflow.spreadsheet.jobs import approve_table as _approve

    _configure_jobs_env(settings)
    return _approve(job_id, table_id, username=username)


def chat_feedback(
    settings: DnaSettings,
    *,
    job_id: str,
    message: str,
    table_id: str = "",
    client_id: str = "",
    monthly_budget_usd: float | None = None,
) -> dict[str, Any]:
    from meshflow.spreadsheet.interpret import _default_invoke, _extract_json
    from meshflow.spreadsheet.jobs import append_chat, load_job, load_report, load_table, update_table_proposal

    _configure_jobs_env(settings)
    text = message.strip()
    if not text:
        raise ValueError("message is required")
    append_chat(job_id, role="user", text=text)

    report = load_report(job_id) or {}
    tables = report.get("tables") or []
    focus = load_table(job_id, table_id) if table_id else None
    context = {
        "job_id": job_id,
        "user_message": text,
        "tables": tables,
        "focus_table": focus,
    }
    system = (
        "You help refine spreadsheet table schema proposals. "
        "Return JSON: {\"assistant_reply\": \"...\", \"table_updates\": "
        "[{\"table_id\":\"t0\",\"entity_name\":\"...\",\"purpose\":\"...\","
        "\"grain\":\"...\",\"schema\":[...],\"notes\":[\"...\"]}]}"
    )
    reply = "Updated the proposal based on your feedback."
    try:
        raw = _default_invoke(system, json.dumps(context, default=str))
        parsed = _extract_json(raw)
        reply = str(parsed.get("assistant_reply") or reply)
        updates = parsed.get("table_updates") or []
        if isinstance(updates, list):
            for item in updates:
                if not isinstance(item, dict):
                    continue
                tid = str(item.get("table_id") or "")
                if tid:
                    update_table_proposal(job_id, tid, item)
    except BedrockBudgetExceeded:
        raise
    except Exception as exc:  # noqa: BLE001
        reply = f"I could not apply that change automatically ({exc}). Try rephrasing your feedback."
    append_chat(job_id, role="assistant", text=reply)
    return {"reply": reply, "job": load_job(job_id), "report": load_report(job_id)}


def bedrock_usage_for_client(
    settings: DnaSettings,
    *,
    client_id: str,
    monthly_budget_usd: float | None,
) -> dict[str, Any]:
    return usage_summary(
        settings,
        client_id=client_id,
        monthly_budget_usd=monthly_budget_usd,
    ).to_dict()
