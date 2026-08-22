"""Tests for HiveFlowAI ECharts reporting layer."""

from __future__ import annotations

import json

import pytest

from hiveflow.dna.web.charts.catalog import (
    CHART_TYPE_CATALOG,
    ChartSeries,
    ChartSpec,
    build_echarts_option,
)
from hiveflow.dna.web.charts.render import chart_mount_html, charts_page_assets
from hiveflow.dna.web.charts.theme import ECHARTS_THEME_NAME, PORTAL_COLORS, echarts_theme


def test_catalog_lists_eight_chart_types() -> None:
    assert set(CHART_TYPE_CATALOG) == {
        "bar",
        "line",
        "area",
        "horizontal_bar",
        "stacked_bar",
        "pie",
        "donut",
        "combo",
    }


def test_echarts_theme_matches_portal_palette() -> None:
    theme = echarts_theme()
    assert theme["color"][0] == PORTAL_COLORS["accent_light_blue"]
    assert theme["backgroundColor"] == "transparent"
    assert theme["tooltip"]["backgroundColor"].startswith("rgba(")
    assert ECHARTS_THEME_NAME == "hiveflowai"


def test_build_bar_option_includes_categories_and_gradient() -> None:
    spec = ChartSpec(
        chart_type="bar",
        categories=["Jan", "Feb"],
        series=[ChartSeries(name="Revenue", values=[100.0, 200.0])],
        value_format="compact_currency",
    )
    option = build_echarts_option(spec)
    assert option["xAxis"]["data"] == ["Jan", "Feb"]
    assert option["series"][0]["type"] == "bar"
    assert option["series"][0]["itemStyle"]["color"]["type"] == "linear"


def test_build_pie_option_maps_categories_to_slices() -> None:
    spec = ChartSpec(
        chart_type="pie",
        categories=["A", "B"],
        series=[ChartSeries(name="Share", values=[60.0, 40.0])],
    )
    option = build_echarts_option(spec)
    data = option["series"][0]["data"]
    assert data[0]["name"] == "A"
    assert data[1]["value"] == 40.0


def test_build_combo_requires_two_series() -> None:
    spec = ChartSpec(
        chart_type="combo",
        categories=["Q1"],
        series=[ChartSeries(name="Volume", values=[10.0])],
    )
    with pytest.raises(ValueError, match="at least 2 series"):
        build_echarts_option(spec)


def test_chart_mount_html_embeds_payload() -> None:
    spec = ChartSpec(
        chart_type="line",
        categories=["Jan"],
        series=[ChartSeries(name="Trend", values=[1.0])],
        title="Trend",
    )
    html = chart_mount_html(spec)
    assert 'data-hive-chart="' in html
    assert 'class="hive-chart card"' in html
    assert 'aria-label="Trend"' in html


def test_charts_page_assets_register_theme_and_scripts() -> None:
    assets = charts_page_assets(lambda path: path)
    assert "HiveFlowEchartsTheme" in assets
    assert "/static/echarts.min.js" in assets
    assert "/static/portal-charts.js" in assets
    assert f'window.HiveFlowEchartsThemeName = "{ECHARTS_THEME_NAME}"' in assets
    start = assets.index("window.HiveFlowEchartsTheme = ") + len("window.HiveFlowEchartsTheme = ")
    end = assets.index("</script>", start)
    theme = json.loads(assets[start:end].rstrip().rstrip(";"))
    assert theme["color"]
