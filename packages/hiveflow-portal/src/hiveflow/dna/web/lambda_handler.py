from __future__ import annotations

import os
from typing import Any

from hiveflow.dna.runtime import resolve_dna_settings
from hiveflow.dna.web.app import create_app
from hiveflow.dna.web.theme import BINARY_STATIC_CONTENT_TYPES

_wsgi_app = None


def _get_wsgi_app():
    global _wsgi_app  # noqa: PLW0603 — Lambda container reuse
    if _wsgi_app is None:
        from hiveflow.project_config import (
            ensure_writable_config_path,
            get_environment_config,
            get_platform_environment_config,
            resolve_selection,
        )

        ensure_writable_config_path()
        company, environment = resolve_selection()
        try:
            env_config = get_platform_environment_config(environment)
        except KeyError:
            env_config = get_environment_config(company, environment)

        _wsgi_app = create_app(
            resolve_dna_settings(),
            company=company,
            environment=environment,
            env_config=env_config,
            ui_mode=os.getenv("HIVEFLOW_UI_MODE"),
        )
    return _wsgi_app


def _cfn_reporting_init(event: dict[str, Any]) -> dict[str, Any]:
    """CloudFormation Provider onEvent — seed reporting config or no-op on Delete."""
    from hiveflow.dna.init_client import ensure_reporting_config
    from hiveflow.dna.runtime import resolve_dna_settings

    request_type = str(event.get("RequestType", ""))
    props = event.get("ResourceProperties") or {}
    if not isinstance(props, dict):
        props = {}
    company = str(props.get("company") or "").strip()
    pack_id = str(props.get("pack_id") or "").strip()
    physical_id = str(
        event.get("PhysicalResourceId")
        or f"reporting-config-init-{pack_id or company or 'default'}"
    )

    if request_type == "Delete":
        return {
            "PhysicalResourceId": physical_id,
            "Data": {"status": "delete_noop", "pack_id": pack_id},
        }

    settings = resolve_dna_settings(
        event={
            "action": "init-reporting",
            "company": company,
            "pack_id": pack_id,
        }
    )
    result = ensure_reporting_config(settings)
    status = str(result.get("status", ""))
    if status not in {"initialized", "skipped"}:
        raise RuntimeError(f"Reporting config init failed: {result}")
    return {
        "PhysicalResourceId": physical_id,
        "Data": {
            "status": status,
            "pack_id": str(result.get("pack_id", pack_id)),
            "reporting_config": str(result.get("reporting_config", "")),
            "version": str(result.get("version", "")),
            "reason": str(result.get("reason", "")),
        },
    }


def ui_handler(event: dict[str, Any] | None, context: Any) -> dict[str, Any]:
    """Lambda entry for reporting UI (API Gateway) and ReportingStack seed CR."""
    payload = event or {}
    if payload.get("RequestType") in {"Create", "Update", "Delete"}:
        return _cfn_reporting_init(payload)

    task = str(payload.get("hiveflow_task") or "").strip()
    if task == "kpi_generator_generate":
        from hiveflow.dna.runtime import resolve_dna_settings
        from hiveflow.dna.web.portal.kpi_generator.generation import run_kpi_generation_job

        return run_kpi_generation_job(resolve_dna_settings(), payload)

    try:
        import awsgi
    except ImportError as exc:
        raise RuntimeError(
            "aws-wsgi is required for the DNA UI Lambda. Install hiveflow with dependencies."
        ) from exc

    return awsgi.response(
        _get_wsgi_app(),
        event,
        context,
        base64_content_types=BINARY_STATIC_CONTENT_TYPES,
    )
