"""Chart type catalog and ECharts option builders for HiveFlowAI portals."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import Any

from hiveflow.dna.web.charts.theme import (
    PORTAL_COLORS,
    axis_defaults,
    primary_bar_gradient,
)

ChartBuilder = Callable[["ChartSpec"], dict[str, Any]]


@dataclass(frozen=True)
class ChartSeries:
    name: str
    values: list[float | int | None]


@dataclass(frozen=True)
class ChartSpec:
    """Declarative chart definition consumed by portal views and Reporting Engine codegen."""

    chart_type: str
    categories: list[str]
    series: list[ChartSeries]
    title: str | None = None
    subtitle: str | None = None
    aria_label: str | None = None
    value_format: str = "number"
    height: int = 320
    stacked: bool = False
    smooth: bool = False
    show_legend: bool | None = None
    y_axis_name: str | None = None
    x_axis_name: str | None = None
    donut_inner_radius: str = "52%"
    extra: dict[str, Any] = field(default_factory=dict)


CHART_TYPE_CATALOG: dict[str, dict[str, Any]] = {
    "bar": {
        "label": "Bar",
        "description": "Vertical bars for category comparisons and monthly totals.",
        "required_fields": ["categories", "series"],
        "optional_fields": ["title", "value_format", "stacked"],
        "min_series": 1,
        "max_series": 8,
    },
    "line": {
        "label": "Line",
        "description": "Trend lines over ordered categories or time buckets.",
        "required_fields": ["categories", "series"],
        "optional_fields": ["title", "value_format", "smooth"],
        "min_series": 1,
        "max_series": 8,
    },
    "area": {
        "label": "Area",
        "description": "Filled line chart for cumulative or volume trends.",
        "required_fields": ["categories", "series"],
        "optional_fields": ["title", "value_format", "smooth", "stacked"],
        "min_series": 1,
        "max_series": 6,
    },
    "horizontal_bar": {
        "label": "Horizontal bar",
        "description": "Ranked categories such as top customers or SKUs.",
        "required_fields": ["categories", "series"],
        "optional_fields": ["title", "value_format"],
        "min_series": 1,
        "max_series": 4,
    },
    "stacked_bar": {
        "label": "Stacked bar",
        "description": "Part-to-whole comparisons across categories.",
        "required_fields": ["categories", "series"],
        "optional_fields": ["title", "value_format"],
        "min_series": 2,
        "max_series": 8,
    },
    "pie": {
        "label": "Pie",
        "description": "Share of total for a single metric across categories.",
        "required_fields": ["categories", "series"],
        "optional_fields": ["title", "value_format"],
        "min_series": 1,
        "max_series": 1,
    },
    "donut": {
        "label": "Donut",
        "description": "Pie chart with center cutout for KPI callouts.",
        "required_fields": ["categories", "series"],
        "optional_fields": ["title", "value_format", "donut_inner_radius"],
        "min_series": 1,
        "max_series": 1,
    },
    "combo": {
        "label": "Combo",
        "description": "Bars for volume with a line overlay for rate or target.",
        "required_fields": ["categories", "series"],
        "optional_fields": ["title", "value_format", "smooth"],
        "min_series": 2,
        "max_series": 2,
    },
}


def format_chart_value(value: float | int | None, value_format: str) -> str:
    """Format a numeric value for display."""
    if value is None:
        return "—"
    number = float(value)
    if value_format == "currency":
        return f"${number:,.2f}"
    if value_format == "compact_currency":
        if abs(number) >= 1_000_000:
            return f"${number / 1_000_000:.1f}M"
        if abs(number) >= 1_000:
            return f"${number / 1_000:.0f}k"
        return f"${number:,.0f}"
    if value_format == "percent":
        return f"{number:.1%}" if abs(number) <= 1 else f"{number:.1f}%"
    if abs(number) >= 1_000_000:
        return f"{number / 1_000_000:.1f}M"
    if abs(number) >= 10_000:
        return f"{number / 1_000:.0f}k"
    if float(number).is_integer():
        return f"{int(number):,}"
    return f"{number:,.2f}"


def _title_block(spec: ChartSpec) -> dict[str, Any] | None:
    if not spec.title and not spec.subtitle:
        return None
    block: dict[str, Any] = {"left": "left", "top": 0}
    if spec.title:
        block["text"] = spec.title
    if spec.subtitle:
        block["subtext"] = spec.subtitle
    return block


def _legend_block(spec: ChartSpec) -> dict[str, Any] | None:
    show = spec.show_legend
    if show is None:
        show = len(spec.series) > 1
    if not show:
        return None
    return {"top": 0, "right": 0, "icon": "roundRect", "itemWidth": 12, "itemHeight": 8}


def _cartesian_option(spec: ChartSpec, *, horizontal: bool = False) -> dict[str, Any]:
    defaults = axis_defaults(compact_y=spec.value_format == "compact_currency")
    category = dict(defaults["category_axis"])
    value = dict(defaults["value_axis"])
    if spec.x_axis_name:
        category["name"] = spec.x_axis_name
    if spec.y_axis_name:
        value["name"] = spec.y_axis_name

    x_axis = category if not horizontal else value
    y_axis = value if not horizontal else {**category, "inverse": True}
    return {
        "grid": defaults["grid"],
        "xAxis": x_axis,
        "yAxis": y_axis,
        "tooltip": {
            "trigger": "axis",
            "axisPointer": {"type": "shadow" if not horizontal else "line"},
        },
    }


def _build_bar(spec: ChartSpec) -> dict[str, Any]:
    option = _cartesian_option(spec)
    gradient = primary_bar_gradient()
    series = []
    for index, entry in enumerate(spec.series):
        item_style: dict[str, Any] = {"borderRadius": [4, 4, 0, 0], "opacity": 0.92}
        if len(spec.series) == 1:
            item_style["color"] = gradient
        series.append(
            {
                "name": entry.name,
                "type": "bar",
                "stack": "total" if spec.stacked else None,
                "barMaxWidth": 48,
                "itemStyle": item_style,
                "emphasis": {"focus": "series"},
                "data": entry.values,
                "z": len(spec.series) - index,
            }
        )
    option["series"] = series
    return option


def _build_line(spec: ChartSpec, *, area: bool = False) -> dict[str, Any]:
    option = _cartesian_option(spec)
    option["tooltip"]["axisPointer"] = {"type": "line"}
    series = []
    for entry in spec.series:
        line: dict[str, Any] = {
            "name": entry.name,
            "type": "line",
            "smooth": spec.smooth,
            "showSymbol": len(spec.categories) <= 24,
            "symbolSize": 7,
            "lineStyle": {"width": 2.5},
            "emphasis": {"focus": "series"},
            "data": entry.values,
        }
        if area:
            line["areaStyle"] = {"opacity": 0.18}
        if spec.stacked:
            line["stack"] = "total"
        series.append(line)
    option["series"] = series
    return option


def _build_horizontal_bar(spec: ChartSpec) -> dict[str, Any]:
    option = _cartesian_option(spec, horizontal=True)
    series = []
    for entry in spec.series:
        series.append(
            {
                "name": entry.name,
                "type": "bar",
                "barMaxWidth": 22,
                "itemStyle": {"borderRadius": [0, 4, 4, 0], "opacity": 0.92},
                "emphasis": {"focus": "series"},
                "data": entry.values,
            }
        )
    option["series"] = series
    return option


def _build_stacked_bar(spec: ChartSpec) -> dict[str, Any]:
    return _build_bar(replace(spec, stacked=True))


def _build_pie(spec: ChartSpec, *, donut: bool = False) -> dict[str, Any]:
    if not spec.series:
        return {"series": []}
    values = spec.series[0].values
    data = []
    for category, value in zip(spec.categories, values, strict=False):
        data.append({"name": category, "value": value if value is not None else 0})
    radius = [spec.donut_inner_radius, "72%"] if donut else "68%"
    return {
        "tooltip": {"trigger": "item"},
        "legend": _legend_block(spec) or {"show": len(data) > 1, "bottom": 0, "icon": "roundRect"},
        "series": [
            {
                "name": spec.series[0].name,
                "type": "pie",
                "radius": radius,
                "center": ["50%", "48%"],
                "avoidLabelOverlap": True,
                "itemStyle": {
                    "borderColor": PORTAL_COLORS["bg_base"],
                    "borderWidth": 2,
                },
                "label": {"color": PORTAL_COLORS["text_muted"], "fontSize": 11},
                "labelLine": {"lineStyle": {"color": PORTAL_COLORS["border_strong"]}},
                "emphasis": {
                    "scale": True,
                    "scaleSize": 8,
                    "itemStyle": {"shadowBlur": 18, "shadowColor": "rgba(0,0,0,0.35)"},
                },
                "data": data,
            }
        ],
    }


def _build_combo(spec: ChartSpec) -> dict[str, Any]:
    option = _cartesian_option(spec)
    if len(spec.series) < 2:
        return _build_bar(spec)
    bar_series = {
        "name": spec.series[0].name,
        "type": "bar",
        "barMaxWidth": 42,
        "itemStyle": {"color": primary_bar_gradient(), "borderRadius": [4, 4, 0, 0], "opacity": 0.92},
        "data": spec.series[0].values,
    }
    line_series = {
        "name": spec.series[1].name,
        "type": "line",
        "smooth": spec.smooth,
        "symbolSize": 7,
        "lineStyle": {"width": 2.5, "color": PORTAL_COLORS["accent_electric_gold"]},
        "itemStyle": {"color": PORTAL_COLORS["accent_electric_gold"]},
        "data": spec.series[1].values,
    }
    option["series"] = [bar_series, line_series]
    return option


_BUILDERS: dict[str, ChartBuilder] = {
    "bar": _build_bar,
    "line": lambda spec: _build_line(spec, area=False),
    "area": lambda spec: _build_line(spec, area=True),
    "horizontal_bar": _build_horizontal_bar,
    "stacked_bar": _build_stacked_bar,
    "pie": lambda spec: _build_pie(spec, donut=False),
    "donut": lambda spec: _build_pie(spec, donut=True),
    "combo": _build_combo,
}


def build_echarts_option(spec: ChartSpec) -> dict[str, Any]:
    """Build a complete ECharts option object from a declarative chart spec."""
    if spec.chart_type not in CHART_TYPE_CATALOG:
        supported = ", ".join(sorted(CHART_TYPE_CATALOG))
        raise ValueError(f"Unknown chart type {spec.chart_type!r}. Supported: {supported}")

    meta = CHART_TYPE_CATALOG[spec.chart_type]
    if len(spec.series) < meta["min_series"]:
        raise ValueError(f"{spec.chart_type} requires at least {meta['min_series']} series")
    if len(spec.series) > meta["max_series"]:
        raise ValueError(f"{spec.chart_type} supports at most {meta['max_series']} series")

    builder = _BUILDERS[spec.chart_type]
    option = builder(spec)
    title = _title_block(spec)
    if title:
        option["title"] = title
    legend = _legend_block(spec)
    if legend:
        option["legend"] = legend
    if spec.categories and spec.chart_type not in {"pie", "donut"}:
        option.setdefault("xAxis", {})
        option.setdefault("yAxis", {})
        if spec.chart_type == "horizontal_bar":
            option["yAxis"]["data"] = spec.categories
        else:
            option["xAxis"]["data"] = spec.categories
    return option
