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

_PIPELINE_STAGES: tuple[tuple[str, str], ...] = (
    ("parse", "Parse workbook"),
    ("profile", "Profile columns"),
    ("interpret", "Generate proposals"),
    ("ready", "Ready for review"),
)

_ACTIVE_STAGE_MESSAGES: dict[int, tuple[str, str]] = {
    0: ("Parsing workbook", "Reading sheets and detecting table regions."),
    1: ("Profiling columns", "Inferring types, keys, and column statistics."),
    2: ("Generating proposals", "Drafting schema proposals with Bedrock."),
}

_COMPLETED_STAGE_COUNT: dict[str, int] = {
    "uploaded": 0,
    "running": 0,
    "parsing": 0,
    "parsed": 1,
    "profiling": 1,
    "profiled": 2,
    "interpreting": 2,
    "ready": 4,
}

_ACTIVE_STAGE_INDEX: dict[str, int] = {
    "uploaded": 0,
    "running": 0,
    "parsing": 0,
    "parsed": 1,
    "profiling": 1,
    "profiled": 2,
    "interpreting": 2,
    "ready": -1,
}


def spreadsheet_pipeline_progress(
    job_status: str,
    *,
    execution_status: str = "",
    error: str = "",
) -> dict[str, Any]:
    status = str(job_status or "uploaded").strip().lower()
    execution = str(execution_status or "").strip().lower()
    err = str(error or "").strip()
    stages: list[dict[str, str]] = []
    complete = status == "ready"
    failed = status == "error" or execution in {"failed", "timed_out", "aborted"}

    if failed:
        active_index = max(_ACTIVE_STAGE_INDEX.get(status, 0), 0)
        for index, (key, label) in enumerate(_PIPELINE_STAGES):
            if index < active_index:
                state = "complete"
            elif index == active_index:
                state = "error"
            else:
                state = "pending"
            stages.append({"key": key, "label": label, "state": state})
        label, detail = "Analysis failed", err or "The Step Functions workflow did not complete successfully."
        return {
            "job_status": status,
            "execution_status": execution,
            "status_label": label,
            "status_detail": detail,
            "error": err,
            "stages": stages,
            "complete": False,
            "failed": True,
        }

    if complete:
        for key, label in _PIPELINE_STAGES:
            stages.append({"key": key, "label": label, "state": "complete"})
        return {
            "job_status": status,
            "execution_status": execution or "succeeded",
            "status_label": "Proposals ready",
            "status_detail": "Review proposed schemas below.",
            "error": "",
            "stages": stages,
            "complete": True,
            "failed": False,
        }

    completed_count = _COMPLETED_STAGE_COUNT.get(status, 0)
    active_index = _ACTIVE_STAGE_INDEX.get(status, 0)
    for index, (key, label) in enumerate(_PIPELINE_STAGES):
        if index < completed_count:
            state = "complete"
        elif index == active_index:
            state = "active"
        else:
            state = "pending"
        stages.append({"key": key, "label": label, "state": state})

    if status in {"uploaded", "running"} and execution in {"", "running"}:
        label = "Starting analysis"
        detail = "Waiting for the Step Functions workflow to begin."
    elif active_index >= 0:
        label, detail = _ACTIVE_STAGE_MESSAGES.get(
            active_index,
            ("Analyzing workbook", "Running spreadsheet analysis pipeline."),
        )
    else:
        label, detail = "Analyzing workbook", "Running spreadsheet analysis pipeline."

    if execution == "running":
        detail = f"{detail} Step Functions status: RUNNING."

    return {
        "job_status": status,
        "execution_status": execution,
        "status_label": label,
        "status_detail": detail,
        "error": "",
        "stages": stages,
        "complete": False,
        "failed": False,
    }


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
        os.environ["MESHFLOW_S3_BUCKET"] = settings.s3_bucket
    if settings.data_dir:
        os.environ["MESHFLOW_DATA_DIR"] = str(settings.data_dir)


def load_job_report(settings: DnaSettings, *, job_id: str) -> dict[str, Any] | None:
    from meshflow.spreadsheet.jobs import load_report

    _configure_jobs_env(settings)
    return load_report(job_id)


