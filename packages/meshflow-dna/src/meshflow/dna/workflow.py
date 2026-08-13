from __future__ import annotations

from datetime import date, datetime
from meshflow.compat import UTC
from typing import Any

from meshflow.dna.governance import (
    load_governance_dna,
    load_governance_workflow,
    save_governance_version,
)
from meshflow.dna.schema import DefinitionPack, PackStatus
from meshflow.dna.settings import DnaSettings
from meshflow.dna.store import write_json_artifact
from meshflow.storage.paths import governance_workflow_key


def _workflow_state_key(pack_id: str) -> str:
    return governance_workflow_key(pack_id)


def load_workflow_state(settings: DnaSettings, pack_id: str) -> dict[str, Any]:
    payload = load_governance_workflow(settings, pack_id)
    if not payload:
        return {"pack_id": pack_id, "active_version": None, "history": []}
    return payload


def save_workflow_state(settings: DnaSettings, state: dict[str, Any]) -> str:
    pack_id = str(state["pack_id"])
    return write_json_artifact(settings, _workflow_state_key(pack_id), state)


def _prepare_reporting_payload(
    settings: DnaSettings,
    pack: DefinitionPack,
    reporting: dict[str, Any] | None,
) -> dict[str, Any]:
    from meshflow.dna.reporting import (
        default_reporting_pack,
        load_reporting_pack,
        normalize_reporting_identity,
    )

    status = pack.approval.status or pack.status
    reporting_id = settings.reporting_config_id
    payload = load_reporting_pack(
        reporting
        if reporting is not None
        else default_reporting_pack(
            pack_id=reporting_id,
            version=pack.version,
            status=status,
        )
    )
    return normalize_reporting_identity(
        settings, payload, version=pack.version, status=payload.get("status") or status
    )


def save_definition_pack(
    settings: DnaSettings,
    pack: DefinitionPack,
    *,
    reporting: dict[str, Any] | None = None,
    docs: list[dict[str, str]] | None = None,
) -> str:
    result = save_governance_version(
        settings,
        pack=pack,
        reporting=_prepare_reporting_payload(settings, pack, reporting),
        docs=docs,
    )
    return str(result["dna_path"])


def promote_pack(
    settings: DnaSettings,
    pack: DefinitionPack,
    *,
    target_status: str,
    approver: str = "",
    notes: str = "",
    reporting: dict[str, Any] | None = None,
    docs: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    allowed = {
        PackStatus.DRAFT.value: {PackStatus.VALIDATED.value},
        PackStatus.VALIDATED.value: {PackStatus.PRODUCTION.value, PackStatus.DRAFT.value},
        PackStatus.PRODUCTION.value: {PackStatus.DRAFT.value},
    }
    current = pack.approval.status
    if target_status not in allowed.get(current, set()):
        raise ValueError(
            f"Cannot promote pack from {current!r} to {target_status!r}"
        )

    pack.approval.status = target_status
    pack.status = target_status
    if target_status in {PackStatus.VALIDATED.value, PackStatus.PRODUCTION.value}:
        pack.approval.approver = approver
        pack.approval.approved_at = date.today().isoformat()
    if notes:
        pack.approval.notes = notes

    saved = save_governance_version(
        settings,
        pack=pack,
        reporting=_prepare_reporting_payload(settings, pack, reporting),
        docs=docs,
    )
    state = load_workflow_state(settings, pack.pack_id)
    state["active_version"] = (
        pack.version if target_status == PackStatus.PRODUCTION.value else state.get("active_version")
    )
    history = state.get("history", [])
    if not isinstance(history, list):
        history = []
    history.append(
        {
            "version": pack.version,
            "status": target_status,
            "approver": approver,
            "at": datetime.now(UTC).isoformat(),
            "notes": notes,
        }
    )
    state["history"] = history
    workflow_path = save_workflow_state(settings, state)

    return {
        "pack_id": pack.pack_id,
        "version": pack.version,
        "status": target_status,
        "pack_path": saved["dna_path"],
        "reporting_path": saved["reporting_path"],
        "manifest_path": saved["manifest_path"],
        "workflow_path": workflow_path,
    }


def load_production_pack(settings: DnaSettings) -> DefinitionPack:
    """Load the company DNA config used by gold compile (``{company}_dna_config``)."""
    pack_id = settings.dna_config_id
    state = load_workflow_state(settings, pack_id)
    version = settings.pack_version or state.get("active_version")
    if not version:
        from meshflow.dna.store import load_pack_from_settings

        return load_pack_from_settings(settings)

    try:
        return load_governance_dna(settings, pack_id, str(version))
    except FileNotFoundError:
        # Gold must use the company config — do not silently fall back to starter
        # packs that are not the tenant's governance artifact.
        raise FileNotFoundError(
            f"Company DNA config {pack_id!r} v{version} not found under governance/. "
            "Deploy DnaStack (or run meshflow-dna init-client) to seed it from "
            "dbc_dna_boilerplate.yaml."
        )
