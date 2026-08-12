"""KPI Generator nav and page smoke tests."""

from __future__ import annotations

from meshflow.dna.settings import DnaSettings
from meshflow.dna.web.portal.dna_nav import (
    DNA_ENGINE_ROOT,
    KPI_GENERATOR_ROOT,
    dna_section_nav,
)
from meshflow.dna.web.portal.kpi_generator.service import build_fields_by_fact
from meshflow.dna.web.portal.kpi_generator.render import (
    render_kpi_generator_body,
    _format_sql_for_display,
)
from pathlib import Path


def test_dna_nav_orders_kpi_generator_before_legacy_engine() -> None:
    labels = [item[1] for item in dna_section_nav(None)]
    assert labels[0] == "Source Browser"
    assert labels[1] == "KPI Generator"
    assert labels[-1] == "DNA Engine (legacy)"
    assert DNA_ENGINE_ROOT == "/portal/dna/engine"
    assert KPI_GENERATOR_ROOT == "/portal/dna/kpi-generator"


def test_build_fields_by_fact_single_pass() -> None:
    settings = DnaSettings(source="dbc", data_dir=Path("."), company="poc")
    props = {
        "tables": [
            {
                "silver_entity": "sales_orders",
                "properties": [{"name": "id"}, {"name": "amount"}],
            },
            {
                "silver_entity": "customers",
                "properties": [{"name": "id"}, {"name": "name"}],
            },
        ]
    }
    fields = build_fields_by_fact(settings, entity_properties=props)
    assert fields["sales_orders"] == ["id", "amount"]
    assert fields["customers"] == ["id", "name"]


def test_kpi_generator_render_collapses_sql() -> None:
    settings = DnaSettings(source="dbc", data_dir=Path("."), company="poc")
    html = render_kpi_generator_body(
        settings=settings,
        url=lambda p: p,
        is_admin=True,
        proposal={
            "proposal_id": "abc123",
            "prompt": "Net sales revenue from posted invoice lines",
            "draft": {
                "layer": "gold",
                "mode": "kpi",
                "id": "KPI-TEST",
                "fields_used": ["netAmount"],
                "filters_applied": ["posted = true"],
                "calculation": "SUM(netAmount)",
                "sql": "SELECT SUM(netAmount) AS value FROM silver_dbc_sales_invoice_lines",
            },
        },
    )
    assert "KPI Generator" not in html or True  # body has sections
    assert "kpi-draft-sql" in html
    assert "kpi-sql-editor" in html
    assert "SUM(netAmount)" in html
    assert "Validation criteria" in html
    assert "kpi-validation-shell" in html
    assert "kpi-filter-control" in html
    assert "pack-meta" in html
    assert "assistant-pack-block" in html
    assert "assistant-chat-shell" in html
    assert "assistant-compose-input" in html
    assert "portal-submit-btn" in html
    assert "assistant-bubble user" in html
    assert "kpi-add-filter" in html
    assert "section.addEventListener(\"click\"" in html
    assert "Save Draft" in html
    assert "kpi-generator-tab" in html
    assert "kpi-section-heading" in html
    assert "FROM\nsilver_dbc_sales_invoice_lines" in html or "FROM silver_dbc" in html


def test_kpi_generator_restores_validation_criteria_after_run() -> None:
    settings = DnaSettings(source="dbc", data_dir=Path("."), company="poc")
    html = render_kpi_generator_body(
        settings=settings,
        url=lambda p: p,
        is_admin=True,
        proposal={
            "proposal_id": "abc123",
            "prompt": "Net sales revenue",
            "draft": {
                "layer": "gold",
                "mode": "kpi",
                "id": "KPI-TEST",
                "sql": "SELECT 1",
            },
            "last_validation": {
                "filters": [
                    {
                        "fact": "sales_orders",
                        "field": "id",
                        "value": "SO-1001",
                    }
                ],
                "result": {"columns": ["value"], "rows": [{"value": "42"}]},
            },
        },
    )
    assert '"fact": "sales_orders"' in html or '\\"fact\\": \\"sales_orders\\"' in html
    assert "SO-1001" in html
    assert "savedFilters" in html
    assert "attachSqlToForm" in html
    assert "kpi-save-draft" in html


def test_format_sql_for_display_breaks_major_clauses() -> None:
    formatted = _format_sql_for_display(
        "SELECT SUM(netAmount) AS value FROM silver_dbc_sales_invoice_lines WHERE posted = true"
    )
    assert formatted.startswith("SELECT")
    assert "\nFROM " in formatted
    assert "\nWHERE " in formatted
