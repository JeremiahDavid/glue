"""Tests for config-driven reporting renderers."""

from __future__ import annotations

from pathlib import Path

import pytest

from hiveflow.dna.settings import DnaSettings
from hiveflow.dna.web.portal.reporting_render import (
    aggregate_chart_series,
    generic_chart_html,
    generic_table_html,
    page_has_content,
    render_page_body,
    render_section,
)


@pytest.fixture
def settings(tmp_path: Path) -> DnaSettings:
    return DnaSettings(source="dbc", data_dir=tmp_path, pack_id="bc_intra_v1")


def test_page_has_content() -> None:
    assert page_has_content({"sections": [{"layout": "kpi_grid"}]})
    assert page_has_content({"tables": [{"source_output": "out_x"}]})
    assert page_has_content({"charts": [{"source_output": "out_x"}]})
    assert not page_has_content({"title": "Empty"})


def test_generic_table_html_respects_columns_sort_limit(settings: DnaSettings, monkeypatch) -> None:
    rows = [
        {"postingDate": "2026-01-15", "netAmount": 100.0, "customerName": "Alpha"},
        {"postingDate": "2026-02-01", "netAmount": 200.0, "customerName": "Beta"},
        {"postingDate": "2026-03-01", "netAmount": 50.0, "customerName": "Gamma"},
    ]
    monkeypatch.setattr(
        "hiveflow.dna.web.portal.reporting_render.read_production_output",
        lambda _settings, _output: list(rows),
    )

    table_config = {
        "source_output": "out_fact_revenue_lines",
        "columns": [
            {"key": "postingDate", "label": "Date"},
            {"key": "customerName", "label": "Customer"},
            {"key": "netAmount", "label": "Amount", "numeric": True},
        ],
        "sort": [{"column": "postingDate", "direction": "desc"}],
        "limit": 2,
    }
    html = generic_table_html(settings, table_config)

    assert "Beta" in html
    assert "Gamma" in html
    assert "Alpha" not in html
    assert "Amount" in html
    assert "200.00" in html
    assert "Showing latest 2 rows" in html


def test_generic_chart_html_dimension_measure(settings: DnaSettings, monkeypatch) -> None:
    rows = [
        {"postingDate": "2026-01-10", "netAmount": 100.0},
        {"postingDate": "2026-01-20", "netAmount": 50.0},
        {"postingDate": "2026-02-05", "netAmount": 200.0},
    ]
    monkeypatch.setattr(
        "hiveflow.dna.web.portal.reporting_render.read_production_output",
        lambda _settings, _output: list(rows),
    )

    chart_config = {
        "type": "bar",
        "title": "Monthly revenue",
        "source_output": "out_fact_revenue_lines",
        "dimension": {"column": "postingDate", "grain": "month"},
        "measure": {"column": "netAmount", "aggregation": "sum"},
        "limit": 12,
        "show_summary": True,
    }
    html, use_charts = generic_chart_html(settings, chart_config)

    assert use_charts is True
    assert "Monthly revenue" in html
    assert "Period total" in html
    assert "350.00" in html
    assert "hive-chart" in html


def test_aggregate_chart_series_month_grain() -> None:
    rows = [
        {"postingDate": "2026-01-01", "netAmount": 10},
        {"postingDate": "2026-01-15", "netAmount": 20},
        {"postingDate": "2026-02-01", "netAmount": 5},
    ]
    assert aggregate_chart_series(
        rows,
        dimension_column="postingDate",
        measure_column="netAmount",
        grain="month",
    ) == [("2026-01", 30.0), ("2026-02", 5.0)]


