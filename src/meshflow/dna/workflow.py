from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from meshflow.dna.schema import DefinitionPack, PackStatus, load_definition_pack
from meshflow.dna.settings import DnaSettings
from meshflow.dna.store import definition_pack_key, read_json_artifact, write_json_artifact


def _workflow_state_key(pack_id: str) -> str:
    return f"dna/definition_packs/{pack_id}/workflow.json"


def load_workflow_state(settings: DnaSettings, pack_id: str) -> dict[str, Any]:
    payload = read_json_artifact(settings, _workflow_state_key(pack_id))
    if not payload:
        return {"pack_id": pack_id, "active_version": None, "history": []}
    return payload


def save_workflow_state(settings: DnaSettings, state: dict[str, Any]) -> str:
    pack_id = str(state["pack_id"])
    return write_json_artifact(settings, _workflow_state_key(pack_id), state)


def save_definition_pack(settings: DnaSettings, pack: DefinitionPack) -> str:
    key = definition_pack_key(pack.pack_id, pack.version)
    return write_json_artifact(settings, key.replace(".yaml", ".json"), pack.to_dict())


def promote_pack(
    settings: DnaSettings,
    pack: DefinitionPack,
    *,
    target_status: str,
    approver: str = "",
    notes: str = "",
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

    pack_path = save_definition_pack(settings, pack)
    state = load_workflow_state(settings, pack.pack_id)
    state["active_version"] = pack.version if target_status == PackStatus.PRODUCTION.value else state.get("active_version")
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
        "pack_path": pack_path,
        "workflow_path": workflow_path,
    }


def load_production_pack(settings: DnaSettings) -> DefinitionPack:
    state = load_workflow_state(settings, settings.pack_id)
    version = settings.pack_version or state.get("active_version")
    if not version:
        from meshflow.dna.store import load_pack_from_settings

        return load_pack_from_settings(settings)

    key = definition_pack_key(settings.pack_id, str(version)).replace(".yaml", ".json")
    payload = read_json_artifact(settings, key)
    if not payload:
        from meshflow.dna.schema import starter_pack_path, load_definition_pack_file

        return load_definition_pack_file(starter_pack_path(settings.pack_id))
    return load_definition_pack(payload)
