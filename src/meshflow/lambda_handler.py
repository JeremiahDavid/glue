from __future__ import annotations

from typing import Any

from meshflow.project_config import resolve_ingest_connector


def handler(event: dict[str, Any] | None, _context: Any) -> dict[str, Any]:
    """Lambda entry point: dispatch to the configured ingest connector."""
    connector = resolve_ingest_connector()
    if connector == "qbd":
        from meshflow.qbd.lambda_handler import handler as qbd_handler

        return qbd_handler(event, _context)

    from meshflow.qbo.lambda_handler import handler as qbo_handler

    return qbo_handler(event, _context)


def lambda_handler(event: dict[str, Any] | None, context: Any) -> dict[str, Any]:
    """AWS Lambda-compatible alias."""
    return handler(event, context)
