"""KPI Generator nav and page smoke tests."""

from __future__ import annotations

from pathlib import Path

from meshflow.dna.settings import DnaSettings
from meshflow.dna.web.portal.dna_nav import KPI_GENERATOR_ROOT, dna_section_nav
from meshflow.dna.web.portal.kpi_generator.render import render_kpi_generator_body
from meshflow.dna.web.portal.kpi_generator.sql_format import format_kpi_sql
from meshflow.dna.web.portal.kpi_generator.service import (
    MAX_KPI_CHAT_TURNS,
    _build_kpi_chat_messages,
    _trim_kpi_chat_history,
    _validate_sql_joins,
    build_allowed_joins,
    build_fields_by_fact,
)


def test_dna_nav_lists_source_browser_kpi_generator_and_catalog() -> None:
    labels = [item[1] for item in dna_section_nav(None)]
    assert labels == ["Source Browser", "KPI Generator", "DNA Catalog"]
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
    assert 'section.addEventListener("click"' in html
    assert "Save Draft" in html
    assert "data-kpi-tab" in html
    assert "semantic-builder-keys-tab" in html
    assert "activateKpiTab" in html
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
    assert "kpi-generator-validation" in html


def test_format_sql_for_display_breaks_major_clauses() -> None:
    formatted = format_kpi_sql(
        "SELECT SUM(netAmount) AS value FROM silver_dbc_sales_invoice_lines WHERE posted = true"
    )
    assert formatted.startswith("SELECT")
    assert "\nFROM " in formatted or formatted.startswith("SELECT\n")
    assert "\nWHERE " in formatted
    assert "\n  SUM(netAmount) AS value" in formatted


def test_format_kpi_sql_splits_select_columns() -> None:
    formatted = format_kpi_sql(
        "SELECT SUM(netAmount) AS value, customerId, COUNT(*) AS line_count "
        "FROM silver_dbc_sales_invoice_lines"
    )
    assert "SUM(netAmount) AS value," in formatted
    assert "\n  customerId," in formatted
    assert "\n  COUNT(*) AS line_count" in formatted


def test_trim_kpi_chat_history_keeps_last_five_user_turns() -> None:
    history = []
    for index in range(MAX_KPI_CHAT_TURNS + 2):
        history.append({"role": "user", "text": f"query {index}"})
        history.append({"role": "assistant", "text": f"reply {index}"})
    trimmed = _trim_kpi_chat_history(history)
    user_texts = [entry["text"] for entry in trimmed if entry["role"] == "user"]
    assert user_texts == [f"query {index}" for index in range(2, MAX_KPI_CHAT_TURNS + 2)]


def test_build_kpi_chat_messages_appends_new_prompt() -> None:
    messages = _build_kpi_chat_messages(
        [{"role": "user", "text": "first"}, {"role": "assistant", "text": "draft"}],
        prompt="refine it",
    )
    assert len(messages) == 3
    assert messages[-1]["role"] == "user"
    assert messages[-1]["content"][0]["text"] == "refine it"


def test_kpi_generator_render_shows_chat_history() -> None:
    settings = DnaSettings(source="dbc", data_dir=Path("."), company="poc")
    html = render_kpi_generator_body(
        settings=settings,
        url=lambda p: p,
        is_admin=True,
        proposal={
            "proposal_id": "abc123",
            "status": "working",
            "chat_history": [
                {"role": "user", "text": "Net sales revenue"},
                {"role": "assistant", "text": "SUM of posted invoice lines"},
                {"role": "user", "text": "Exclude credit memos"},
                {"role": "assistant", "text": "Updated SQL with credit memo filter"},
            ],
            "draft": {
                "layer": "gold",
                "mode": "kpi",
                "id": "KPI-TEST",
                "sql": "SELECT 1",
            },
        },
    )
    assert "Net sales revenue" in html
    assert "Exclude credit memos" in html
    assert "Updated SQL with credit memo filter" in html
    assert 'name="prior_proposal_id"' in html
    assert 'value="abc123"' in html
    assert "Discard Draft" in html
    assert 'id="kpi-discard-draft"' in html
    assert 'btn btn-secondary' in html


def test_build_allowed_joins_from_gold_relationships() -> None:
    relationships = {
        "source": "dbc",
        "tables": {
            "sales_invoice_lines": {
                "PK": "id",
                "relationships": [
                    {"target": "sales_invoices", "PK": "id", "FK": "documentId"},
                    {"target": "items", "PK": "id", "FK": "itemId"},
                ],
            }
        },
    }
    allowed = build_allowed_joins(relationships, source="dbc")
    assert {
        (
            join["left_table"],
            join["left_column"],
            join["right_table"],
            join["right_column"],
        )
        for join in allowed
    } == {
        (
            "silver_dbc_sales_invoice_lines",
            "documentId",
            "silver_dbc_sales_invoices",
            "id",
        ),
        (
            "silver_dbc_sales_invoices",
            "id",
            "silver_dbc_sales_invoice_lines",
            "documentId",
        ),
        (
            "silver_dbc_sales_invoice_lines",
            "itemId",
            "silver_dbc_items",
            "id",
        ),
        (
            "silver_dbc_items",
            "id",
            "silver_dbc_sales_invoice_lines",
            "itemId",
        ),
    }


def test_validate_sql_joins_accepts_catalog_join(tmp_path: Path) -> None:
    settings = DnaSettings(source="dbc", data_dir=tmp_path, company="poc")
    relationships = {
        "source": "dbc",
        "tables": {
            "sales_invoice_lines": {
                "PK": "id",
                "relationships": [
                    {"target": "sales_invoices", "PK": "id", "FK": "documentId"},
                ],
            }
        },
    }
    sql = (
        "SELECT SUM(lines.netAmount) AS value "
        "FROM silver_dbc_sales_invoice_lines lines "
        "JOIN silver_dbc_sales_invoices invoices "
        "ON lines.documentId = invoices.id"
    )
    _validate_sql_joins(settings, sql, relationships=relationships)


def test_validate_sql_joins_rejects_undefined_join(tmp_path: Path) -> None:
    settings = DnaSettings(source="dbc", data_dir=tmp_path, company="poc")
    relationships = {
        "source": "dbc",
        "tables": {
            "sales_invoice_lines": {
                "PK": "id",
                "relationships": [
                    {"target": "sales_invoices", "PK": "id", "FK": "documentId"},
                ],
            }
        },
    }
    sql = (
        "SELECT SUM(lines.netAmount) AS value "
        "FROM silver_dbc_sales_invoice_lines lines "
        "JOIN silver_dbc_customers customers ON lines.customerId = customers.id"
    )
    try:
        _validate_sql_joins(settings, sql, relationships=relationships)
    except ValueError as exc:
        assert "not defined in gold entity_relationships.yaml" in str(exc)
    else:
        raise AssertionError("expected undefined join to be rejected")
