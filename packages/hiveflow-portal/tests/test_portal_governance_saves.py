"""Portal governance save / reporting layout integration tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from hiveflow.dna.settings import DnaSettings

def test_reporting_layout_drives_menu_and_source_outputs(tmp_path: Path) -> None:
    from hiveflow.dna.init_client import init_client_governance
    from hiveflow.dna.web.portal.reporting_layout import (
        find_reporting_page,
        page_source_output,
        reporting_data_menu,
        reporting_quick_links,
    )

    settings = DnaSettings(source="dbc", data_dir=tmp_path, company="POC")
    init_client_governance(settings, company="POC")

    menu = reporting_data_menu(settings)
    assert ("/portal", "Summary") in menu
    assert ("/portal/executive", "Executive") in menu
    assert ("/portal/revenue", "Order-to-cash detail") not in menu
    sales = next(item for item in menu if item[0] == "/portal/sales")
    assert ("/portal/revenue", "Order-to-cash detail") in sales[2]
    assert ("/portal/revenue-trend", "Revenue trend") in sales[2]

    links = reporting_quick_links(settings)
    assert all(path != "/portal" for path, _title, _desc in links)
    assert any(path == "/portal/executive" for path, _title, _desc in links)

    revenue = find_reporting_page(settings, "/portal/revenue")
    assert revenue is not None
    assert page_source_output(revenue, kind="table", default="x") == "out_fact_revenue_lines"
    assert find_reporting_page(settings, "/portal/not-configured") is None


def test_portal_save_keeps_reporting_config_id(tmp_path: Path) -> None:
    import yaml

    from hiveflow.dna.init_client import init_client_governance
    from hiveflow.dna.web.portal.governance_helpers.proposals import (
        bump_minor_version,
        bump_patch_version,
    )
    from hiveflow.dna.web.portal.views import save_governance_packs_from_portal
    from hiveflow.dna.reporting import load_production_reporting
    from hiveflow.dna.workflow import load_production_pack

    settings = DnaSettings(source="dbc", data_dir=tmp_path, company="POC")
    init_client_governance(settings, company="POC")
    dna = load_production_pack(settings)
    reporting = load_production_reporting(settings)
    next_version = bump_patch_version(dna.version)
    # Simulate a bad editor payload that used the DNA id for reporting.
    bad_reporting = dict(reporting)
    bad_reporting["pack_id"] = "poc_dna_config"

    result = save_governance_packs_from_portal(
        settings,
        dna_yaml=yaml.safe_dump(dna.to_dict(), sort_keys=False),
        reporting_yaml=yaml.safe_dump(bad_reporting, sort_keys=False),
        dna_version=next_version,
        reporting_version=next_version,
        pin_production=True,
        approver="Portal admin",
    )
    assert result["status"] == "saved"
    assert result["bump_kind"] == "patch"
    saved = load_production_reporting(settings)
    assert saved["pack_id"] == "poc_reporting_config"
    assert saved["version"] == next_version
    assert (
        tmp_path
        / "governance"
        / "poc_dna_config"
        / f"v{next_version}"
        / "poc_reporting_config.yaml"
    ).is_file()

    with pytest.raises(ValueError, match="next patch"):
        save_governance_packs_from_portal(
            settings,
            dna_yaml=yaml.safe_dump(dna.to_dict(), sort_keys=False),
            reporting_yaml=yaml.safe_dump(reporting, sort_keys=False),
            dna_version="9.9.9",
            reporting_version="9.9.9",
            pin_production=False,
            approver="Portal admin",
        )

    minor = bump_minor_version(next_version)
    minor_result = save_governance_packs_from_portal(
        settings,
        dna_yaml=yaml.safe_dump(dna.to_dict(), sort_keys=False),
        reporting_yaml=yaml.safe_dump(reporting, sort_keys=False),
        dna_version=minor,
        reporting_version=minor,
        pin_production=False,
        approver="Portal admin",
    )
    assert minor_result["bump_kind"] == "minor"
    assert "resets to 0" in minor_result["warning"]


def test_portal_save_independent_dna_and_reporting_versions(tmp_path: Path) -> None:
    import yaml

    from hiveflow.dna.init_client import init_client_governance
    from hiveflow.dna.web.portal.governance_helpers.proposals import bump_patch_version
    from hiveflow.dna.web.portal.views import save_governance_packs_from_portal
    from hiveflow.dna.reporting import (
        load_production_reporting,
        load_reporting_pack_from_governance,
        save_reporting_pack,
    )
    from hiveflow.dna.workflow import load_production_pack, load_workflow_state, save_workflow_state

    settings = DnaSettings(source="dbc", data_dir=tmp_path, company="POC")
    init_client_governance(settings, company="POC")
    dna = load_production_pack(settings)
    reporting = load_production_reporting(settings)
    state = load_workflow_state(settings, settings.dna_config_id)

    reporting_only = bump_patch_version(
        str(state.get("active_reporting_version") or state["active_version"])
    )
    save_reporting_pack(
        settings,
        pack_id=settings.dna_config_id,
        version=reporting_only,
        reporting=reporting,
        status="production",
    )
    state["active_reporting_version"] = reporting_only
    save_workflow_state(settings, state)

    dna_next = bump_patch_version(str(state["active_version"]))
    reporting_next = bump_patch_version(reporting_only)

    result = save_governance_packs_from_portal(
        settings,
        dna_yaml=yaml.safe_dump(dna.to_dict(), sort_keys=False),
        reporting_yaml=yaml.safe_dump(reporting, sort_keys=False),
        dna_version=dna_next,
        reporting_version=reporting_next,
        pin_production=True,
        approver="Portal admin",
    )
    assert result["dna_version"] == dna_next
    assert result["reporting_version"] == reporting_next
    assert dna_next != reporting_next

    state = load_workflow_state(settings, settings.dna_config_id)
    assert state["active_version"] == dna_next
    assert state["active_reporting_version"] == reporting_next

    saved_reporting = load_production_reporting(settings)
    assert saved_reporting["version"] == reporting_next
    assert load_reporting_pack_from_governance(settings, settings.dna_config_id, reporting_next)
    assert (
        tmp_path
        / "governance"
        / "poc_dna_config"
        / f"v{dna_next}"
        / "poc_dna_config.yaml"
    ).is_file()
    assert (
        tmp_path
        / "governance"
        / "poc_dna_config"
        / f"v{reporting_next}"
        / "poc_reporting_config.yaml"
    ).is_file()


def test_portal_manual_approve_dna_only(tmp_path: Path) -> None:
    import yaml

    from hiveflow.dna.init_client import init_client_governance
    from hiveflow.dna.web.portal.governance_helpers.proposals import bump_patch_version
    from hiveflow.dna.web.portal.views import save_governance_dna_from_portal
    from hiveflow.dna.reporting import load_production_reporting
    from hiveflow.dna.workflow import load_production_pack, load_workflow_state

    settings = DnaSettings(source="dbc", data_dir=tmp_path, company="POC")
    init_client_governance(settings, company="POC")
    dna = load_production_pack(settings)
    reporting_before = load_production_reporting(settings)
    state = load_workflow_state(settings, settings.dna_config_id)
    reporting_pin_before = str(
        state.get("active_reporting_version") or state.get("active_version") or ""
    )

    dna_next = bump_patch_version(str(state["active_version"]))
    result = save_governance_dna_from_portal(
        settings,
        dna_yaml=yaml.safe_dump(dna.to_dict(), sort_keys=False),
        dna_version=dna_next,
        pin_production=True,
        approver="Portal admin",
    )
    assert result["target"] == "dna"
    assert result["dna_version"] == dna_next

    state = load_workflow_state(settings, settings.dna_config_id)
    assert state["active_version"] == dna_next
    assert state.get("active_reporting_version") == reporting_pin_before

    reporting_after = load_production_reporting(settings)
    assert reporting_after["version"] == reporting_before["version"]