def test_render_page_body_from_tables_and_charts(settings: DnaSettings, monkeypatch) -> None:
    def fake_read(_settings: DnaSettings, output_id: str) -> list[dict]:
        if output_id == "out_fact_revenue_lines":
            return [{"postingDate": "2026-01-01", "netAmount": 42.0, "customerName": "Acme"}]
        return []

    monkeypatch.setattr(
        "hiveflow.dna.web.portal.reporting_render.read_production_output",
        fake_read,
    )

    page = {
        "tables": [
            {
                "source_output": "out_fact_revenue_lines",
                "columns": [{"key": "customerName", "label": "Customer"}],
            }
        ],
        "charts": [
            {
                "source_output": "out_fact_revenue_lines",
                "dimension": {"column": "postingDate", "grain": "month"},
                "measure": {"column": "netAmount", "aggregation": "sum"},
                "title": "Trend",
            }
        ],
    }
    html, use_charts = render_page_body(page, settings=settings)

    assert "Acme" in html
    assert "Trend" in html
    assert use_charts is True


def test_render_section_compare_kpi_grid(settings: DnaSettings, monkeypatch) -> None:
    monkeypatch.setattr(
        "hiveflow.dna.web.portal.reporting_render.read_production_output",
        lambda _settings, _output: [
            {
                "kpi_id": "KPI-REV-YoY-MTD",
                "kpi_name": "Revenue YoY MTD",
                "value_cy": 1000,
                "value_py": 800,
                "pct_change": 0.25,
                "window": "mtd",
            }
        ],
    )
    section = {
        "title": "MTD",
        "layout": "compare_kpi_grid",
        "bindings": [
            {
                "source_output": "out_executive_kpis",
                "filter": {"window": "mtd"},
                "kpi_ids": ["KPI-REV-YoY-MTD"],
            }
        ],
    }
    html, use_charts = render_section(section, settings=settings)

    assert use_charts is False
    assert "MTD" in html
    assert "kpi-compare-card" in html
    assert "Revenue YoY MTD" in html


def test_ranked_table_resolves_dim_labels(settings: DnaSettings, monkeypatch) -> None:
    def fake_read(_settings: DnaSettings, output_id: str) -> list[dict]:
        if output_id == "out_top_customers_ytd":
            return [{"customerId": "C1", "value_cy": 100.0, "value_py": 80.0, "delta": 20.0, "pct_change": 0.25}]
        if output_id == "out_dim_customers":
            return [{"id": "C1", "displayName": "Acme Corp", "number": "10000"}]
        return []

    monkeypatch.setattr(
        "hiveflow.dna.web.portal.reporting_render.read_production_output",
        fake_read,
    )
    monkeypatch.setattr(
        "hiveflow.dna.web.portal.kpi_display.read_production_output",
        fake_read,
    )
    section = {
        "title": "Top customers",
        "layout": "ranked_table",
        "table": {
            "source_output": "out_top_customers_ytd",
            "limit": 10,
            "dim_join": {
                "output": "out_dim_customers",
                "id_column": "customerId",
                "dim_id_column": "id",
                "label_columns": ["displayName"],
                "title_column": "Customer",
            },
        },
    }
    html, _ = render_section(section, settings=settings)
    assert "Acme Corp" in html
    assert "C1" not in html


def test_ranked_table_fills_missing_dim_id_column(settings: DnaSettings, monkeypatch) -> None:
    """Packs that set label_columns but omit dim_id_column still resolve names."""

    def fake_read(_settings: DnaSettings, output_id: str) -> list[dict]:
        if output_id == "out_top_customers_ytd":
            return [{"customerId": "C1", "value_cy": 100.0, "value_py": 80.0, "delta": 20.0, "pct_change": 0.25}]
        if output_id == "out_dim_customers":
            return [{"id": "C1", "displayName": "Acme Corp", "number": "10000"}]
        return []

    monkeypatch.setattr(
        "hiveflow.dna.web.portal.reporting_render.read_production_output",
        fake_read,
    )
    monkeypatch.setattr(
        "hiveflow.dna.web.portal.kpi_display.read_production_output",
        fake_read,
    )
    section = {
        "title": "Top customers",
        "layout": "ranked_table",
        "table": {
            "source_output": "out_top_customers_ytd",
            "limit": 10,
            "dim_join": {
                "output": "out_dim_customers",
                "id_column": "customerId",
                "label_columns": ["displayName"],
                "title_column": "Customer",
            },
        },
    }
    html, _ = render_section(section, settings=settings)
    assert "Acme Corp" in html
    assert "C1" not in html
