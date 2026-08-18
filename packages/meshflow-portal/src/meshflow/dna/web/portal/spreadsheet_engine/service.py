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
    ("propose", "Propose transformations"),
    ("ready", "Ready for review"),
)

_ACTIVE_STAGE_MESSAGES: dict[int, tuple[str, str]] = {
    0: ("Parsing workbook", "Reading sheets and detecting table regions."),
    1: ("Profiling columns", "Inferring types, keys, and column statistics."),
    2: ("Generating proposals", "Drafting schema proposals with Bedrock."),
    3: ("Proposing transformations", "Drafting transformation steps from knowledge base."),
}

_COMPLETED_STAGE_COUNT: dict[str, int] = {
    "uploaded": 0,
    "running": 0,
    "parsing": 0,
    "parsed": 1,
    "profiling": 1,
    "profiled": 2,
    "interpreting": 2,
    "interpreted": 3,
    "proposing": 3,
    "ready": 5,
}

_ACTIVE_STAGE_INDEX: dict[str, int] = {
    "uploaded": 0,
    "running": 0,
    "parsing": 0,
    "parsed": 1,
    "profiling": 1,
    "profiled": 2,
    "interpreting": 2,
    "interpreted": 3,
    "proposing": 3,
    "ready": -1,
}


_RELOAD_PIPELINE_STAGES: tuple[tuple[str, str], ...] = (
    ("parse", "Parse workbook"),
    ("profile", "Profile columns"),
    ("interpret", "Validate against catalog"),
    ("propose", "Finalize validation"),
    ("ready", "Ready for review"),
)

_RELOAD_ACTIVE_STAGE_MESSAGES: dict[int, tuple[str, str]] = {
    0: ("Parsing workbook", "Reading sheets and detecting table regions."),
    1: ("Profiling columns", "Inferring types and column statistics."),
    2: ("Validating reload", "Applying approved transformation and checking output schema."),
    3: ("Finalizing validation", "Preparing reload review — no AI calls."),
}


