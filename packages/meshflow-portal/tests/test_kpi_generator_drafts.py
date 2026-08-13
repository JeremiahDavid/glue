"""KPI Generator draft review workflow tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from meshflow.dna.init_client import init_client_governance
from meshflow.dna.settings import DnaSettings
from meshflow.dna.store import write_json_artifact
from meshflow.dna.web.portal.kpi_generator.render import render_kpi_generator_body
from meshflow.dna.web.portal.kpi_generator.service import (
    _normalize_sql_file_path,
    discard_kpi_proposal,
    find_working_kpi_proposal,
    kpi_generator_proposal_key,
    list_kpi_pending_drafts,
    reject_kpi_proposal,
    save_kpi_governance_draft,
    save_validation_criteria,
    update_kpi_draft_sql,
    validation_criteria_from_proposal,
)


@pytest.fixture
def draft_settings(tmp_path: Path) -> DnaSettings:
    settings = DnaSettings(source="dbc", data_dir=tmp_path, company="poc")
    init_client_governance(settings, company="poc")
    return settings


def test_normalize_sql_file_path_adds_layer_prefix() -> None:
    assert _normalize_sql_file_path(
        "silver",
        "add_isInterco_to_customers.sql",
        "add_isInterco_to_customers",
    ) == "silver/add_isInterco_to_customers.sql"
    assert _normalize_sql_file_path(
        "gold",
        "kpi_net_revenue",
        "kpi_net_revenue",
    ) == "gold/kpi_net_revenue.sql"
    assert _normalize_sql_file_path(
        "silver",
        "silver/add_gp.sql",
        "add_gp",
    ) == "silver/add_gp.sql"


def test_save_kpi_governance_draft_normalizes_unqualified_file_path(
    draft_settings: DnaSettings,
) -> None:
    settings = draft_settings
    write_json_artifact(
        settings,
        kpi_generator_proposal_key("poc_dna_config", "silver1"),
        {
            "proposal_id": "silver1",
            "status": "working",
            "draft": {
                "id": "add_isInterco_to_customers",
                "layer": "silver",
                "mode": "add_columns",
                "target_entity": "customers",
                "file": "add_isInterco_to_customers.sql",
                "sql": "SELECT id, name, isInterco FROM silver_dbc_customers",
            },
        },
    )
    result = save_kpi_governance_draft(
        settings,
        proposal_id="silver1",
        username="tester",
    )
    assert result["status"] == "pending_review"
    assert result["sql_file"] == "silver/contributions/customers/add_isinterco_to_customers.sql"


def test_list_kpi_pending_drafts_filters_status(draft_settings: DnaSettings) -> None:
    settings = draft_settings
    write_json_artifact(
        settings,
        kpi_generator_proposal_key("poc_dna_config", "pending1"),
        {
            "proposal_id": "pending1",
            "status": "pending_review",
            "created_at": "2026-01-02T00:00:00+00:00",
            "draft": {"id": "KPI-A", "layer": "gold", "mode": "kpi"},
        },
    )
    write_json_artifact(
        settings,
        kpi_generator_proposal_key("poc_dna_config", "working1"),
        {
            "proposal_id": "working1",
            "status": "working",
            "created_at": "2026-01-01T00:00:00+00:00",
            "draft": {"id": "KPI-B", "layer": "gold", "mode": "kpi"},
        },
    )
    pending = list_kpi_pending_drafts(settings)
    assert len(pending) == 1
    assert pending[0]["proposal_id"] == "pending1"


def test_reject_kpi_proposal_marks_rejected(draft_settings: DnaSettings) -> None:
    settings = draft_settings
    write_json_artifact(
        settings,
        kpi_generator_proposal_key("poc_dna_config", "pending2"),
        {
            "proposal_id": "pending2",
            "status": "pending_review",
            "draft": {"id": "KPI-C", "layer": "gold", "mode": "kpi"},
        },
    )
    result = reject_kpi_proposal(settings, proposal_id="pending2", username="tester")
    assert result["status"] == "rejected"
    assert list_kpi_pending_drafts(settings) == []


def test_discard_kpi_proposal_marks_discarded(draft_settings: DnaSettings) -> None:
    settings = draft_settings
    write_json_artifact(
        settings,
        kpi_generator_proposal_key("poc_dna_config", "working2"),
        {
            "proposal_id": "working2",
            "status": "working",
            "chat_history": [{"role": "user", "text": "test"}],
            "draft": {"id": "KPI-D", "layer": "gold", "mode": "kpi", "output_id": "out_d", "sql": "SELECT 1"},
        },
    )
    result = discard_kpi_proposal(settings, proposal_id="working2", username="tester")
    assert result["status"] == "discarded"


def test_update_kpi_draft_sql_persists_edits(draft_settings: DnaSettings) -> None:
    settings = draft_settings
    write_json_artifact(
        settings,
        kpi_generator_proposal_key("poc_dna_config", "edit1"),
        {
            "proposal_id": "edit1",
            "status": "working",
            "draft": {
                "id": "KPI-EDIT",
                "layer": "gold",
                "mode": "kpi",
                "output_id": "out_edit",
                "sql": "SELECT 1",
            },
        },
    )
    updated = update_kpi_draft_sql(
        settings,
        proposal_id="edit1",
        sql="SELECT SUM(amount) AS value FROM silver_dbc_sales_orders",
    )
    assert "SUM(amount)" in updated["draft"]["sql"]


def test_review_tab_renders_pending_draft_rows() -> None:
    settings = DnaSettings(source="dbc", data_dir=Path("."), company="poc")
    pending = [
        {
            "proposal_id": "abc123",
            "status": "pending_review",
            "governance_version": "1.0.1",
            "prompt": "Net revenue",
            "draft": {
                "id": "KPI-TEST",
                "layer": "gold",
                "mode": "kpi",
                "output_id": "out_test",
                "calculation": "SUM(x)",
                "sql": "SELECT 1 FROM silver_dbc_sales_orders",
            },
        }
    ]
    html = render_kpi_generator_body(
        settings=settings,
        url=lambda p: p,
        is_admin=True,
        active_tab="review",
        pending_drafts=pending,
    )
    assert "Review Drafts (1)" in html
    assert "kpi-kanban-board" in html
    assert "kpi-kanban-pillar" in html
    assert "kpi-kanban-lane" in html
    assert "Integrity Validation" in html
    assert "Publish Approved KPIs" in html
    assert 'data-stage="integrity"' in html
    assert "kpi-kanban-tile" in html
    assert 'id="kpi-generator-panel-review"' in html
    assert 'role="tabpanel">' in html


def test_review_tab_portal_footer_stays_inside_main_column() -> None:
    """Regression: malformed review tabpanel HTML used to eject the portal footer."""
    from bs4 import BeautifulSoup

    from meshflow.dna.web.theme import render_portal_page

    settings = DnaSettings(source="dbc", data_dir=Path("."), company="poc")
    body = render_kpi_generator_body(
        settings=settings,
        url=lambda p: p,
        is_admin=True,
        active_tab="review",
        pending_drafts=[
            {
                "proposal_id": "abc123",
                "status": "pending_review",
                "draft": {
                    "id": "KPI-TEST",
                    "layer": "silver",
                    "mode": "add",
                    "target_entity": "customers",
                },
            }
        ],
    )
    class _Client:
        display_name = "POC"

    page = render_portal_page(
        title="KPI",
        active_path="/portal/dna/kpi-generator",
        body=body,
        nav_links=(),
        client=_Client(),
        url=lambda p: p,
        side_nav_title="DNA",
        side_nav_items=(("KPI Generator", "/portal/dna/kpi-generator"),),
        side_nav_id="dna-nav",
    )
    soup = BeautifulSoup(page, "html.parser")
    footer = soup.select_one("footer.portal-footer")
    portal_main = soup.select_one(".portal-main")
    assert footer is not None
    assert portal_main is not None
    assert footer.parent == portal_main


def test_review_tab_enables_approve_when_integrity_passed() -> None:
    settings = DnaSettings(source="dbc", data_dir=Path("."), company="poc")
    pending = [
        {
            "proposal_id": "abc123",
            "status": "pending_review",
            "integrity_validation": {
                "status": "passed",
                "target_key": "gold:out_test",
            },
            "draft": {
                "id": "KPI-TEST",
                "layer": "gold",
                "mode": "kpi",
                "output_id": "out_test",
                "sql": "SELECT 1 FROM silver_dbc_sales_orders",
            },
        }
    ]
    html = render_kpi_generator_body(
        settings=settings,
        url=lambda p: p,
        is_admin=True,
        active_tab="review",
        pending_drafts=pending,
    )
    assert 'value="approve"' in html
    assert 'data-stage="approve"' in html
    assert "KPI-TEST" in html
    assert "data-kpi-panel" in html
    assert "Next governance version" in html


def test_review_tab_publish_toolbar_for_approved_drafts() -> None:
    settings = DnaSettings(source="dbc", data_dir=Path("."), company="poc")
    html = render_kpi_generator_body(
        settings=settings,
        url=lambda p: p,
        is_admin=True,
        active_tab="review",
        pending_drafts=[],
        approved_drafts=[
            {
                "proposal_id": "pub1",
                "status": "approved",
                "approved_version": "1.0.2",
                "draft": {
                    "id": "KPI-SILVER",
                    "layer": "silver",
                    "mode": "add_columns",
                    "target_entity": "customers",
                    "sql": "SELECT id FROM silver_dbc_customers",
                },
            }
        ],
    )
    assert 'value="publish_approved"' in html
    assert "Publish Approved KPIs (1)" in html
    assert "Ready to publish" in html
    assert 'data-stage="integrity"' not in html or "kpi-kanban-pillar" in html


def test_classify_proposal_stage() -> None:
    from meshflow.dna.web.portal.kpi_generator.integrity import (
        classify_proposal_stage,
        partition_proposals_by_stage,
    )

    pending = {
        "proposal_id": "a",
        "status": "pending_review",
        "draft": {"layer": "gold", "mode": "kpi", "output_id": "out_a", "id": "k1"},
    }
    assert classify_proposal_stage(pending) == "integrity"

    passed = {
        "proposal_id": "b",
        "status": "pending_review",
        "integrity_validation": {"status": "passed", "target_key": "gold:out_b"},
        "draft": {"layer": "gold", "mode": "kpi", "output_id": "out_b", "id": "k2"},
    }
    assert classify_proposal_stage(passed) == "approve"

    staged = partition_proposals_by_stage([pending, passed])
    assert len(staged["integrity"]) == 1
    assert len(staged["approve"]) == 1


def test_save_validation_criteria_persists_filters(draft_settings: DnaSettings) -> None:
    settings = draft_settings
    write_json_artifact(
        settings,
        kpi_generator_proposal_key("poc_dna_config", "criteria1"),
        {
            "proposal_id": "criteria1",
            "status": "working",
            "draft": {"id": "KPI-C", "layer": "gold", "mode": "kpi", "sql": "SELECT 1"},
            "last_validation": {
                "filters": [{"fact": "sales_orders", "field": "id", "value": "SO-1"}],
                "result": {"columns": ["value"], "rows": []},
                "validated_at": "2026-01-01T00:00:00+00:00",
            },
        },
    )
    updated = save_validation_criteria(
        settings,
        proposal_id="criteria1",
        filters=[{"fact": "customers", "field": "id", "value": "C-9"}],
    )
    last_val = updated["last_validation"]
    assert last_val["filters"] == [{"fact": "customers", "field": "id", "value": "C-9"}]
    assert "result" not in last_val
    assert "validated_at" not in last_val


def test_find_working_kpi_proposal_returns_most_recent(draft_settings: DnaSettings) -> None:
    settings = draft_settings
    write_json_artifact(
        settings,
        kpi_generator_proposal_key("poc_dna_config", "older"),
        {
            "proposal_id": "older",
            "status": "working",
            "created_at": "2026-01-01T00:00:00+00:00",
            "draft": {"id": "OLD", "layer": "gold", "mode": "kpi", "sql": "SELECT 1"},
        },
    )
    write_json_artifact(
        settings,
        kpi_generator_proposal_key("poc_dna_config", "newer"),
        {
            "proposal_id": "newer",
            "status": "working",
            "created_at": "2026-01-02T00:00:00+00:00",
            "draft": {"id": "NEW", "layer": "gold", "mode": "kpi", "sql": "SELECT 2"},
        },
    )
    working = find_working_kpi_proposal(settings)
    assert working is not None
    assert working["proposal_id"] == "newer"


def test_validation_criteria_from_proposal_returns_filters_only() -> None:
    criteria = validation_criteria_from_proposal(
        {
            "last_validation": {
                "filters": [{"fact": "sales_orders", "field": "id", "value": "SO-1"}],
                "result": {"columns": ["value"], "rows": []},
            }
        }
    )
    assert criteria == {
        "filters": [{"fact": "sales_orders", "field": "id", "value": "SO-1"}]
    }
    assert validation_criteria_from_proposal({"last_validation": {"filters": []}}) is None
