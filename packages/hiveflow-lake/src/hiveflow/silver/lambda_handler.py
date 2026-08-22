from __future__ import annotations

from typing import Any

from meshflow.silver.glue_runner import run_silver_consolidate


def handler(event: dict[str, Any] | None, _context: Any) -> dict[str, Any]:
    """Local/Lambda entrypoint; production refresh uses the Glue job."""
    payload = event or {}
    requested_source = str(payload.get("source", "")).strip().lower()
    full_rebuild = bool(payload.get("full_rebuild"))
    return run_silver_consolidate(source=requested_source, full_rebuild=full_rebuild)


def lambda_handler(event: dict[str, Any] | None, context: Any) -> dict[str, Any]:
    return handler(event, context)
