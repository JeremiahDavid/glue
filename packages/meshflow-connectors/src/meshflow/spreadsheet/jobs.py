"""Spreadsheet Engine job persistence and orchestration."""

from __future__ import annotations

import json
import os
import re
import tempfile
import uuid
from datetime import datetime
from meshflow.compat import UTC
from pathlib import Path
from typing import Any

from meshflow.spreadsheet.interpret import interpret_tables
from meshflow.spreadsheet.profiler import profile_tables
from meshflow.spreadsheet.propose import propose_transforms
from meshflow.spreadsheet.transform import (
    build_output_shape,
    compute_input_shape,
    preview_transformation,
    slugify_filename,
)
from meshflow.storage.paths import (
    prefix_path,
    spreadsheet_engine_catalog_entry_key,
    spreadsheet_engine_catalog_prefix,
    spreadsheet_engine_job_key,
    spreadsheet_engine_job_parse_key,
    spreadsheet_engine_job_prefix,
    spreadsheet_engine_jobs_prefix,
    spreadsheet_engine_job_profile_key,
    spreadsheet_engine_job_report_key,
    spreadsheet_engine_job_table_key,
    spreadsheet_engine_job_upload_key,
    spreadsheet_engine_knowledge_entry_key,
    spreadsheet_engine_knowledge_prefix,
)

JOB_KIND = "spreadsheet_engine_job"
CATALOG_ENTRY_KIND = "spreadsheet_engine_catalog_entry"
KNOWLEDGE_ENTRY_KIND = "spreadsheet_engine_knowledge"
TERMINAL_STATUSES = frozenset({"ready", "error"})
UPLOAD_HISTORY_LIMIT = 20


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


def create_job(
    *,
    filename: str,
    username: str = "",
    linked_catalog_id: str = "",
) -> dict[str, Any]:
    job_id = new_job_id()
    now = _now_iso()
    linked = str(linked_catalog_id or "").strip().lower()
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
        "linked_catalog_id": linked,
        "suggested_catalog_ids": [],
        "reupload": bool(linked),
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
        from meshflow.spreadsheet.parser import parse_workbook

        parse_payload = parse_workbook(local_path, filename=filename)
    parse_payload["job_id"] = job_id
    _write_json(spreadsheet_engine_job_parse_key(job_id), parse_payload)

    job = load_job(job_id) or job
    job["status"] = "parsed"
    job["parse_key"] = spreadsheet_engine_job_parse_key(job_id)
    job["table_ids"] = [str(t.get("table_id")) for t in parse_payload.get("tables") or []]
    if not str(job.get("linked_catalog_id") or "").strip():
        suggestions = find_catalog_matches_for_parse(parse_payload)
        job["suggested_catalog_ids"] = suggestions
    save_job(job)
    return job


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


def _is_reload_job(job: dict[str, Any] | None) -> bool:
    if not job:
        return False
    if not bool(job.get("reupload")):
        return False
    return bool(str(job.get("linked_catalog_id") or "").strip())


