"""Tests for chart catalog demo page."""

from __future__ import annotations

from meshflow.dna.web.charts.catalog import CHART_TYPE_CATALOG
from meshflow.dna.web.charts.demo import chart_demo_section_html, chart_demo_specs


def test_chart_demo_specs_cover_catalog() -> None:
    specs = chart_demo_specs()
    assert len(specs) == len(CHART_TYPE_CATALOG)
    assert {spec.chart_type for spec in specs} == set(CHART_TYPE_CATALOG)


def test_chart_demo_section_renders_all_mounts() -> None:
    html = chart_demo_section_html()
    assert html.count("data-hive-chart=") == len(CHART_TYPE_CATALOG)
    assert "chart-demo-grid" in html
