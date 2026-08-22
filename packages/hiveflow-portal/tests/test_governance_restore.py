from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from meshflow.dna.governance import load_governance_dna, save_governance_version
from meshflow.dna.init_client import init_client_governance
from meshflow.dna.settings import DnaSettings
from meshflow.dna.web.portal.governance_helpers.proposals import bump_patch_version
from meshflow.dna.web.portal.governance_restore import (
    governance_target_snapshot_exists,
    restore_governance_target,
)
from meshflow.dna.web.portal.views import _history_table_rows
from meshflow.dna.reporting import (
    load_production_reporting,
    load_reporting_pack_from_governance,
    normalize_reporting_identity,
    save_reporting_pack,
)
from meshflow.dna.workflow import load_production_pack, load_workflow_state, save_workflow_state


@pytest.fixture
def seeded_settings(tmp_path: Path) -> DnaSettings:
    settings = DnaSettings(source="dbc", data_dir=tmp_path, company="POC")
    init_client_governance(settings, company="POC")
    return settings


def _append_history(
    state: dict,
    *,
    version: str,
    target: str,
    username: str = "admin",
    notes: str = "",
) -> None:
    history = state.get("history")
    if not isinstance(history, list):
        history = []
    history.append(
        {
            "version": version,
            "status": "production",
            "approver": username,
            "at": datetime.now(UTC).isoformat(),
            "notes": notes or f"Test {target} bump",
            "target": target,
        }
    )
    state["history"] = history


def _pin_dna_with_description(settings: DnaSettings, description: str) -> str:
    state = load_workflow_state(settings, settings.dna_config_id)
    current = str(state.get("active_version") or "")
    new_version = bump_patch_version(current)
    pack = load_production_pack(settings)
    pack.version = new_version
    pack.description = description
    pack.status = "production"
    pack.approval.status = "production"
    pack.approval.approver = "admin"
    save_governance_version(settings, pack=pack, reporting=None)
    state["active_version"] = new_version
    if not state.get("active_reporting_version"):
        state["active_reporting_version"] = current
    _append_history(state, version=new_version, target="dna", notes="DNA content bump")
    save_workflow_state(settings, state)
    return new_version


def _pin_reporting_with_description(settings: DnaSettings, description: str) -> str:
    state = load_workflow_state(settings, settings.dna_config_id)
    current = str(
        state.get("active_reporting_version") or state.get("active_version") or ""
    )
    new_version = bump_patch_version(current)
    reporting = normalize_reporting_identity(
        settings,
        load_production_reporting(settings),
        version=new_version,
        status="production",
    )
    reporting["description"] = description
    save_reporting_pack(
        settings,
        pack_id=settings.dna_config_id,
        version=new_version,
        reporting=reporting,
        status="production",
    )
    state["active_reporting_version"] = new_version
    if not state.get("active_version"):
        state["active_version"] = current
    _append_history(
        state, version=new_version, target="reporting", notes="Reporting content bump"
    )
    save_workflow_state(settings, state)
    return new_version


def test_restore_dna_forward_pins_and_preserves_reporting(
    seeded_settings: DnaSettings,
) -> None:
    state = load_workflow_state(seeded_settings, "poc_dna_config")
    source_version = str(state["active_version"])
    source_pack = load_governance_dna(seeded_settings, "poc_dna_config", source_version)
    source_description = source_pack.description
    reporting_pin_before = str(
        state.get("active_reporting_version") or state["active_version"]
    )

    bumped = _pin_dna_with_description(seeded_settings, "changed dna description")
    assert bumped != source_version
    assert load_production_pack(seeded_settings).description == "changed dna description"

    result = restore_governance_target(
        seeded_settings,
        target="dna",
        source_version=source_version,
        username="restorer",
    )
    assert result["target"] == "dna"
    assert result["restored_from"] == source_version
    assert result["version"] == bump_patch_version(bumped)

    state = load_workflow_state(seeded_settings, "poc_dna_config")
    assert state["active_version"] == result["version"]
    assert state["active_reporting_version"] == reporting_pin_before

    restored = load_production_pack(seeded_settings)
    assert restored.version == result["version"]
    assert restored.description == source_description
    assert restored.approval.status == "production"
    assert restored.approval.approver == "restorer"

    history = state["history"]
    assert history[-1]["target"] == "dna"
    assert history[-1]["restored_from"] == source_version
    assert history[-1]["version"] == result["version"]
    assert "Restored DNA from" in history[-1]["notes"]


