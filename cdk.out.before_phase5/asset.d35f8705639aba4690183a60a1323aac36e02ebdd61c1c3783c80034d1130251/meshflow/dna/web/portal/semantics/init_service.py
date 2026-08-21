"""Portal semantic init — sync pack bootstrap + async LLM enrichment."""

from __future__ import annotations

import json
import os
from typing import Any

from meshflow.dna.semantic_init import run_semantic_init
from meshflow.dna.settings import DnaSettings


def enqueue_semantic_llm_tagging(*, username: str, company: str) -> dict[str, Any]:
    """Fire-and-forget Lambda Event invoke for LLM column tagging."""
    import boto3

    function_name = os.environ.get("AWS_LAMBDA_FUNCTION_NAME", "").strip()
    if not function_name:
        return {"status": "skipped", "reason": "not_on_lambda"}

    region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-2"
    client = boto3.client("lambda", region_name=region)
    response = client.invoke(
        FunctionName=function_name,
        InvocationType="Event",
        Payload=json.dumps(
            {
                "meshflow_task": "semantic_llm_tagging",
                "username": username,
                "company": company,
                "environment": os.environ.get("MESHFLOW_ENVIRONMENT", ""),
            }
        ).encode("utf-8"),
    )
    status = int(response.get("StatusCode") or 0)
    if status not in {202, 200}:
        raise RuntimeError(f"Background LLM tagging invoke returned status {status}")
    print(
        json.dumps(
            {
                "msg": "semantic_llm_tagging_enqueued",
                "username": username,
                "status_code": status,
            }
        )
    )
    return {"status": "enqueued", "status_code": status}


def run_portal_semantic_init(
    settings: DnaSettings,
    *,
    username: str,
    company: str,
    force: bool = False,
) -> dict[str, Any]:
    """Initialize from source packs synchronously; enqueue LLM tagging when on Lambda.

    Keeps the HTTP response under API Gateway's ~29s limit.
    """
    result = run_semantic_init(
        settings,
        username=username,
        force=force,
        enable_llm_tagging=False,
    )
    if result.get("status") == "skipped":
        return result

    result["llm_tagging"] = {
        "tagged_count": 0,
        "skipped_count": 0,
        "reason": "deferred_to_step_3",
    }
    return result
