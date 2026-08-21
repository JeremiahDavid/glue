"""HTML helpers for embedding ECharts mounts in portal pages."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from meshflow.dna.web.charts.catalog import ChartSpec, build_echarts_option
from meshflow.dna.web.charts.theme import ECHARTS_THEME_NAME, echarts_theme
from meshflow.dna.web.theme import escape


def _json_for_html(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


def charts_page_assets(url: Callable[[str], str]) -> str:
    """Return script tags that register the HiveFlowAI theme and hydrate chart mounts."""
    theme_json = _json_for_html(echarts_theme())
    return f"""
<script>
window.HiveFlowEchartsThemeName = {json.dumps(ECHARTS_THEME_NAME)};
window.HiveFlowEchartsTheme = {theme_json};
</script>
<script src="{escape(url("/static/echarts.min.js"))}" defer></script>
<script src="{escape(url("/static/portal-charts.js"))}" defer></script>
"""


def chart_mount_html(
    spec: ChartSpec,
    *,
    css_class: str = "hive-chart card",
    chart_id: str | None = None,
) -> str:
    """Render a chart container with an embedded ECharts option payload."""
    option = build_echarts_option(spec)
    payload = {
        "type": spec.chart_type,
        "height": spec.height,
        "valueFormat": spec.value_format,
        "ariaLabel": spec.aria_label or spec.title or "Chart",
        "option": option,
    }
    attrs = [
        f'class="{escape(css_class)}"',
        f'data-hive-chart="{escape(_json_for_html(payload))}"',
        f'style="height:{int(spec.height)}px"',
        'role="img"',
        f'aria-label="{escape(spec.aria_label or spec.title or "Chart")}"',
    ]
    if chart_id:
        attrs.insert(0, f'id="{escape(chart_id)}"')
    return f"<div {' '.join(attrs)}></div>"
