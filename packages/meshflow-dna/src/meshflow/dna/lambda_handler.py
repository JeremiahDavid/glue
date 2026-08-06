from __future__ import annotations

from typing import Any

from meshflow.dna.compile import compile_pack
from meshflow.dna.publish import publish_staging
from meshflow.dna.settings import DnaSettings
from meshflow.dna.validate import run_validation
from meshflow.dna.workflow import load_production_pack


def run_dna_pipeline(settings: DnaSettings) -> dict[str, Any]:
    from meshflow.dna.init_client import ensure_client_governance

    governance_init = ensure_client_governance(settings)
    pack = load_production_pack(settings)
    compile_manifest = compile_pack(settings, pack)
    validation_result = run_validation(settings, pack)
    if validation_result["status"] != "passed":
        return {
            "status": "validation_failed",
            "governance_init": governance_init,
            "compile": compile_manifest,
            "validation": validation_result,
        }
    publish_manifest = publish_staging(
        settings,
        compile_manifest=compile_manifest,
        validation_result=validation_result,
    )
    return {
        "status": "published",
        "governance_init": governance_init,
        "compile": compile_manifest,
        "validation": validation_result,
        "publish": publish_manifest,
    }


def _cfn_governance_init(event: dict[str, Any]) -> dict[str, Any]:
    """CloudFormation Provider onEvent — seed governance or no-op on Delete."""
    from meshflow.dna.init_client import ensure_client_governance
    from meshflow.dna.runtime import resolve_dna_settings

    request_type = str(event.get("RequestType", ""))
    props = event.get("ResourceProperties") or {}
    if not isinstance(props, dict):
        props = {}
    company = str(props.get("company") or "").strip()
    pack_id = str(props.get("pack_id") or "").strip()
    physical_id = str(
        event.get("PhysicalResourceId") or f"governance-init-{pack_id or company or 'default'}"
    )

    if request_type == "Delete":
        return {
            "PhysicalResourceId": physical_id,
            "Data": {"status": "delete_noop", "pack_id": pack_id},
        }

    settings = resolve_dna_settings(
        event={
            "action": "init-client",
            "company": company,
            "pack_id": pack_id,
        }
    )
    result = ensure_client_governance(settings)
    status = str(result.get("status", ""))
    if status not in {"initialized", "skipped"}:
        raise RuntimeError(f"Governance init failed: {result}")
    return {
        "PhysicalResourceId": physical_id,
        "Data": {
            "status": status,
            "pack_id": str(result.get("pack_id", pack_id)),
            "version": str(result.get("version", "")),
            "reason": str(result.get("reason", "")),
        },
    }


def handler(event: dict[str, Any] | None, _context: Any) -> dict[str, Any]:
    from meshflow.dna.init_client import ensure_client_governance
    from meshflow.dna.runtime import resolve_dna_settings

    payload = event or {}

    # CDK custom_resources.Provider / CloudFormation custom resource protocol
    if payload.get("RequestType") in {"Create", "Update", "Delete"}:
        return _cfn_governance_init(payload)

    settings = resolve_dna_settings(event=payload)
    action = str(payload.get("action", "publish")).strip().lower()

    if action in {"init-client", "init_client", "init-governance", "init_governance"}:
        return ensure_client_governance(settings)

    pack = load_production_pack(settings)

    if action == "compile":
        return compile_pack(settings, pack)
    if action == "validate":
        compile_pack(settings, pack)
        return run_validation(settings, pack)
    if action == "publish":
        return run_dna_pipeline(settings)
    raise ValueError(f"Unknown DNA action {action!r}")


def lambda_handler(event: dict[str, Any] | None, context: Any) -> dict[str, Any]:
    return handler(event, context)
