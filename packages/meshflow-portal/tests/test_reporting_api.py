"""Tests for gold binding catalog and generic reporting API."""

from __future__ import annotations

from pathlib import Path

import pytest

from meshflow.dna.init_client import init_client_governance
from meshflow.dna.schema import OutputSpec
from meshflow.dna.settings import DnaSettings
from meshflow.dna.web.portal.governance_helpers.gold_bindings import (
    build_reporting_binding_catalog,
    suggest_chart_binding,
    suggest_table_binding,
)
from meshflow.dna.web.portal.reporting_api import fetch_output_rows


@pytest.fixture
def seeded_settings(tmp_path: Path) -> DnaSettings:
    settings = DnaSettings(source="dbc", data_dir=tmp_path, company="POC")
    init_client_governance(settings, company="POC")
    return settings


def test_suggest_table_binding_for_fact_output() -> None:
    output = OutputSpec(
        id="out_fact_revenue_lines",
        output_type="table",
        build="join",
        columns=[
            "postingDate",
            "customerName",
            "netAmount",
        ],
    )
    binding = suggest_table_binding(output)
    assert binding is not None
    assert binding["source_output"] == "out_fact_revenue_lines"
    assert binding["sort"] == [{"column": "postingDate", "direction": "desc"}]
    assert binding["columns"][2]["numeric"] is True


def test_suggest_chart_binding_for_fact_output() -> None:
    output = OutputSpec(
        id="out_fact_revenue_lines",
        output_type="table",
        build="join",
        columns=["postingDate", "netAmount"],
    )
    binding = suggest_chart_binding(output)
    assert binding is not None
    assert binding["dimension"] == {"column": "postingDate", "grain": "month"}
    assert binding["measure"] == {"column": "netAmount", "aggregation": "sum"}


def test_build_reporting_binding_catalog(seeded_settings: DnaSettings) -> None:
    catalog = build_reporting_binding_catalog(seeded_settings)
    assert catalog["pack_id"]
    output_ids = {item["output_id"] for item in catalog["outputs"]}
    assert "out_fact_revenue_lines" in output_ids
    revenue = next(item for item in catalog["outputs"] if item["output_id"] == "out_fact_revenue_lines")
    assert revenue.get("suggested_table")
    assert revenue.get("suggested_chart")


def test_fetch_output_rows(seeded_settings: DnaSettings) -> None:
    result = fetch_output_rows(seeded_settings, "out_fact_revenue_lines", limit=10)
    assert result["output_id"] == "out_fact_revenue_lines"
    assert result["rows"] == []
