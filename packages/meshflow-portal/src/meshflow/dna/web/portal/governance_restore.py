"""Forward-restore DNA or reporting configs from a historical governance snapshot."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from meshflow.dna.governance import (
    load_governance_dna,
    load_governance_reporting_payload,
    save_governance_version,
)
from meshflow.dna.settings import DnaSettings
from meshflow.dna.web.portal.governance_helpers.proposals import bump_patch_version
from meshflow.dna.reporting import (
    load_reporting_pack,
    normalize_reporting_identity,
    save_reporting_pack,
)
from meshflow.dna.workflow import load_workflow_state, save_workflow_state

RestoreTarget = Literal["dna", "reporting"]


def governance_target_snapshot_exists(
    settings: DnaSettings,
    *,
    target: RestoreTarget,
    version: str,
) -> bool:
    """True when the historical artifact for ``target`` at ``version`` is present."""
    pack_id = settings.dna_config_id
    version = str(version or "").strip()
    if not version:
        return False
    if target == "dna":
        try:
            load_governance_dna(settings, pack_id, version)
        except FileNotFoundError:
            return False
        return True
    payload = load_governance_reporting_payload(settings, pack_id, version)
    return payload is not None


def restore_governance_target(
    settings: DnaSettings,
    *,
    target: RestoreTarget,
    source_version: str,
    username: str,
) -> dict[str, Any]:
    """Copy a historical snapshot into the next patch version and pin that target only."""
    if target not in {"dna", "reporting"}:
        raise ValueError("target must be 'dna' or 'reporting'")

    source_version = str(source_version or "").strip()
    if not source_version:
        raise ValueError("source_version is required")

    pack_id = settings.dna_config_id
    state = load_workflow_state(settings, pack_id)
    state["pack_id"] = pack_id

    if target == "dna":
        current_pin = str(state.get("active_version") or "").strip()
        if not current_pin:
            raise ValueError("No active DNA production pin to restore from")
        if source_version == current_pin:
            raise ValueError(f"DNA v{source_version} is already the production pin")
        if not governance_target_snapshot_exists(
            settings, target="dna", version=source_version
        ):
            raise FileNotFoundError(
                f"No DNA snapshot found for {pack_id!r} v{source_version}"
            )

        new_version = bump_patch_version(current_pin)
        pack = load_governance_dna(settings, pack_id, source_version)
        pack.pack_id = pack_id
        pack.version = new_version
        pack.status = "production"
        pack.approval.status = "production"
        pack.approval.approver = username
        pack.approval.approved_at = datetime.now(UTC).date().isoformat()
        pack.approval.notes = f"Restored from v{source_version}"
        saved = save_governance_version(settings, pack=pack, reporting=None)
        if not state.get("active_reporting_version"):
            state["active_reporting_version"] = current_pin
        state["active_version"] = new_version
        _append_restore_history(
            state,
            version=new_version,
            username=username,
            target="dna",
            restored_from=source_version,
        )
        save_workflow_state(settings, state)
        return {
            "target": "dna",
            "version": new_version,
            "restored_from": source_version,
            "active_version": new_version,
            "active_reporting_version": state.get("active_reporting_version"),
            **{k: saved[k] for k in ("dna_path", "manifest_path") if k in saved},
        }

    current_pin = str(state.get("active_reporting_version") or "").strip()
    if not current_pin:
        current_pin = str(state.get("active_version") or "").strip()
    if not current_pin:
        raise ValueError("No active reporting production pin to restore from")
    if source_version == current_pin:
        raise ValueError(f"Reporting v{source_version} is already the production pin")
    payload = load_governance_reporting_payload(settings, pack_id, source_version)
    if payload is None:
        raise FileNotFoundError(
            f"No reporting snapshot found for {pack_id!r} v{source_version}"
        )

    new_version = bump_patch_version(current_pin)
    reporting = normalize_reporting_identity(
        settings,
        load_reporting_pack(payload),
        version=new_version,
        status="production",
    )
    saved = save_reporting_pack(
        settings,
        pack_id=pack_id,
        version=new_version,
        reporting=reporting,
        status="production",
    )
    state["active_reporting_version"] = new_version
    if not state.get("active_version"):
        state["active_version"] = current_pin
    _append_restore_history(
        state,
        version=new_version,
        username=username,
        target="reporting",
        restored_from=source_version,
    )
    save_workflow_state(settings, state)
    return {
        "target": "reporting",
        "version": new_version,
        "restored_from": source_version,
        "active_version": state.get("active_version"),
        "active_reporting_version": new_version,
        **{k: saved[k] for k in ("key", "path") if k in saved},
    }


def _append_restore_history(
    state: dict[str, Any],
    *,
    version: str,
    username: str,
    target: RestoreTarget,
    restored_from: str,
) -> None:
    history = state.get("history")
    if not isinstance(history, list):
        history = []
    label = "DNA" if target == "dna" else "reporting"
    history.append(
        {
            "version": version,
            "status": "production",
            "approver": username,
            "at": datetime.now(UTC).isoformat(),
            "notes": f"Restored {label} from v{restored_from}",
            "target": target,
            "restored_from": restored_from,
        }
    )
    state["history"] = history
