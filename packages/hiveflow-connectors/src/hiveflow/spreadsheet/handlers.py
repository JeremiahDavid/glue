"""AWS Lambda handlers for Spreadsheet Engine Step Functions."""

from __future__ import annotations

from typing import Any

from meshflow.spreadsheet.jobs import run_interpret, run_parse, run_profile, run_propose


def parse_handler(event: dict[str, Any] | None, _context: Any) -> dict[str, Any]:
    body = event or {}
    job_id = str(body.get("job_id") or "").strip()
    if not job_id:
        raise ValueError("job_id is required")
    job = run_parse(job_id)
    return {"status": "ok", "job_id": job_id, "job": job}


def profile_handler(event: dict[str, Any] | None, _context: Any) -> dict[str, Any]:
    body = event or {}
    job_id = str(body.get("job_id") or "").strip()
    if not job_id:
        raise ValueError("job_id is required")
    job = run_profile(job_id)
    return {"status": "ok", "job_id": job_id, "job": job}


def interpret_handler(event: dict[str, Any] | None, _context: Any) -> dict[str, Any]:
    body = event or {}
    job_id = str(body.get("job_id") or "").strip()
    if not job_id:
        raise ValueError("job_id is required")
    job = run_interpret(job_id)
    return {"status": "ok", "job_id": job_id, "job": job}


def propose_handler(event: dict[str, Any] | None, _context: Any) -> dict[str, Any]:
    body = event or {}
    job_id = str(body.get("job_id") or "").strip()
    if not job_id:
        raise ValueError("job_id is required")
    job = run_propose(job_id)
    return {"status": "ok", "job_id": job_id, "job": job}


def pipeline_handler(event: dict[str, Any] | None, _context: Any) -> dict[str, Any]:
    """Local/dev convenience handler that runs the full pipeline synchronously."""
    body = event or {}
    job_id = str(body.get("job_id") or "").strip()
    if not job_id:
        raise ValueError("job_id is required")
    from meshflow.spreadsheet.jobs import run_pipeline

    job = run_pipeline(job_id)
    return {"status": job.get("status", "ok"), "job_id": job_id, "job": job}