def run_reload_prepare(job_id: str) -> dict[str, Any]:
    """Build report from catalog for a linked re-upload — no AI."""
    job = load_job(job_id) or {}
    job["status"] = "interpreting"
    save_job(job)

    linked_id = str(job.get("linked_catalog_id") or "").strip().lower()
    catalog_entry = load_catalog_entry(linked_id)
    if not catalog_entry:
        raise ValueError(f"Unknown linked catalog entry {linked_id!r}")

    parse_payload = _read_json(spreadsheet_engine_job_parse_key(job_id))
    profile_payload = _read_json(spreadsheet_engine_job_profile_key(job_id))
    if not parse_payload or not profile_payload:
        raise ValueError(f"Missing parse/profile output for reload job {job_id!r}")

    parse_tables = {
        str(t.get("table_id")): t
        for t in (parse_payload.get("tables") or [])
        if isinstance(t, dict) and t.get("table_id")
    }
    profile_tables = {
        str(t.get("table_id")): t
        for t in (profile_payload.get("tables") or [])
        if isinstance(t, dict) and t.get("table_id")
    }

    if not parse_tables:
        raise ValueError(f"No tables detected in workbook for reload job {job_id!r}")

    catalog_table_id = str(catalog_entry.get("table_id") or "t0")
    table_id = catalog_table_id if catalog_table_id in parse_tables else next(iter(parse_tables), "t0")
    parse_table = parse_tables.get(table_id) or next(iter(parse_tables.values()), {})
    profile_table = profile_tables.get(table_id)

    from meshflow.spreadsheet.reload import build_reload_table_proposal, validate_reload_table

    headers = [str(h) for h in (parse_table.get("headers") or []) if str(h).strip()]
    preview = load_table_preview(job_id, table_id, max_rows=50) or {}
    sample_rows = list(preview.get("rows") or [])
    sample_headers = list(preview.get("headers") or headers)

    validation = validate_reload_table(
        parse_table=parse_table,
        profile_table=profile_table,
        catalog_entry=catalog_entry,
        sample_headers=sample_headers,
        sample_rows=sample_rows,
    )
    table = build_reload_table_proposal(
        table_id=table_id,
        parse_table=parse_table,
        profile_table=profile_table,
        catalog_entry=catalog_entry,
        validation=validation,
    )

    report = {
        "kind": "spreadsheet_engine_report",
        "job_id": job_id,
        "filename": parse_payload.get("filename") or job.get("filename"),
        "table_count": 1,
        "tables": [table],
        "reload_mode": True,
    }
    _write_json(spreadsheet_engine_job_report_key(job_id), report)
    _write_json(spreadsheet_engine_job_table_key(job_id, table_id), table)

    job = load_job(job_id) or job
    job["status"] = "interpreted"
    job["reload_mode"] = True
    job["reload_validation_status"] = validation.get("reload_validation_status")
    job["report_key"] = spreadsheet_engine_job_report_key(job_id)
    job["table_count"] = 1
    job["table_ids"] = [table_id]
    return save_job(job)


def run_interpret(job_id: str, *, force_ai: bool = False) -> dict[str, Any]:
    job = load_job(job_id) or {}
    if _is_reload_job(job) and not force_ai:
        return run_reload_prepare(job_id)

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
    job["status"] = "interpreted"
    job["report_key"] = spreadsheet_engine_job_report_key(job_id)
    job["table_count"] = report.get("table_count", 0)
    return save_job(job)


def run_reload_finalize(job_id: str) -> dict[str, Any]:
    """Mark reload job ready after validation — no AI, no catalog write until user confirms."""
    job = load_job(job_id) or {}
    job["status"] = "proposing"
    save_job(job)

    report = load_report(job_id)
    if not report:
        raise ValueError(f"Missing report for reload job {job_id!r}")

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


def run_propose(job_id: str, *, force_ai: bool = False) -> dict[str, Any]:
    job = load_job(job_id) or {}
    if _is_reload_job(job) and not force_ai:
        return run_reload_finalize(job_id)

    job["status"] = "proposing"
    save_job(job)
    parse_payload = _read_json(spreadsheet_engine_job_parse_key(job_id))
    profile_payload = _read_json(spreadsheet_engine_job_profile_key(job_id))
    report = load_report(job_id)
    if not parse_payload or not profile_payload or not report:
        raise ValueError(f"Missing parse/profile/report for job {job_id!r}")

    linked_catalog = None
    linked_id = str(job.get("linked_catalog_id") or "").strip().lower()
    if linked_id:
        linked_catalog = load_catalog_entry(linked_id)

    knowledge_entries: list[dict[str, Any]] = []
    for table in parse_payload.get("tables") or []:
        if not isinstance(table, dict):
            continue
        input_shape = compute_input_shape(table)
        knowledge_entries.extend(load_knowledge_matches(shape_hash=input_shape.get("shape_hash") or ""))

    report = propose_transforms(
        parse_payload,
        profile_payload,
        report,
        linked_catalog=linked_catalog,
        knowledge_entries=knowledge_entries,
    )
    report["job_id"] = job_id
    _write_json(spreadsheet_engine_job_report_key(job_id), report)
    for table in report.get("tables") or []:
        if not isinstance(table, dict):
            continue
        table_id = str(table.get("table_id") or "")
        if table_id:
            _write_json(spreadsheet_engine_job_table_key(job_id, table_id), table)

    if linked_catalog:
        record_upload_on_catalog(
            linked_id,
            job_id=job_id,
            uploaded_by=str(job.get("created_by") or ""),
            input_shape_hash=_first_shape_hash(parse_payload),
        )

    job = load_job(job_id) or job
    job["status"] = "ready"
    job["report_key"] = spreadsheet_engine_job_report_key(job_id)
    job["table_count"] = report.get("table_count", 0)
    return save_job(job)


