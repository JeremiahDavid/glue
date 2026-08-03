"""Tests for chart catalog demo page."""

from __future__ import annotations

from pathlib import Path

import pytest

from meshflow.dna.settings import DnaSettings
from meshflow.dna.web.charts.catalog import CHART_TYPE_CATALOG
from meshflow.dna.web.charts.demo import chart_demo_section_html, chart_demo_specs


@pytest.fixture
def gold_settings(tmp_path: Path) -> DnaSettings:
    from meshflow.ingest.storage import write_parquet_local

    write_parquet_local(
        tmp_path / "gold" / "dna" / "out_fact_revenue_lines",
        "data.parquet",
        [
            {
                "postingDate": "2026-01-15",
                "netAmount": 100.0,
                "quantity": 2.0,
                "customerId": "c1",
                "customerName": "Acme",
                "itemId": "i1",
            },
            {
                "postingDate": "2026-01-20",
                "netAmount": 50.0,
                "quantity": 1.0,
                "customerId": "c2",
                "customerName": "Northwind",
                "itemId": "i2",
            },
            {
                "postingDate": "2026-02-01",
                "netAmount": 200.0,
                "quantity": 4.0,
                "customerId": "c1",
                "customerName": "Acme",
                "itemId": "i1",
            },
        ],
    )
    write_parquet_local(
        tmp_path / "gold" / "dna" / "out_dim_items",
        "data.parquet",
        [
            {"id": "i1", "displayName": "Widget A", "number": "W-A"},
            {"id": "i2", "displayName": "Widget B", "number": "W-B"},
        ],
    )
    return DnaSettings(source="dbc", data_dir=tmp_path, pack_id="bc_intra_v1")


def test_chart_demo_specs_cover_catalog(gold_settings: DnaSettings) -> None:
    specs = chart_demo_specs(gold_settings)
    assert set(specs) == set(CHART_TYPE_CATALOG)
    assert specs["bar"] is not None
    assert specs["stacked_bar"] is not None


def test_chart_demo_section_renders_gold_charts(gold_settings: DnaSettings) -> None:
    html = chart_demo_section_html(gold_settings)
    assert html.count("data-hive-chart=") == len(CHART_TYPE_CATALOG)
    assert "out_fact_revenue_lines" in html
    assert "Widget A" in html
    assert "Acme" in html


def test_chart_demo_section_without_gold_shows_empty_states(tmp_path: Path) -> None:
    settings = DnaSettings(source="dbc", data_dir=tmp_path, pack_id="bc_intra_v1")
    html = chart_demo_section_html(settings)
    assert html.count("No gold data yet") == len(CHART_TYPE_CATALOG)
    assert "data-hive-chart=" not in html
