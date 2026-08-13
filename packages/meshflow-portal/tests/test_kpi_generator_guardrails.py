"""Tests for KPI Generator silver merge and gold grain guardrails."""

from __future__ import annotations

from pathlib import Path

import pytest

from meshflow.dna.init_client import init_client_governance
from meshflow.dna.settings import DnaSettings
from meshflow.dna.silver_enhancement import (
    canonical_enhancement_file,
    contribution_sql_relative_path,
    load_contribution_sql,
)
from meshflow.dna.sql_pack import load_sql_pack
from meshflow.dna.store import write_json_artifact
from meshflow.dna.web.portal.kpi_generator.merge import merge_silver_enhancement
from meshflow.dna.web.portal.kpi_generator.service import (
    _validate_layer_rules,
    kpi_generator_proposal_key,
    save_kpi_governance_draft,
)


@pytest.fixture
def draft_settings(tmp_path: Path) -> DnaSettings:
    settings = DnaSettings(source="dbc", data_dir=tmp_path, company="poc")
    init_client_governance(settings, company="poc")
    return settings


def test_merge_silver_enhancement_single_contribution() -> None:
    settings = DnaSettings(source="dbc", data_dir=Path("."), company="poc")
    sql = "SELECT id, name, isInterco FROM silver_dbc_customers"
    merged = merge_silver_enhancement(
        settings,
        target_entity="customers",
        contributions={"add_is_interco": sql},
    )
    assert "isInterco" in merged


def test_save_silver_draft_writes_contribution_and_canonical_transform(
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
    version = result["version"]
    contrib = load_contribution_sql(
        settings,
        pack_id="poc_dna_config",
        version=version,
        target_entity="customers",
        kpi_id="add_isinterco_to_customers",
    )
    assert contrib is not None
    assert "isInterco" in contrib

    pack = load_sql_pack(settings, version=version)
    assert pack is not None
    silver = pack.by_layer("silver")
    assert len(silver) == 1
    assert silver[0].id == "enhance__customers"
    assert silver[0].file == canonical_enhancement_file("customers")


def test_save_second_silver_kpi_merges_into_same_canonical_transform(
    draft_settings: DnaSettings,
) -> None:
    settings = draft_settings
    write_json_artifact(
        settings,
        kpi_generator_proposal_key("poc_dna_config", "silver_a"),
        {
            "proposal_id": "silver_a",
            "status": "working",
            "draft": {
                "id": "add_col_a",
                "layer": "silver",
                "mode": "add_columns",
                "target_entity": "customers",
                "sql": "SELECT id, col_a AS colA FROM silver_dbc_customers",
            },
        },
    )
    save_kpi_governance_draft(settings, proposal_id="silver_a", username="tester")

    write_json_artifact(
        settings,
        kpi_generator_proposal_key("poc_dna_config", "silver_b"),
        {
            "proposal_id": "silver_b",
            "status": "working",
            "draft": {
                "id": "add_col_b",
                "layer": "silver",
                "mode": "add_columns",
                "target_entity": "customers",
                "sql": "SELECT id, col_b AS colB FROM silver_dbc_customers",
            },
        },
    )
    result = save_kpi_governance_draft(settings, proposal_id="silver_b", username="tester")
    pack = load_sql_pack(settings, version=result["version"])
    assert pack is not None
    assert len(pack.by_layer("silver")) == 1
    assert pack.by_layer("silver")[0].id == "enhance__customers"

    contrib_a = load_contribution_sql(
        settings,
        pack_id="poc_dna_config",
        version=result["version"],
        target_entity="customers",
        kpi_id="add_col_a",
    )
    contrib_b = load_contribution_sql(
        settings,
        pack_id="poc_dna_config",
        version=result["version"],
        target_entity="customers",
        kpi_id="add_col_b",
    )
    assert contrib_a is not None
    assert contrib_b is not None


def test_validate_layer_rules_rejects_duplicate_gold_grain() -> None:
    draft = {
        "layer": "gold",
        "mode": "kpi",
        "id": "kpi_b",
        "output_id": "out_b",
        "grain_columns": ["customerId"],
        "sql": "SELECT customerId, SUM(amount) AS value FROM silver_dbc_sales_orders GROUP BY customerId",
    }
    existing = [
        {
            "id": "kpi_a",
            "layer": "gold",
            "output_id": "out_a",
            "grain_columns": ["customerId"],
        }
    ]
    with pytest.raises(ValueError, match="already used"):
        _validate_layer_rules(draft, existing_gold_transforms=existing)


def test_validate_layer_rules_requires_gold_grain_columns() -> None:
    draft = {
        "layer": "gold",
        "mode": "kpi",
        "id": "kpi_total",
        "output_id": "out_total",
        "sql": "SELECT SUM(amount) AS value FROM silver_dbc_sales_orders",
    }
    with pytest.raises(ValueError, match="grain_columns"):
        _validate_layer_rules(draft)


def test_contribution_sql_relative_path() -> None:
    assert (
        contribution_sql_relative_path("customers", "add_is_interco")
        == "silver/contributions/customers/add_is_interco.sql"
    )


def test_group_pending_drafts_by_target() -> None:
    from meshflow.dna.web.portal.kpi_generator.integrity import (
        draft_target_key,
        group_pending_drafts,
    )

    proposals = [
        {
            "proposal_id": "a",
            "draft": {"layer": "silver", "mode": "add_columns", "target_entity": "customers", "id": "k1"},
        },
        {
            "proposal_id": "b",
            "draft": {"layer": "silver", "mode": "add_columns", "target_entity": "customers", "id": "k2"},
        },
        {
            "proposal_id": "c",
            "draft": {"layer": "gold", "mode": "kpi", "output_id": "out_rev", "id": "k3"},
        },
    ]
    groups = group_pending_drafts(proposals)
    assert draft_target_key(proposals[0]["draft"]) == "silver:customers"
    assert len(groups["silver:customers"]) == 2
    assert len(groups["gold:out_rev"]) == 1


def test_approve_group_requires_prior_integrity_validation(
    draft_settings: DnaSettings,
) -> None:
    from meshflow.dna.store import write_json_artifact
    from meshflow.dna.web.portal.kpi_generator.service import (
        approve_kpi_draft_group,
        kpi_generator_proposal_key,
    )

    settings = draft_settings
    write_json_artifact(
        settings,
        kpi_generator_proposal_key("poc_dna_config", "pending_no_integrity"),
        {
            "proposal_id": "pending_no_integrity",
            "status": "pending_review",
            "draft": {
                "id": "add_col",
                "layer": "silver",
                "mode": "add_columns",
                "target_entity": "customers",
                "sql": "SELECT id, name FROM silver_dbc_customers",
            },
        },
    )
    with pytest.raises(ValueError, match="Integrity validation has not passed"):
        approve_kpi_draft_group(
            settings,
            target_key="silver:customers",
            proposal_ids=["pending_no_integrity"],
            username="tester",
        )