def _first_shape_hash(parse_payload: dict[str, Any]) -> str:
    for table in parse_payload.get("tables") or []:
        if isinstance(table, dict):
            return str(compute_input_shape(table).get("shape_hash") or "")
    return ""


def run_pipeline(job_id: str) -> dict[str, Any]:
    try:
        run_parse(job_id)
        run_profile(job_id)
        run_interpret(job_id)
        return run_propose(job_id)
    except Exception as exc:  # noqa: BLE001
        job = load_job(job_id) or {"job_id": job_id, "kind": JOB_KIND}
        job["status"] = "error"
        job["error"] = str(exc)
        return save_job(job)


def _list_table_ids(job_id: str) -> list[str]:
    prefix = f"{spreadsheet_engine_job_prefix(job_id)}/tables/"
    table_ids: list[str] = []
    bucket = _bucket()
    if bucket:
        import boto3

        client = boto3.client("s3")
        paginator = client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for item in page.get("Contents") or []:
                key = str(item.get("Key") or "")
                if not key.endswith(".json"):
                    continue
                name = key.rsplit("/", 1)[-1][:-5].strip().lower()
                if name:
                    table_ids.append(name)
        return sorted(dict.fromkeys(table_ids))

    root = prefix_path(_data_dir(), prefix)
    if not root.exists():
        return []
    for path in sorted(root.glob("*.json")):
        name = path.stem.strip().lower()
        if name:
            table_ids.append(name)
    return table_ids


def load_report(job_id: str) -> dict[str, Any] | None:
    report = _read_json(spreadsheet_engine_job_report_key(job_id))
    if report and report.get("tables"):
        return report
    job = load_job(job_id) or {}
    table_ids = [str(tid) for tid in (job.get("table_ids") or []) if str(tid).strip()]
    if not table_ids:
        table_ids = _list_table_ids(job_id)
    if not table_ids:
        return report
    tables = []
    for table_id in table_ids:
        table = load_table(job_id, table_id)
        if isinstance(table, dict):
            tables.append(table)
    if not tables:
        return report
    rebuilt = {
        "kind": "spreadsheet_engine_report",
        "job_id": job_id,
        "filename": job.get("filename") or (report or {}).get("filename"),
        "table_count": len(tables),
        "tables": tables,
    }
    _write_json(spreadsheet_engine_job_report_key(job_id), rebuilt)
    return rebuilt


def load_table(job_id: str, table_id: str) -> dict[str, Any] | None:
    return _read_json(spreadsheet_engine_job_table_key(job_id, table_id))


def load_table_preview(job_id: str, table_id: str, *, max_rows: int = 100) -> dict[str, Any] | None:
    from meshflow.spreadsheet.preview import MAX_PREVIEW_ROWS, extract_table_preview

    job = load_job(job_id)
    if not job:
        return None
    parse_payload = _read_json(spreadsheet_engine_job_parse_key(job_id))
    if not parse_payload:
        return None
    parse_table = None
    for item in parse_payload.get("tables") or []:
        if isinstance(item, dict) and str(item.get("table_id") or "") == table_id:
            parse_table = item
            break
    if not parse_table:
        return None

    proposal = load_table(job_id, table_id) or {}
    headers = [
        str(col.get("name") or "")
        for col in (proposal.get("schema") or [])
        if isinstance(col, dict) and str(col.get("name") or "").strip()
    ]
    if not headers:
        headers = [str(name) for name in (parse_table.get("headers") or []) if str(name).strip()]

    filename = str(job.get("filename") or "workbook.xlsx")
    upload_key = str(job.get("upload_key") or spreadsheet_engine_job_upload_key(job_id, filename))
    with tempfile.TemporaryDirectory() as tmp:
        local_path = Path(tmp) / filename
        local_path.write_bytes(_read_bytes(upload_key))
        preview = extract_table_preview(
            local_path,
            sheet=str(parse_table.get("sheet") or ""),
            data_start_row=int(parse_table.get("data_start_row") or 0),
            data_end_row=int(parse_table.get("data_end_row") or 0),
            min_col=int(parse_table.get("min_col") or 1),
            max_col=int(parse_table.get("max_col") or 1),
            headers=headers,
            max_rows=min(max_rows, MAX_PREVIEW_ROWS),
        )
    preview["table_id"] = table_id
    preview["job_id"] = job_id
    return preview


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


