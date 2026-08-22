"""HTML helpers for embedding ECharts mounts in portal pages."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from hiveflow.dna.web.charts.catalog import ChartSpec, build_echarts_option
from hiveflow.dna.web.charts.theme import ECHARTS_THEME_NAME, echarts_theme
from hiveflow.dna.web.templating import render_template


def _json_for_html(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


def charts_page_assets(url: Callable[[str], str]) -> str:
    """Return script tags that register the HiveFlowAI theme and hydrate chart mounts."""
    return render_template(
        "_charts_assets.html",
        theme_name=ECHARTS_THEME_NAME,
        theme=echarts_theme(),
        echarts_js_url=url("/static/echarts.min.js"),
        portal_charts_js_url=url("/static/portal-charts.js"),
    )


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
    return render_template(
        "_chart_mount.html",
        css_class=css_class,
        chart_id=chart_id,
        payload_json=_json_for_html(payload),
        height=int(spec.height),
        aria_label=spec.aria_label or spec.title or "Chart",
    )