def spreadsheet_pipeline_progress(
    job_status: str,
    *,
    execution_status: str = "",
    error: str = "",
    reload_mode: bool = False,
) -> dict[str, Any]:
    pipeline_stages = _RELOAD_PIPELINE_STAGES if reload_mode else _PIPELINE_STAGES
    active_messages = _RELOAD_ACTIVE_STAGE_MESSAGES if reload_mode else _ACTIVE_STAGE_MESSAGES
    status = str(job_status or "uploaded").strip().lower()
    execution = str(execution_status or "").strip().lower()
    err = str(error or "").strip()
    stages: list[dict[str, str]] = []
    complete = status == "ready"
    failed = status == "error" or execution in {"failed", "timed_out", "aborted"}

    if failed:
        active_index = max(_ACTIVE_STAGE_INDEX.get(status, 0), 0)
        for index, (key, label) in enumerate(pipeline_stages):
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
        for key, label in pipeline_stages:
            stages.append({"key": key, "label": label, "state": "complete"})
        return {
            "job_status": status,
            "execution_status": execution or "succeeded",
            "status_label": "Reload validated" if reload_mode else "Proposals ready",
            "status_detail": (
                "Output matches the approved schema — complete the reload or review details."
                if reload_mode
                else "Review proposed schemas below."
            ),
            "error": "",
            "stages": stages,
            "complete": True,
            "failed": False,
        }

    completed_count = _COMPLETED_STAGE_COUNT.get(status, 0)
    active_index = _ACTIVE_STAGE_INDEX.get(status, 0)
    for index, (key, label) in enumerate(pipeline_stages):
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
        label, detail = active_messages.get(
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
    linked_catalog_id: str = "",
) -> dict[str, Any]:
    from meshflow.spreadsheet.jobs import create_job, store_upload

    _configure_jobs_env(settings)
    job = create_job(
        filename=filename,
        username=username,
        linked_catalog_id=linked_catalog_id,
    )
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
    reload_mode = bool((job or {}).get("reload_mode")) or bool((job or {}).get("reupload"))
    pipeline = spreadsheet_pipeline_progress(
        job_status_value,
        execution_status=execution_status,
        error=str(job.get("error") or execution_error or ""),
        reload_mode=reload_mode,
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


def load_transform_preview_data(
    settings: DnaSettings,
    *,
    job_id: str,
    table_id: str,
    max_rows: int = 25,
) -> dict[str, Any] | None:
    from meshflow.spreadsheet.jobs import load_transform_preview

    _configure_jobs_env(settings)
    if not job_id.strip() or not table_id.strip():
        return None
    return load_transform_preview(job_id.strip(), table_id.strip(), max_rows=max_rows)


def link_job_catalog(
    settings: DnaSettings,
    *,
    job_id: str,
    catalog_id: str,
) -> dict[str, Any]:
    from meshflow.spreadsheet.jobs import link_job_to_catalog

    _configure_jobs_env(settings)
    return link_job_to_catalog(job_id, catalog_id)


def suggest_catalog_matches(
    settings: DnaSettings,
    *,
    job_id: str,
) -> list[str]:
    from meshflow.spreadsheet.jobs import find_catalog_matches_for_parse, load_job
    from meshflow.storage.paths import spreadsheet_engine_job_parse_key

    _configure_jobs_env(settings)
    job = load_job(job_id)
    if not job:
        return []
    import json
    import os
    from pathlib import Path

    from meshflow.storage.paths import prefix_path

    parse_key = spreadsheet_engine_job_parse_key(job_id)
    parse_payload = None
    bucket = os.getenv("MESHFLOW_S3_BUCKET", "").strip()
    if bucket:
        import boto3

        try:
            response = boto3.client("s3").get_object(Bucket=bucket, Key=parse_key)
            parse_payload = json.loads(response["Body"].read().decode("utf-8"))
        except Exception:  # noqa: BLE001
            parse_payload = None
    else:
        data_dir = Path(os.getenv("MESHFLOW_DATA_DIR", "data")).resolve()
        path = prefix_path(data_dir, parse_key)
        if path.exists():
            parse_payload = json.loads(path.read_text(encoding="utf-8"))
    if not parse_payload:
        return list(job.get("suggested_catalog_ids") or [])
    return find_catalog_matches_for_parse(parse_payload)


def approve_transformation(
    settings: DnaSettings,
    *,
    job_id: str,
    table_id: str,
    username: str = "",
) -> dict[str, Any]:
    from meshflow.spreadsheet.jobs import approve_transformation as _approve

    _configure_jobs_env(settings)
    return _approve(job_id, table_id, username=username)


def reject_transformation(
    settings: DnaSettings,
    *,
    job_id: str,
    table_id: str,
    reason: str = "",
    username: str = "",
) -> dict[str, Any]:
    from meshflow.spreadsheet.jobs import reject_transformation as _reject

    _configure_jobs_env(settings)
    return _reject(job_id, table_id, reason=reason, username=username)


def edit_transformation(
    settings: DnaSettings,
    *,
    job_id: str,
    table_id: str,
    transformation: dict[str, Any],
) -> dict[str, Any]:
    from meshflow.spreadsheet.jobs import edit_transformation as _edit

    _configure_jobs_env(settings)
    return _edit(job_id, table_id, transformation)


def reupload_to_catalog(
    settings: DnaSettings,
    *,
    catalog_id: str,
    filename: str,
    body: bytes,
    username: str = "",
    company: str,
    environment: str,
) -> dict[str, Any]:
    job = start_upload(
        settings,
        filename=filename,
        body=body,
        username=username,
        linked_catalog_id=catalog_id,
    )
    result = enqueue_analysis(
        settings,
        job_id=job["job_id"],
        company=company,
        environment=environment,
    )
    return {"job": job, **result}


def complete_reload(
    settings: DnaSettings,
    *,
    job_id: str,
    table_id: str,
    username: str = "",
) -> dict[str, Any]:
    from meshflow.spreadsheet.jobs import complete_reload as _complete

    _configure_jobs_env(settings)
    return _complete(job_id, table_id, username=username)


def request_schema_rewrite(
    settings: DnaSettings,
    *,
    job_id: str,
    company: str,
    environment: str,
) -> dict[str, Any]:
    from meshflow.spreadsheet.jobs import request_schema_rewrite as _rewrite

    _configure_jobs_env(settings)
    job = _rewrite(job_id)
    return {"job": job, "job_id": job_id}


def request_transformation_rewrite(
    settings: DnaSettings,
    *,
    job_id: str,
    company: str,
    environment: str,
) -> dict[str, Any]:
    from meshflow.spreadsheet.jobs import request_transformation_rewrite as _rewrite

    _configure_jobs_env(settings)
    job = _rewrite(job_id)
    return {"job": job, "job_id": job_id}


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
        "\"grain\":\"...\",\"schema\":[...],\"transformation\":{...},\"notes\":[\"...\"]}]}"
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
                    if item.get("transformation"):
                        item["transformation_status"] = "pending_review"
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