def catalog_id_for(job_id: str, table_id: str) -> str:
    """Legacy job-bound catalog id (backward compatibility)."""
    return f"{job_id.strip().lower()}__{table_id.strip().lower()}"


def catalog_id_for_stable(source_file_slug: str, entity_name: str) -> str:
    slug = slugify_filename(source_file_slug) if "." in source_file_slug else str(source_file_slug or "").strip().lower()
    entity = re.sub(r"[^a-z0-9_]+", "_", str(entity_name or "").strip().lower()).strip("_")
    if not slug or not entity:
        raise ValueError("source_file_slug and entity_name are required for stable catalog id")
    return f"{slug}__{entity}"


def link_job_to_catalog(job_id: str, catalog_id: str) -> dict[str, Any]:
    job = load_job(job_id)
    if not job:
        raise ValueError(f"Unknown job {job_id!r}")
    cid = str(catalog_id or "").strip().lower()
    if not cid:
        raise ValueError("catalog_id is required")
    entry = load_catalog_entry(cid)
    if not entry:
        raise ValueError(f"Unknown catalog entry {cid!r}")
    job["linked_catalog_id"] = cid
    job["reupload"] = True
    return save_job(job)


def find_catalog_matches_for_parse(parse_payload: dict[str, Any], *, limit: int = 5) -> list[str]:
    """Return catalog_ids whose stored input_shape matches any parsed table."""
    matches: list[tuple[float, str]] = []
    for table in parse_payload.get("tables") or []:
        if not isinstance(table, dict):
            continue
        input_shape = compute_input_shape(table)
        shape_hash = str(input_shape.get("shape_hash") or "")
        for entry in list_catalog_entries(limit=200):
            ref_shape = entry.get("input_shape") or {}
            ref_hash = str(ref_shape.get("shape_hash") or "")
            if shape_hash and ref_hash == shape_hash:
                cid = str(entry.get("catalog_id") or "")
                if cid:
                    matches.append((1.0, cid))
            elif ref_shape:
                from meshflow.spreadsheet.transform import shape_compatibility

                score, _ = shape_compatibility(input_shape, ref_shape)
                if score >= 0.8:
                    cid = str(entry.get("catalog_id") or "")
                    if cid:
                        matches.append((score, cid))
    seen: set[str] = set()
    ordered: list[str] = []
    for score, cid in sorted(matches, key=lambda item: -item[0]):
        if cid not in seen:
            seen.add(cid)
            ordered.append(cid)
        if len(ordered) >= limit:
            break
    return ordered


def save_knowledge_entry(entry: dict[str, Any]) -> dict[str, Any]:
    kid = str(entry.get("knowledge_id") or entry.get("catalog_id") or "").strip().lower()
    if not kid:
        raise ValueError("knowledge_id is required")
    entry = {**entry, "kind": KNOWLEDGE_ENTRY_KIND, "knowledge_id": kid}
    _write_json(spreadsheet_engine_knowledge_entry_key(kid), entry)
    return entry


def load_knowledge_entry(knowledge_id: str) -> dict[str, Any] | None:
    return _read_json(spreadsheet_engine_knowledge_entry_key(knowledge_id))


