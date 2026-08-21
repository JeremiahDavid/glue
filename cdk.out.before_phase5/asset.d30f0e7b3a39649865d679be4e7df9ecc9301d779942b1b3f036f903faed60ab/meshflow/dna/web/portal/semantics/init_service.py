"""Portal semantic init — async profiling on Lambda + deferred LLM tagging."""

from __future__ import annotations

import json
import os
from typing import Any

from meshflow.dna.semantic_init import run_semantic_profiling_job
from meshflow.dna.settings import DnaSettings


def _on_lambda() -> bool:
    return bool(os.environ.get("AWS_LAMBDA_FUNCTION_NAME", "").strip())


def _enqueue_background_task(*, task: str, username: str, company: str, **extra: Any) -> dict[str, Any]:
    import boto3

    function_name = os.environ.get("AWS_LAMBDA_FUNCTION_NAME", "").strip()
    if not function_name:
        return {"status": "skipped", "reason": "not_on_lambda"}

    region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-2"
    client = boto3.client("lambda", region_name=region)
    payload: dict[str, Any] = {
        "meshflow_task": task,
        "username": username,
        "company": company,
        "environment": os.environ.get("MESHFLOW_ENVIRONMENT", ""),
    }
    payload.update(extra)
    response = client.invoke(
        FunctionName=function_name,
        InvocationType="Event",
        Payload=json.dumps(payload).encode("utf-8"),
    )
    status = int(response.get("StatusCode") or 0)
    if status not in {202, 200}:
        raise RuntimeError(f"Background {task} invoke returned status {status}")
    print(json.dumps({"msg": f"{task}_enqueued", "username": username, "status_code": status}))
    return {"status": "enqueued", "status_code": status}


def enqueue_semantic_profiling(
    *,
    username: str,
    company: str,
    force: bool = False,
) -> dict[str, Any]:
    """Fire-and-forget Lambda Event invoke for silver profiling + key inference."""
    return _enqueue_background_task(
        task="semantic_profiling",
        username=username,
        company=company,
        force=bool(force),
    )


def enqueue_semantic_llm_tagging(*, username: str, company: str) -> dict[str, Any]:
    """Fire-and-forget Lambda Event invoke for LLM column tagging."""
    return _enqueue_background_task(
        task="semantic_llm_tagging",
        username=username,
        company=company,
    )


def run_portal_semantic_init(
    settings: DnaSettings,
    *,
    username: str,
    company: str,
    force: bool = False,
) -> dict[str, Any]:
    """Profile silver in the background on Lambda; run synchronously for local dev.

    Keeps the HTTP response under API Gateway's ~29s limit.
    """
    if _on_lambda():
        from meshflow.dna.semantic_model import load_semantic_model_workflow, update_profiling_workflow

        workflow = load_semantic_model_workflow(settings)
        if workflow.get("profiling_status") == "in_progress" and not force:
            return {
                "status": "skipped",
                "reason": "profiling_in_progress",
                "profiling": {"status": "in_progress"},
            }

        update_profiling_workflow(settings, status="in_progress", username=username)
        try:
            enqueue_result = enqueue_semantic_profiling(
                username=username,
                company=company,
                force=force,
            )
        except Exception as exc:  # noqa: BLE001
            update_profiling_workflow(settings, status="error", username=username, error=str(exc))
            raise
        return {
            "status": "enqueued",
            "reason": "async_profiling",
            "profiling": {
                "status": "in_progress",
                "enqueue": enqueue_result,
            },
            "llm_tagging": {
                "tagged_count": 0,
                "skipped_count": 0,
                "reason": "deferred_to_step_3",
            },
        }

    result = run_semantic_profiling_job(settings, username=username, force=force)
    if result.get("status") == "skipped":
        return result

    result["llm_tagging"] = {
        "tagged_count": 0,
        "skipped_count": 0,
        "reason": "deferred_to_step_3",
    }
    return result
