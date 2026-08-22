"""HiveFlowAI ECharts theme — aligned to portal CSS tokens in theme.py."""

from __future__ import annotations

from typing import Any

# Keep in sync with :root tokens in hiveflow.dna.web.theme.styles().
PORTAL_COLORS = {
    "bg_base": "#060912",
    "bg_card": "rgba(14, 22, 38, 0.72)",
    "text": "#eef2f8",
    "text_muted": "#8b97ad",
    "text_dim": "#5c677d",
    "border": "rgba(255, 255, 255, 0.08)",
    "border_strong": "rgba(255, 255, 255, 0.14)",
    "accent_start": "#f59e0b",
    "accent_mid": "#14b8a6",
    "accent_end": "#38bdf8",
    "accent_electric_blue": "#0066ff",
    "accent_electric_gold": "#ffb800",
    "accent_light_blue": "#079be8",
}

SERIES_PALETTE = (
    PORTAL_COLORS["accent_light_blue"],
    PORTAL_COLORS["accent_electric_gold"],
    PORTAL_COLORS["accent_mid"],
    PORTAL_COLORS["accent_end"],
    PORTAL_COLORS["accent_start"],
    PORTAL_COLORS["accent_electric_blue"],
)

FONT_FAMILY = '-apple-system, BlinkMacSystemFont, "Segoe UI", Inter, Roboto, Helvetica, Arial, sans-serif'

ECHARTS_THEME_NAME = "hiveflowai"


def echarts_theme() -> dict[str, Any]:
    """Return the ECharts theme object registered client-side as ``hiveflowai``."""
    text = PORTAL_COLORS["text"]
    muted = PORTAL_COLORS["text_muted"]
    dim = PORTAL_COLORS["text_dim"]
    border = PORTAL_COLORS["border"]
    return {
        "color": list(SERIES_PALETTE),
        "backgroundColor": "transparent",
        "textStyle": {
            "color": text,
            "fontFamily": FONT_FAMILY,
        },
        "title": {
            "textStyle": {"color": text, "fontWeight": 600},
            "subtextStyle": {"color": muted},
        },
        "legend": {
            "textStyle": {"color": muted},
            "pageTextStyle": {"color": muted},
            "inactiveColor": dim,
        },
        "tooltip": {
            "backgroundColor": "rgba(10, 16, 28, 0.96)",
            "borderColor": PORTAL_COLORS["border_strong"],
            "textStyle": {"color": text, "fontSize": 12},
            "extraCssText": "box-shadow: 0 12px 32px rgba(0,0,0,0.45); border-radius: 10px;",
        },
        "axisPointer": {
            "lineStyle": {"color": PORTAL_COLORS["accent_mid"], "opacity": 0.45},
            "crossStyle": {"color": PORTAL_COLORS["accent_mid"], "opacity": 0.45},
        },
        "categoryAxis": {
            "axisLine": {"lineStyle": {"color": border}},
            "axisTick": {"lineStyle": {"color": border}},
            "axisLabel": {"color": muted},
            "splitLine": {"lineStyle": {"color": border}},
        },
        "valueAxis": {
            "axisLine": {"lineStyle": {"color": border}},
            "axisTick": {"lineStyle": {"color": border}},
            "axisLabel": {"color": muted},
            "splitLine": {"lineStyle": {"color": border}},
        },
        "timeAxis": {
            "axisLine": {"lineStyle": {"color": border}},
            "axisTick": {"lineStyle": {"color": border}},
            "axisLabel": {"color": muted},
            "splitLine": {"lineStyle": {"color": border}},
        },
        "line": {
            "lineStyle": {"width": 2},
            "symbolSize": 6,
            "symbol": "circle",
            "smooth": False,
        },
        "bar": {
            "itemStyle": {"borderRadius": [4, 4, 0, 0]},
        },
        "pie": {
            "itemStyle": {"borderColor": PORTAL_COLORS["bg_base"], "borderWidth": 2},
            "label": {"color": muted},
        },
    }


def primary_bar_gradient() -> dict[str, Any]:
    """Vertical bar gradient used for headline KPI / trend charts."""
    return {
        "type": "linear",
        "x": 0,
        "y": 1,
        "x2": 0,
        "y2": 0,
        "colorStops": [
            {"offset": 0, "color": PORTAL_COLORS["accent_light_blue"]},
            {"offset": 1, "color": PORTAL_COLORS["accent_electric_gold"]},
        ],
    }


def axis_defaults(*, compact_y: bool = False) -> dict[str, Any]:
    """Shared axis styling fragments merged into chart options."""
    grid = {
        "left": 56 if compact_y else 64,
        "right": 24,
        "top": 48,
        "bottom": 48,
        "containLabel": False,
    }
    category_axis = {
        "type": "category",
        "axisLine": {"lineStyle": {"color": PORTAL_COLORS["border_strong"]}},
        "axisTick": {"show": False},
        "axisLabel": {"color": PORTAL_COLORS["text_muted"], "fontSize": 11},
    }
    value_axis = {
        "type": "value",
        "splitNumber": 4,
        "axisLine": {"show": False},
        "axisTick": {"show": False},
        "axisLabel": {"color": PORTAL_COLORS["text_muted"], "fontSize": 11},
        "splitLine": {"lineStyle": {"color": PORTAL_COLORS["border"], "type": "solid"}},
    }
    return {"grid": grid, "category_axis": category_axis, "value_axis": value_axis}
