"""Trigger / status helpers for client gold source-docs builds."""

from __future__ import annotations

import json
import os
from typing import Any

from meshflow.dna.settings import DnaSettings
from meshflow.dna.source_docs_reference import load_source_docs_gold


def _on_lambda() -> bool:
    return bool(os.environ.get("AWS_LAMBDA_FUNCTION_NAME", "").strip())


def gold_function_name(*, company: str, environment: str) -> str:
    override = os.getenv("MESHFLOW_SOURCE_DOCS_GOLD_FUNCTION", "").strip()
    if override:
        return override
    return f"{company.strip().lower()}-{environment.strip().lower()}-bc-source-docs-gold"


def source_docs_gold_status(settings: DnaSettings) -> dict[str, Any]:
    return load_source_docs_gold(settings)


def enqueue_source_docs_gold_build(
    settings: DnaSettings,
    *,
    company: str,
    environment: str,
    seed_missing_overlays: bool = True,
    publish_schemas: bool = True,
) -> dict[str, Any]:
    """Enqueue (Lambda) or run locally the gold merge job."""
    source = settings.source.strip().lower() or "dbc"
    payload = {
        "source": source,
        "seed_missing_overlays": bool(seed_missing_overlays),
        "publish_schemas": bool(publish_schemas),
        "client_bucket": settings.s3_bucket or os.getenv("MESHFLOW_S3_BUCKET", "").strip() or None,
    }

    if _on_lambda():
        import boto3

        function_name = gold_function_name(company=company, environment=environment)
        region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-2"
        client = boto3.client("lambda", region_name=region)
        response = client.invoke(
            FunctionName=function_name,
            InvocationType="Event",
            Payload=json.dumps(payload, default=str).encode("utf-8"),
        )
        status = int(response.get("StatusCode") or 0)
        if status not in {202, 200}:
            raise RuntimeError(f"Gold build invoke returned status {status}")
        return {
            "status": "enqueued",
            "function_name": function_name,
            "status_code": status,
            "payload": payload,
        }

    # Local / test: run the merge job in-process when connectors are installed.
    try:
        from meshflow.bc.source_docs_gold import run_source_docs_gold_job
    except ImportError as exc:  # pragma: no cover - depends on install set
        return {
            "status": "error",
            "reason": "connectors_unavailable",
            "error": str(exc),
            "hint": (
                "Install meshflow-connectors or invoke "
                f"{gold_function_name(company=company, environment=environment)} directly."
            ),
        }

    result = run_source_docs_gold_job(
        source=source,
        client_bucket=payload.get("client_bucket"),
        publish_schemas=bool(publish_schemas),
        seed_missing_overlays=bool(seed_missing_overlays),
        dry_run=False,
    )
    return {"status": "published", "result": result}