def load_table_preview_data(
    settings: DnaSettings,
    *,
    job_id: str,
    table_id: str,
    max_rows: int = 100,
) -> dict[str, Any] | None:
    from meshflow.spreadsheet.jobs import load_table_preview

    _configure_jobs_env(settings)
    if not job_id.strip() or not table_id.strip():
        return None
    return load_table_preview(job_id.strip(), table_id.strip(), max_rows=max_rows)


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
        report = load_report(job_id)
        return {
            "status": "missing",
            "job_id": job_id,
            "job": None,
            "report": report,
            "table_count": (report or {}).get("table_count", 0),
            "execution_arn": "",
            "execution_status": "",
            "pipeline": spreadsheet_pipeline_progress(
                "ready" if report and report.get("tables") else "error",
                error="" if report and report.get("tables") else "Workbook job not found.",
            ),
        }
    execution_arn = str(job.get("execution_arn") or "")
    execution_status = ""
    execution_error = ""
    if execution_arn:
        import boto3

        region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-2"
        client = boto3.client("stepfunctions", region_name=region)
        try:
            execution = client.describe_execution(executionArn=execution_arn)
            sf_status = str(execution.get("status") or "")
            execution_status = sf_status.strip().lower()
            changed = False
            if sf_status == "SUCCEEDED":
                pass
            elif sf_status in {"FAILED", "TIMED_OUT", "ABORTED"}:
                execution_error = str(execution.get("cause") or execution.get("error") or sf_status)
                if str(job.get("status") or "") != "error" or job.get("error") != execution_error:
                    job["status"] = "error"
                    job["error"] = execution_error
                    changed = True
            elif str(job.get("status") or "") in {"", "uploaded"}:
                job["status"] = "running"
                changed = True
            if changed:
                save_job(job)
        except Exception:  # noqa: BLE001
            pass
    report = load_report(job_id)
    if report and report.get("tables") and str(job.get("status") or "") not in {"error"}:
        if str(job.get("status") or "") != "ready":
            job["status"] = "ready"
            save_job(job)
    elif execution_status == "succeeded" and str(job.get("status") or "") not in {"error", "ready"}:
        job["status"] = "ready"
        save_job(job)
    job_status_value = str(job.get("status") or "")
    pipeline = spreadsheet_pipeline_progress(
        job_status_value,
        execution_status=execution_status,
        error=str(job.get("error") or execution_error or ""),
    )
    return {
        "status": job_status_value,
        "job_id": job_id,
        "job": job,
        "report": report,
        "table_count": (report or {}).get("table_count", 0),
        "execution_arn": execution_arn,
        "execution_status": execution_status,
        "pipeline": pipeline,
    }


def list_catalog_entries(settings: DnaSettings, *, limit: int = 100) -> list[dict[str, Any]]:
    from meshflow.spreadsheet.jobs import list_catalog_entries as _list

    _configure_jobs_env(settings)
    return _list(limit=limit)


def load_catalog_entry(settings: DnaSettings, *, catalog_id: str) -> dict[str, Any] | None:
    from meshflow.spreadsheet.jobs import load_catalog_entry as _load

    _configure_jobs_env(settings)
    return _load(catalog_id)


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
    from meshflow.spreadsheet.jobs import (
        append_table_chat,
        load_report,
        load_table,
        update_table_proposal,
    )

    _configure_jobs_env(settings)
    text = message.strip()
    if not text:
        raise ValueError("message is required")
    if not table_id.strip():
        raise ValueError("table_id is required to refine a proposal")

    table_id = table_id.strip()
    append_table_chat(job_id, table_id, role="user", text=text)

    report = load_report(job_id) or {}
    tables = report.get("tables") or []
    focus = load_table(job_id, table_id)
    context = {
        "job_id": job_id,
        "user_message": text,
        "focus_table": focus,
        "other_tables": [t for t in tables if str(t.get("table_id")) != table_id],
    }
    system = (
        "You help refine one spreadsheet table schema proposal at a time. "
        "Only update the focused table unless the user explicitly asks about others. "
        "Return JSON: {\"assistant_reply\": \"...\", \"table_updates\": "
        "[{\"table_id\":\"t0\",\"entity_name\":\"...\",\"purpose\":\"...\","
        "\"grain\":\"...\",\"schema\":[...],\"notes\":[\"...\"]}]}"
    )
    reply = "Updated this table proposal based on your feedback."
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
    append_table_chat(job_id, table_id, role="assistant", text=reply)
    return {"reply": reply, "report": load_report(job_id), "table": load_table(job_id, table_id)}


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
