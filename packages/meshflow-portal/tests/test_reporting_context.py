"""Tests for Config Assistant reporting layout context."""

from __future__ import annotations

from pathlib import Path

import pytest

from meshflow.dna.init_client import init_client_governance
from meshflow.dna.settings import DnaSettings
from meshflow.dna.web.portal.config_assistant.bedrock_chat import run_tool, system_prompt
from meshflow.dna.web.portal.config_assistant.reporting_context import (
    REPORTING_LAYOUT_COOKBOOK,
    build_kpi_binding_hints,
    build_reporting_assistant_context,
)


@pytest.fixture
def seeded_settings(tmp_path: Path) -> DnaSettings:
    settings = DnaSettings(source="dbc", data_dir=tmp_path, company="POC")
    init_client_governance(settings, company="POC")
    return settings


def test_reporting_layout_cookbook_covers_ranked_table_dim_join() -> None:
    assert "ranked_table" in REPORTING_LAYOUT_COOKBOOK
    assert "dim_join" in REPORTING_LAYOUT_COOKBOOK
    assert "dim_id_column" in REPORTING_LAYOUT_COOKBOOK
    assert "label_columns" in REPORTING_LAYOUT_COOKBOOK


def test_build_kpi_binding_hints(seeded_settings: DnaSettings) -> None:
    hints = build_kpi_binding_hints(seeded_settings)
    assert hints
    executive = next(item for item in hints if item["output_id"] == "out_executive_kpis")
    assert executive["kpis"]
    assert any(kpi["kpi_id"].startswith("KPI-") for kpi in executive["kpis"])


def test_build_reporting_assistant_context(seeded_settings: DnaSettings) -> None:
    ctx = build_reporting_assistant_context(seeded_settings)
    assert "layout_cookbook" in ctx
    assert "kpi_binding_hints" in ctx
    assert ctx["kpi_binding_hints"]


def test_system_prompt_includes_reporting_cookbook(seeded_settings: DnaSettings) -> None:
    prompt = system_prompt(
        seeded_settings,
        base_version="1.0.0",
        next_version="1.0.1",
    )
    assert "Reporting layout cookbook" in prompt
    assert "ranked_table" in prompt
    assert "dim_join" in prompt
    assert "KPI binding hints" in prompt
    assert "Published field semantics" in prompt


def test_run_tool_get_reporting_layout_cookbook(seeded_settings: DnaSettings) -> None:
    payload = run_tool(seeded_settings, "get_reporting_layout_cookbook")
    assert "layout_cookbook" in payload
    assert "kpi_binding_hints" in payload
    assert "out_executive_kpis" in payload