def test_restore_reporting_forward_pins_and_preserves_dna(
    seeded_settings: DnaSettings,
) -> None:
    state = load_workflow_state(seeded_settings, "poc_dna_config")
    source_version = str(
        state.get("active_reporting_version") or state["active_version"]
    )
    source_reporting = load_reporting_pack_from_governance(
        seeded_settings, "poc_dna_config", source_version
    )
    source_description = source_reporting.get("description")
    dna_pin_before = str(state["active_version"])

    bumped = _pin_reporting_with_description(
        seeded_settings, "changed reporting description"
    )
    assert bumped != source_version
    assert (
        load_production_reporting(seeded_settings)["description"]
        == "changed reporting description"
    )

    result = restore_governance_target(
        seeded_settings,
        target="reporting",
        source_version=source_version,
        username="restorer",
    )
    assert result["target"] == "reporting"
    assert result["restored_from"] == source_version
    assert result["version"] == bump_patch_version(bumped)

    state = load_workflow_state(seeded_settings, "poc_dna_config")
    assert state["active_reporting_version"] == result["version"]
    assert state["active_version"] == dna_pin_before

    restored = load_production_reporting(seeded_settings)
    assert restored["version"] == result["version"]
    assert restored["description"] == source_description
    assert restored["status"] == "production"

    history = state["history"]
    assert history[-1]["target"] == "reporting"
    assert history[-1]["restored_from"] == source_version


def test_restore_rejects_current_pin(seeded_settings: DnaSettings) -> None:
    state = load_workflow_state(seeded_settings, "poc_dna_config")
    current = str(state["active_version"])
    with pytest.raises(ValueError, match="already the production pin"):
        restore_governance_target(
            seeded_settings,
            target="dna",
            source_version=current,
            username="admin",
        )


def test_restore_rejects_missing_snapshot(seeded_settings: DnaSettings) -> None:
    with pytest.raises(FileNotFoundError, match="No DNA snapshot"):
        restore_governance_target(
            seeded_settings,
            target="dna",
            source_version="9.9.9",
            username="admin",
        )
    with pytest.raises(FileNotFoundError, match="No reporting snapshot"):
        restore_governance_target(
            seeded_settings,
            target="reporting",
            source_version="9.9.9",
            username="admin",
        )


def test_snapshot_exists_helper(seeded_settings: DnaSettings) -> None:
    state = load_workflow_state(seeded_settings, "poc_dna_config")
    version = str(state["active_version"])
    assert governance_target_snapshot_exists(
        seeded_settings, target="dna", version=version
    )
    assert governance_target_snapshot_exists(
        seeded_settings, target="reporting", version=version
    )
    assert not governance_target_snapshot_exists(
        seeded_settings, target="dna", version="0.0.0"
    )


def test_history_table_rows_revert_controls(seeded_settings: DnaSettings) -> None:
    state = load_workflow_state(seeded_settings, "poc_dna_config")
    source_version = str(state["active_version"])
    bumped = _pin_dna_with_description(seeded_settings, "newer dna")
    history = [
        {"version": source_version, "status": "production", "approver": "a", "notes": "seed"},
        {"version": bumped, "status": "production", "approver": "b", "notes": "bump", "target": "dna"},
    ]

    admin_rows = _history_table_rows(
        history,
        pack_kind="dna",
        active_version=bumped,
        is_admin=True,
        form_action="/portal/governance",
        settings=seeded_settings,
    )
    assert "Revert" in admin_rows
    assert f'value="{source_version}"' in admin_rows
    assert "restore_dna" in admin_rows
    assert "Current" in admin_rows
    assert f'value="{bumped}"' not in admin_rows or admin_rows.count("Revert") == 1

    viewer_rows = _history_table_rows(
        history,
        pack_kind="dna",
        active_version=bumped,
        is_admin=False,
        form_action="/portal/governance",
        settings=seeded_settings,
    )
    assert "Revert" not in viewer_rows
    assert "Current" not in viewer_rows
    assert "Actions" not in viewer_rows
