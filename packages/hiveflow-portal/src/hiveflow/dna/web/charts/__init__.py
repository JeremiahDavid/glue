"""HiveFlowAI ECharts reporting layer — catalog, theme, and HTML helpers."""

from hiveflow.dna.web.charts.catalog import CHART_TYPE_CATALOG, ChartSeries, ChartSpec, build_echarts_option
from hiveflow.dna.web.charts.render import chart_mount_html, charts_page_assets

__all__ = [
    "CHART_TYPE_CATALOG",
    "ChartSeries",
    "ChartSpec",
    "build_echarts_option",
    "chart_mount_html",
    "charts_page_assets",
]
