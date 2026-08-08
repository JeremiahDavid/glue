from __future__ import annotations

import os
from typing import Any

from meshflow.dna.runtime import resolve_dna_settings
from meshflow.dna.web.app import create_app
from meshflow.dna.web.theme import BINARY_STATIC_CONTENT_TYPES

_wsgi_app = None


def _get_wsgi_app():
    global _wsgi_app  # noqa: PLW0603 — Lambda container reuse
    if _wsgi_app is None:
        from meshflow.project_config import (
            get_environment_config,
            get_platform_environment_config,
            resolve_selection,
        )

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
            ui_mode=os.getenv("MESHFLOW_UI_MODE"),
        )
    return _wsgi_app


def _cfn_reporting_init(event: dict[str, Any]) -> dict[str, Any]:
    """CloudFormation Provider onEvent — seed reporting config or no-op on Delete."""
    from meshflow.dna.init_client import ensure_reporting_config
    from meshflow.dna.runtime import resolve_dna_settings

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
    if payload.get("meshflow_task") == "config_assistant_chat":
        return _config_assistant_chat_task(payload)
    if payload.get("meshflow_task") == "semantic_llm_tagging":
        return _semantic_llm_tagging_task(payload)
    if payload.get("meshflow_task") == "semantic_profiling":
        return _semantic_profiling_task(payload)

    try:
        import awsgi
    except ImportError as exc:
        raise RuntimeError(
            "aws-wsgi is required for the DNA UI Lambda. Install meshflow with dependencies."
        ) from exc

    return awsgi.response(
        _get_wsgi_app(),
        event,
        context,
        base64_content_types=BINARY_STATIC_CONTENT_TYPES,
    )


def _config_assistant_chat_task(event: dict[str, Any]) -> dict[str, Any]:
    """Background Bedrock chat — avoids API Gateway's ~29s integration timeout."""
    import json

    from meshflow.dna.web.portal.config_assistant.service import complete_chat_turn

    proposal_id = str(event.get("proposal_id") or "").strip()
    username = str(event.get("username") or "admin").strip() or "admin"
    if not proposal_id:
        raise ValueError("proposal_id is required for config_assistant_chat")

    print(
        json.dumps(
            {
                "msg": "config_assistant_chat_start",
                "proposal_id": proposal_id,
                "username": username,
            }
        )
    )
    settings = resolve_dna_settings(
        event={
            "action": "config-assistant-chat",
            "company": str(event.get("company") or "").strip() or None,
        }
    )
    complete_chat_turn(settings, proposal_id=proposal_id, username=username)
    print(json.dumps({"msg": "config_assistant_chat_done", "proposal_id": proposal_id}))
    return {"ok": True, "proposal_id": proposal_id}


def _semantic_profiling_task(event: dict[str, Any]) -> dict[str, Any]:
    """Background silver profiling — avoids API Gateway's ~29s integration timeout."""
    import json

    from meshflow.dna.semantic_init import run_semantic_profiling_job

    username = str(event.get("username") or "admin").strip() or "admin"
    force = bool(event.get("force"))
    print(json.dumps({"msg": "semantic_profiling_start", "username": username, "force": force}))
    settings = resolve_dna_settings(
        event={
            "action": "semantic-profiling",
            "company": str(event.get("company") or "").strip() or None,
        }
    )
    result = run_semantic_profiling_job(settings, username=username, force=force)
    print(json.dumps({"msg": "semantic_profiling_done", "result": result}))
    return result


def _semantic_llm_tagging_task(event: dict[str, Any]) -> dict[str, Any]:
    """Background LLM column tagging after sync semantic init (API Gateway-safe)."""
    import json

    from meshflow.dna.semantic_init import enrich_semantic_model_llm_tags

    username = str(event.get("username") or "admin").strip() or "admin"
    print(json.dumps({"msg": "semantic_llm_tagging_start", "username": username}))
    settings = resolve_dna_settings(
        event={
            "action": "semantic-llm-tagging",
            "company": str(event.get("company") or "").strip() or None,
        }
    )
    result = enrich_semantic_model_llm_tags(settings, username=username)
    print(json.dumps({"msg": "semantic_llm_tagging_done", "result": result}))
    return result
