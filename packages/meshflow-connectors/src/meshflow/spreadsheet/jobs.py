"""Spreadsheet Engine job persistence and orchestration."""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from datetime import datetime
from meshflow.compat import UTC
from pathlib import Path
from typing import Any

from meshflow.spreadsheet.interpret import interpret_tables
from meshflow.spreadsheet.parser import parse_workbook
from meshflow.spreadsheet.profiler import profile_tables
from meshflow.storage.paths import (
    prefix_path,
    spreadsheet_engine_job_key,
    spreadsheet_engine_job_parse_key,
    spreadsheet_engine_jobs_prefix,
    spreadsheet_engine_job_profile_key,
    spreadsheet_engine_job_report_key,
    spreadsheet_engine_job_table_key,
    spreadsheet_engine_job_upload_key,
)

JOB_KIND = "spreadsheet_engine_job"
TERMINAL_STATUSES = frozenset({"ready", "error"})


def new_job_id() -> str:
    return uuid.uuid4().hex


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _bucket() -> str:
    return os.getenv("MESHFLOW_S3_BUCKET", "").strip()


def _data_dir() -> Path:
    return Path(os.getenv("MESHFLOW_DATA_DIR", "data")).resolve()


def _write_json(key: str, payload: dict[str, Any]) -> str:
    body = json.dumps(payload, indent=2, default=str).encode("utf-8")
    bucket = _bucket()
    if bucket:
        import boto3

        boto3.client("s3").put_object(
            Bucket=bucket,
            Key=key,
            Body=body,
            ContentType="application/json",
        )
        return f"s3://{bucket}/{key}"
    path = prefix_path(_data_dir(), key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return str(path)


def _read_json(key: str) -> dict[str, Any] | None:
    bucket = _bucket()
    if bucket:
        import boto3

        client = boto3.client("s3")
        try:
            response = client.get_object(Bucket=bucket, Key=key)
        except client.exceptions.NoSuchKey:
            return None
        except Exception as exc:  # noqa: BLE001
            if exc.__class__.__name__ == "NoSuchKey":
                return None
            raise
        payload = json.loads(response["Body"].read().decode("utf-8"))
        return payload if isinstance(payload, dict) else None
    path = prefix_path(_data_dir(), key)
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _write_bytes(key: str, body: bytes, *, content_type: str) -> str:
    bucket = _bucket()
    if bucket:
        import boto3

        boto3.client("s3").put_object(
            Bucket=bucket,
            Key=key,
            Body=body,
            ContentType=content_type,
        )
        return f"s3://{bucket}/{key}"
    path = prefix_path(_data_dir(), key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return str(path)


def _read_bytes(key: str) -> bytes:
    bucket = _bucket()
    if bucket:
        import boto3

        response = boto3.client("s3").get_object(Bucket=bucket, Key=key)
        return response["Body"].read()
    path = prefix_path(_data_dir(), key)
    return path.read_bytes()


def save_job(job: dict[str, Any]) -> dict[str, Any]:
    job_id = str(job.get("job_id") or "").strip()
    if not job_id:
        raise ValueError("job_id is required")
    job["updated_at"] = _now_iso()
    _write_json(spreadsheet_engine_job_key(job_id), job)
    return job


def load_job(job_id: str) -> dict[str, Any] | None:
    return _read_json(spreadsheet_engine_job_key(job_id))


def create_job(*, filename: str, username: str = "") -> dict[str, Any]:
    job_id = new_job_id()
    now = _now_iso()
    job = {
        "kind": JOB_KIND,
        "job_id": job_id,
        "status": "uploaded",
        "filename": filename,
        "created_at": now,
        "updated_at": now,
        "created_by": username,
        "chat_history": [],
        "table_ids": [],
        "execution_arn": "",
        "error": "",
    }
    return save_job(job)


def store_upload(job_id: str, *, filename: str, body: bytes) -> str:
    key = spreadsheet_engine_job_upload_key(job_id, filename)
    content_type = (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        if filename.lower().endswith(".xlsx")
        else "application/octet-stream"
    )
    location = _write_bytes(key, body, content_type=content_type)
    job = load_job(job_id) or {}
    job["upload_key"] = key
    job["filename"] = filename
    job["status"] = "uploaded"
    save_job(job)
    return location


def _local_upload_path(job_id: str, filename: str) -> Path:
    key = spreadsheet_engine_job_upload_key(job_id, filename)
    return prefix_path(_data_dir(), key)


def run_parse(job_id: str) -> dict[str, Any]:
    job = load_job(job_id)
    if not job:
        raise ValueError(f"Unknown job {job_id!r}")
    filename = str(job.get("filename") or "workbook.xlsx")
    upload_key = str(job.get("upload_key") or spreadsheet_engine_job_upload_key(job_id, filename))
    job["status"] = "parsing"
    save_job(job)

    with tempfile.TemporaryDirectory() as tmp:
        local_path = Path(tmp) / filename
        local_path.write_bytes(_read_bytes(upload_key))
        parse_payload = parse_workbook(local_path, filename=filename)
    parse_payload["job_id"] = job_id
    _write_json(spreadsheet_engine_job_parse_key(job_id), parse_payload)

    job = load_job(job_id) or job
    job["status"] = "parsed"
    job["parse_key"] = spreadsheet_engine_job_parse_key(job_id)
    job["table_ids"] = [str(t.get("table_id")) for t in parse_payload.get("tables") or []]
    return save_job(job)


def run_profile(job_id: str) -> dict[str, Any]:
    job = load_job(job_id) or {}
    job["status"] = "profiling"
    save_job(job)
    parse_payload = _read_json(spreadsheet_engine_job_parse_key(job_id))
    if not parse_payload:
        raise ValueError(f"Missing parse output for job {job_id!r}")
    profile_payload = profile_tables(parse_payload)
    profile_payload["job_id"] = job_id
    _write_json(spreadsheet_engine_job_profile_key(job_id), profile_payload)

    job = load_job(job_id) or job
    job["status"] = "profiled"
    job["profile_key"] = spreadsheet_engine_job_profile_key(job_id)
    return save_job(job)


def run_interpret(job_id: str) -> dict[str, Any]:
    job = load_job(job_id) or {}
    job["status"] = "interpreting"
    save_job(job)
    parse_payload = _read_json(spreadsheet_engine_job_parse_key(job_id))
    profile_payload = _read_json(spreadsheet_engine_job_profile_key(job_id))
    if not parse_payload or not profile_payload:
        raise ValueError(f"Missing parse/profile output for job {job_id!r}")
    report = interpret_tables(parse_payload, profile_payload)
    report["job_id"] = job_id
    _write_json(spreadsheet_engine_job_report_key(job_id), report)
    for table in report.get("tables") or []:
        if not isinstance(table, dict):
            continue
        table_id = str(table.get("table_id") or "")
        if table_id:
            _write_json(spreadsheet_engine_job_table_key(job_id, table_id), table)

    job = load_job(job_id) or job
    job["status"] = "ready"
    job["report_key"] = spreadsheet_engine_job_report_key(job_id)
    job["table_count"] = report.get("table_count", 0)
    return save_job(job)


def run_pipeline(job_id: str) -> dict[str, Any]:
    try:
        run_parse(job_id)
        run_profile(job_id)
        return run_interpret(job_id)
    except Exception as exc:  # noqa: BLE001
        job = load_job(job_id) or {"job_id": job_id, "kind": JOB_KIND}
        job["status"] = "error"
        job["error"] = str(exc)
        return save_job(job)


def load_report(job_id: str) -> dict[str, Any] | None:
    return _read_json(spreadsheet_engine_job_report_key(job_id))


def load_table(job_id: str, table_id: str) -> dict[str, Any] | None:
    return _read_json(spreadsheet_engine_job_table_key(job_id, table_id))


def list_jobs(limit: int = 20) -> list[dict[str, Any]]:
    bucket = _bucket()
    jobs: list[dict[str, Any]] = []
    if bucket:
        import boto3

        client = boto3.client("s3")
        paginator = client.get_paginator("list_objects_v2")
        keys: list[str] = []
        for page in paginator.paginate(Bucket=bucket, Prefix=f"{spreadsheet_engine_jobs_prefix()}/"):
            for item in page.get("Contents") or []:
                key = str(item.get("Key") or "")
                if key.endswith("/job.json"):
                    keys.append(key)
        keys.sort(reverse=True)
        for key in keys[:limit]:
            payload = _read_json(key)
            if payload:
                jobs.append(payload)
        return jobs

    root = prefix_path(_data_dir(), spreadsheet_engine_jobs_prefix())
    if not root.exists():
        return []
    for job_dir in sorted(root.iterdir(), reverse=True):
        if not job_dir.is_dir():
            continue
        job_file = job_dir / "job.json"
        if job_file.exists():
            payload = json.loads(job_file.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                jobs.append(payload)
        if len(jobs) >= limit:
            break
    return jobs


def update_table_proposal(job_id: str, table_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    table = load_table(job_id, table_id)
    if not table:
        raise ValueError(f"Unknown table {table_id!r} for job {job_id!r}")
    merged = {**table, **updates, "status": updates.get("status", table.get("status", "pending_review"))}
    _write_json(spreadsheet_engine_job_table_key(job_id, table_id), merged)
    report = load_report(job_id) or {"tables": []}
    tables = []
    for item in report.get("tables") or []:
        if str(item.get("table_id")) == table_id:
            tables.append(merged)
        else:
            tables.append(item)
    report["tables"] = tables
    _write_json(spreadsheet_engine_job_report_key(job_id), report)
    return merged


def update_report_tables(job_id: str, tables: list[dict[str, Any]]) -> dict[str, Any]:
    report = load_report(job_id) or {"kind": "spreadsheet_engine_report", "tables": []}
    report["tables"] = tables
    report["table_count"] = len(tables)
    _write_json(spreadsheet_engine_job_report_key(job_id), report)
    for table in tables:
        table_id = str(table.get("table_id") or "")
        if table_id:
            _write_json(spreadsheet_engine_job_table_key(job_id, table_id), table)
    return report


def approve_table(job_id: str, table_id: str, *, username: str = "") -> dict[str, Any]:
    table = load_table(job_id, table_id)
    if not table:
        raise ValueError(f"Unknown table {table_id!r} for job {job_id!r}")
    table["status"] = "approved"
    table["approved_at"] = _now_iso()
    table["approved_by"] = username
    _write_json(spreadsheet_engine_job_table_key(job_id, table_id), table)
    report = load_report(job_id) or {"tables": []}
    tables = []
    for item in report.get("tables") or []:
        if str(item.get("table_id")) == table_id:
            tables.append(table)
        else:
            tables.append(item)
    report["tables"] = tables
    _write_json(spreadsheet_engine_job_report_key(job_id), report)
    return table


def append_chat(job_id: str, *, role: str, text: str) -> dict[str, Any]:
    job = load_job(job_id)
    if not job:
        raise ValueError(f"Unknown job {job_id!r}")
    history = list(job.get("chat_history") or [])
    history.append({"role": role, "text": text, "at": _now_iso()})
    job["chat_history"] = history[-20:]
    return save_job(job)