def list_knowledge_entries(limit: int = 200) -> list[dict[str, Any]]:
    bucket = _bucket()
    entries: list[dict[str, Any]] = []
    if bucket:
        import boto3

        client = boto3.client("s3")
        paginator = client.get_paginator("list_objects_v2")
        keys: list[str] = []
        for page in paginator.paginate(Bucket=bucket, Prefix=f"{spreadsheet_engine_knowledge_prefix()}/"):
            for item in page.get("Contents") or []:
                key = str(item.get("Key") or "")
                if key.endswith(".json"):
                    keys.append(key)
        keys.sort(reverse=True)
        for key in keys[:limit]:
            payload = _read_json(key)
            if payload:
                entries.append(payload)
        return entries

    root = prefix_path(_data_dir(), spreadsheet_engine_knowledge_prefix())
    if not root.exists():
        return []
    for entry_file in sorted(root.glob("*.json"), reverse=True):
        payload = json.loads(entry_file.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            entries.append(payload)
        if len(entries) >= limit:
            break
    return entries


def load_knowledge_matches(
    *,
    shape_hash: str = "",
    entity_name: str = "",
    limit: int = 5,
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    entity = str(entity_name or "").strip().lower()
    hash_val = str(shape_hash or "").strip().lower()
    for entry in list_knowledge_entries():
        keys = entry.get("match_keys") or {}
        if hash_val and str(keys.get("shape_hash") or "").lower() == hash_val:
            matches.append(entry)
        elif entity and str(entry.get("entity_name") or "").lower() == entity:
            matches.append(entry)
        if len(matches) >= limit:
            break
    return matches


def record_upload_on_catalog(
    catalog_id: str,
    *,
    job_id: str,
    uploaded_by: str = "",
    input_shape_hash: str = "",
) -> dict[str, Any]:
    entry = load_catalog_entry(catalog_id)
    if not entry:
        raise ValueError(f"Unknown catalog entry {catalog_id!r}")
    now = _now_iso()
    history = list(entry.get("upload_history") or [])
    history.append(
        {
            "job_id": job_id,
            "uploaded_at": now,
            "uploaded_by": uploaded_by,
            "input_shape_hash": input_shape_hash,
        }
    )
    entry["upload_history"] = history[-UPLOAD_HISTORY_LIMIT:]
    entry["last_upload_at"] = now
    entry["last_upload_job_id"] = job_id
    _write_json(spreadsheet_engine_catalog_entry_key(catalog_id), entry)
    return entry


def save_catalog_entry(
    job_id: str,
    table_id: str,
    table: dict[str, Any],
    *,
    filename: str = "",
    catalog_id: str = "",
) -> dict[str, Any]:
    job = load_job(job_id) or {}
    entity_name = str(table.get("entity_name") or table_id)
    source_slug = slugify_filename(str(filename or job.get("filename") or ""))
    cid = str(catalog_id or "").strip().lower()
    if not cid:
        try:
            cid = catalog_id_for_stable(source_slug, entity_name)
        except ValueError:
            cid = catalog_id_for(job_id, table_id)

    transformation = table.get("transformation") or {}
    input_shape = transformation.get("input_shape") or table.get("input_shape") or {}
    output_shape = transformation.get("output_shape") or build_output_shape(table)
    now = _now_iso()

    existing = load_catalog_entry(cid)
    upload_history = list((existing or {}).get("upload_history") or [])
    if not upload_history:
        upload_history = [
            {
                "job_id": job_id,
                "uploaded_at": now,
                "uploaded_by": str(table.get("approved_by") or job.get("created_by") or ""),
                "input_shape_hash": str(input_shape.get("shape_hash") or ""),
            }
        ]

    entry = {
        "kind": CATALOG_ENTRY_KIND,
        "catalog_id": cid,
        "job_id": job_id,
        "table_id": table_id,
        "legacy_catalog_id": catalog_id_for(job_id, table_id),
        "filename": filename or str(job.get("filename") or ""),
        "entity_name": entity_name,
        "source_file_slug": source_slug,
        "approved_at": table.get("approved_at"),
        "approved_by": table.get("approved_by"),
        "last_upload_at": (existing or {}).get("last_upload_at") or now,
        "last_upload_job_id": job_id,
        "upload_history": upload_history[-UPLOAD_HISTORY_LIMIT:],
        "transformation": transformation,
        "input_shape": input_shape,
        "output_shape": output_shape,
        "proposal": table,
    }
    _write_json(spreadsheet_engine_catalog_entry_key(cid), entry)
    return entry


def load_catalog_entry(catalog_id: str) -> dict[str, Any] | None:
    return _read_json(spreadsheet_engine_catalog_entry_key(catalog_id))


def list_catalog_entries(limit: int = 100) -> list[dict[str, Any]]:
    bucket = _bucket()
    entries: list[dict[str, Any]] = []
    if bucket:
        import boto3

        client = boto3.client("s3")
        paginator = client.get_paginator("list_objects_v2")
        keys: list[str] = []
        for page in paginator.paginate(Bucket=bucket, Prefix=f"{spreadsheet_engine_catalog_prefix()}/"):
            for item in page.get("Contents") or []:
                key = str(item.get("Key") or "")
                if key.endswith(".json"):
                    keys.append(key)
        keys.sort(reverse=True)
        for key in keys[:limit]:
            payload = _read_json(key)
            if payload:
                entries.append(payload)
        return entries

    root = prefix_path(_data_dir(), spreadsheet_engine_catalog_prefix())
    if not root.exists():
        return []
    for entry_file in sorted(root.glob("*.json"), reverse=True):
        payload = json.loads(entry_file.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            entries.append(payload)
        if len(entries) >= limit:
            break
    return entries


def load_transform_preview(
    job_id: str,
    table_id: str,
    *,
    max_rows: int = 25,
) -> dict[str, Any] | None:
    preview = load_table_preview(job_id, table_id, max_rows=max_rows)
    if not preview:
        return None
    table = load_table(job_id, table_id) or {}
    transformation = table.get("transformation") or {}
    headers = list(preview.get("headers") or [])
    rows = list(preview.get("rows") or [])
    transform_preview = preview_transformation(rows, headers, transformation, max_rows=max_rows)
    return {
        **preview,
        "transformation_preview": transform_preview,
        "transformation_status": table.get("transformation_status"),
        "transformation_drift": list(table.get("transformation_drift") or []),
    }


def approve_transformation(
    job_id: str,
    table_id: str,
    *,
    username: str = "",
) -> dict[str, Any]:
    table = load_table(job_id, table_id)
    if not table:
        raise ValueError(f"Unknown table {table_id!r} for job {job_id!r}")
    transformation = table.get("transformation") or {}
    table["transformation_status"] = "approved"
    table["transformation_approved_at"] = _now_iso()
    table["transformation_approved_by"] = username
    update_table_proposal(job_id, table_id, table)

    job = load_job(job_id) or {}
    entity_name = str(table.get("entity_name") or table_id)
    source_slug = slugify_filename(str(job.get("filename") or ""))
    try:
        cid = catalog_id_for_stable(source_slug, entity_name)
    except ValueError:
        cid = catalog_id_for(job_id, table_id)

    input_shape = transformation.get("input_shape") or {}
    output_shape = transformation.get("output_shape") or build_output_shape(table)
    knowledge_entry = {
        "knowledge_id": cid,
        "catalog_id": cid,
        "entity_name": entity_name,
        "source_file_slug": source_slug,
        "input_shape": input_shape,
        "output_shape": output_shape,
        "transformation": transformation,
        "approved_at": table["transformation_approved_at"],
        "approved_by": username,
        "match_keys": {
            "shape_hash": str(input_shape.get("shape_hash") or ""),
            "headers_normalized": list(input_shape.get("headers_normalized") or []),
        },
    }
    save_knowledge_entry(knowledge_entry)

    linked_id = str(job.get("linked_catalog_id") or cid)
    if load_catalog_entry(linked_id):
        record_upload_on_catalog(
            linked_id,
            job_id=job_id,
            uploaded_by=username,
            input_shape_hash=str(input_shape.get("shape_hash") or ""),
        )
    return load_table(job_id, table_id) or table


def reject_transformation(
    job_id: str,
    table_id: str,
    *,
    reason: str = "",
    username: str = "",
) -> dict[str, Any]:
    table = load_table(job_id, table_id)
    if not table:
        raise ValueError(f"Unknown table {table_id!r} for job {job_id!r}")
    table["transformation_status"] = "rejected"
    if reason.strip():
        append_table_chat(job_id, table_id, role="user", text=f"Reject transformation: {reason.strip()}")
    update_table_proposal(job_id, table_id, {"transformation_status": "rejected"})

    from meshflow.spreadsheet.propose import propose_transforms_for_report

    parse_payload = _read_json(spreadsheet_engine_job_parse_key(job_id)) or {}
    report = load_report(job_id) or {}
    job = load_job(job_id) or {}
    linked_catalog = None
    linked_id = str(job.get("linked_catalog_id") or "").strip().lower()
    if linked_id:
        linked_catalog = load_catalog_entry(linked_id)
    knowledge_entries = load_knowledge_matches(entity_name=str(table.get("entity_name") or ""))
    report = propose_transforms_for_report(
        report,
        parse_payload,
        linked_catalog=linked_catalog,
        knowledge_entries=knowledge_entries,
        invoke=False,
    )
    for item in report.get("tables") or []:
        if str(item.get("table_id") or "") == table_id:
            if reason.strip():
                notes = list(item.get("transformation_notes") or [])
                notes.append(f"Re-proposed after rejection: {reason.strip()}")
                item["transformation_notes"] = notes
            update_table_proposal(job_id, table_id, item)
            break
    return load_table(job_id, table_id) or table


def edit_transformation(
    job_id: str,
    table_id: str,
    transformation: dict[str, Any],
) -> dict[str, Any]:
    table = load_table(job_id, table_id)
    if not table:
        raise ValueError(f"Unknown table {table_id!r} for job {job_id!r}")
    updates = {
        "transformation": transformation,
        "transformation_status": "pending_review",
    }
    return update_table_proposal(job_id, table_id, updates)


def approve_table(job_id: str, table_id: str, *, username: str = "") -> dict[str, Any]:
    table = load_table(job_id, table_id)
    if not table:
        raise ValueError(f"Unknown table {table_id!r} for job {job_id!r}")

    transformation = table.get("transformation") or {}
    steps = transformation.get("steps") or []
    transform_status = str(table.get("transformation_status") or "")
    if steps and transform_status != "approved":
        raise ValueError("Approve the transformation before approving the table.")

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
    job = load_job(job_id) or {}
    entry = save_catalog_entry(
        job_id,
        table_id,
        table,
        filename=str(job.get("filename") or ""),
    )
    if transformation and steps:
        save_knowledge_entry(
            {
                "knowledge_id": entry["catalog_id"],
                "catalog_id": entry["catalog_id"],
                "entity_name": entry.get("entity_name"),
                "source_file_slug": entry.get("source_file_slug"),
                "input_shape": entry.get("input_shape"),
                "output_shape": entry.get("output_shape"),
                "transformation": transformation,
                "approved_at": table["approved_at"],
                "approved_by": username,
                "match_keys": {
                    "shape_hash": str((entry.get("input_shape") or {}).get("shape_hash") or ""),
                    "headers_normalized": list(
                        (entry.get("input_shape") or {}).get("headers_normalized") or []
                    ),
                },
            }
        )
    return table


def complete_reload(job_id: str, table_id: str, *, username: str = "") -> dict[str, Any]:
    """Complete a passed reload — update catalog without re-running AI."""
    table = load_table(job_id, table_id)
    if not table:
        raise ValueError(f"Unknown table {table_id!r} for job {job_id!r}")
    if str(table.get("reload_validation_status") or "") != "passed":
        raise ValueError("Reload validation must pass before completing the reload.")
    job = load_job(job_id) or {}
    linked_id = str(job.get("linked_catalog_id") or "").strip().lower()
    if not linked_id:
        raise ValueError("Linked catalog entry is required to complete reload.")

    table["status"] = "approved"
    table["approved_at"] = _now_iso()
    table["approved_by"] = username
    update_table_proposal(job_id, table_id, table)

    entry = save_catalog_entry(
        job_id,
        table_id,
        table,
        filename=str(job.get("filename") or ""),
        catalog_id=linked_id,
    )
    record_upload_on_catalog(
        linked_id,
        job_id=job_id,
        uploaded_by=username,
        input_shape_hash=str((table.get("transformation") or {}).get("input_shape", {}).get("shape_hash") or ""),
    )
    return {"table": table, "catalog_entry": entry}


def request_schema_rewrite(job_id: str) -> dict[str, Any]:
    """Re-run interpret + propose with AI after a failed reload validation."""
    job = load_job(job_id) or {}
    job["reupload"] = False
    job["reload_mode"] = False
    job["reload_validation_status"] = ""
    save_job(job)
    run_interpret(job_id, force_ai=True)
    return run_propose(job_id, force_ai=True)


def request_transformation_rewrite(job_id: str) -> dict[str, Any]:
    """Re-run transformation proposal with AI, keeping the current schema."""
    job = load_job(job_id) or {}
    job["reload_mode"] = False
    job["reload_validation_status"] = ""
    save_job(job)
    return run_propose(job_id, force_ai=True)


def append_table_chat(job_id: str, table_id: str, *, role: str, text: str) -> dict[str, Any]:
    table = load_table(job_id, table_id)
    if not table:
        raise ValueError(f"Unknown table {table_id!r} for job {job_id!r}")
    history = list(table.get("chat_history") or [])
    history.append({"role": role, "text": text, "at": _now_iso()})
    table["chat_history"] = history[-20:]
    return update_table_proposal(job_id, table_id, {"chat_history": table["chat_history"]})


def append_chat(job_id: str, *, role: str, text: str) -> dict[str, Any]:
    job = load_job(job_id)
    if not job:
        raise ValueError(f"Unknown job {job_id!r}")
    history = list(job.get("chat_history") or [])
    history.append({"role": role, "text": text, "at": _now_iso()})
    job["chat_history"] = history[-20:]
    return save_job(job)
