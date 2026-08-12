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
    kpi_generator_proposal_key,
    list_kpi_pending_drafts,
    reject_kpi_proposal,
    save_kpi_governance_draft,
    update_kpi_draft_sql,
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
    assert result["sql_file"] == "silver/add_isInterco_to_customers.sql"


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
    assert "kpi-draft-item" in html
    assert "Approve all" in html
    assert "KPI-TEST" in html
