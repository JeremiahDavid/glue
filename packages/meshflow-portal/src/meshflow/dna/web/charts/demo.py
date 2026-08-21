"""Chart catalog demo built from certified gold outputs."""

from __future__ import annotations

from meshflow.dna.settings import DnaSettings
from meshflow.dna.web.charts.catalog import CHART_TYPE_CATALOG, ChartSeries, ChartSpec
from meshflow.dna.web.charts.gold import (
    REVENUE_OUTPUT_ID,
    aggregate_count_by_month,
    aggregate_revenue_by_item,
    aggregate_revenue_by_month,
    aggregate_stacked_customer_revenue,
    aggregate_sum_by_month,
    aggregate_top_customers,
    format_month_label,
    load_items,
    load_revenue_lines,
    rolling_average,
)
from markupsafe import Markup

from meshflow.dna.web.charts.render import chart_mount_html
from meshflow.dna.web.templating import render_template
from meshflow.dna.web.theme import empty_state


def _monthly_categories(monthly: list[tuple[str, float]]) -> list[str]:
    return [format_month_label(month) for month, _value in monthly]


def _monthly_values(monthly: list[tuple[str, float]]) -> list[float]:
    return [value for _month, value in monthly]


def chart_demo_specs(settings: DnaSettings) -> dict[str, ChartSpec | None]:
    """Build one chart spec per catalog type from gold-layer outputs."""
    revenue_lines = load_revenue_lines(settings)
    items = load_items(settings)
    monthly_revenue = aggregate_revenue_by_month(revenue_lines)
    monthly_line_count = aggregate_count_by_month(revenue_lines)
    monthly_quantity = aggregate_sum_by_month(revenue_lines, "quantity")
    top_customers = aggregate_top_customers(revenue_lines)
    item_mix = aggregate_revenue_by_item(revenue_lines, items)
    stacked_categories, stacked_series = aggregate_stacked_customer_revenue(revenue_lines)

    revenue_values = _monthly_values(monthly_revenue)
    moving_avg = rolling_average(revenue_values)

    return {
        "bar": ChartSpec(
            chart_type="bar",
            title="Monthly posted revenue",
            subtitle=f"{REVENUE_OUTPUT_ID} · netAmount by posting month",
            aria_label="Bar chart: monthly posted revenue from gold",
            value_format="compact_currency",
            categories=_monthly_categories(monthly_revenue),
            series=[ChartSeries(name="Posted revenue", values=revenue_values)],
        )
        if monthly_revenue
        else None,
        "line": ChartSpec(
            chart_type="line",
            title="Invoice line volume",
            subtitle=f"{REVENUE_OUTPUT_ID} · line count by posting month",
            aria_label="Line chart: invoice line count from gold",
            value_format="number",
            smooth=True,
            categories=_monthly_categories(monthly_line_count),
            series=[ChartSeries(name="Invoice lines", values=_monthly_values(monthly_line_count))],
        )
        if monthly_line_count
        else None,
        "area": ChartSpec(
            chart_type="area",
            title="Invoiced quantity",
            subtitle=f"{REVENUE_OUTPUT_ID} · quantity by posting month",
            aria_label="Area chart: invoiced quantity from gold",
            value_format="number",
            smooth=True,
            categories=_monthly_categories(monthly_quantity),
            series=[ChartSeries(name="Quantity", values=_monthly_values(monthly_quantity))],
        )
        if monthly_quantity
        else None,
        "horizontal_bar": ChartSpec(
            chart_type="horizontal_bar",
            title="Top customers by revenue",
            subtitle=f"{REVENUE_OUTPUT_ID} · ranked netAmount",
            aria_label="Horizontal bar chart: top customers from gold",
            value_format="currency",
            height=300,
            categories=[label for label, _amount in top_customers],
            series=[ChartSeries(name="Revenue", values=[amount for _label, amount in top_customers])],
        )
        if top_customers
        else None,
        "stacked_bar": ChartSpec(
            chart_type="stacked_bar",
            title="Customer revenue by month",
            subtitle=f"{REVENUE_OUTPUT_ID} · top customers stacked by posting month",
            aria_label="Stacked bar chart: customer revenue by month from gold",
            value_format="compact_currency",
            categories=stacked_categories,
            series=[ChartSeries(name=name, values=values) for name, values in stacked_series],
            show_legend=True,
        )
        if len(stacked_series) >= 2
        else None,
        "pie": ChartSpec(
            chart_type="pie",
            title="Revenue by item",
            subtitle=f"{REVENUE_OUTPUT_ID} + out_dim_items · netAmount by item",
            aria_label="Pie chart: revenue by item from gold",
            value_format="currency",
            height=300,
            categories=[label for label, _amount in item_mix],
            series=[ChartSeries(name="Revenue", values=[amount for _label, amount in item_mix])],
        )
        if item_mix
        else None,
        "donut": ChartSpec(
            chart_type="donut",
            title="Revenue by item",
            subtitle=f"{REVENUE_OUTPUT_ID} + out_dim_items · share of posted revenue",
            aria_label="Donut chart: revenue by item from gold",
            value_format="currency",
            height=300,
            categories=[label for label, _amount in item_mix],
            series=[ChartSeries(name="Revenue", values=[amount for _label, amount in item_mix])],
        )
        if item_mix
        else None,
        "combo": ChartSpec(
            chart_type="combo",
            title="Revenue and 3-month average",
            subtitle=f"{REVENUE_OUTPUT_ID} · posted revenue vs rolling average",
            aria_label="Combo chart: monthly revenue and rolling average from gold",
            value_format="compact_currency",
            smooth=True,
            categories=_monthly_categories(monthly_revenue),
            series=[
                ChartSeries(name="Posted revenue", values=revenue_values),
                ChartSeries(name="3-mo avg", values=moving_avg),
            ],
            show_legend=True,
        )
        if monthly_revenue
        else None,
    }


def chart_demo_section_html(settings: DnaSettings) -> str:
    """Render all catalog chart types sourced from gold outputs."""
    specs = chart_demo_specs(settings)
    items = []
    for chart_type in CHART_TYPE_CATALOG:
        meta = CHART_TYPE_CATALOG[chart_type]
        spec = specs[chart_type]
        if spec is None:
            chart_html = empty_state(
                "No gold data yet",
                f"Publish DNA to populate {REVENUE_OUTPUT_ID} before this {meta['label'].lower()} chart can render.",
            )
        else:
            chart_html = chart_mount_html(spec, css_class="hive-chart chart-demo-mount")

        source = spec.subtitle if spec and spec.subtitle else REVENUE_OUTPUT_ID
        items.append(
            {
                "chart_type": chart_type,
                "label": meta["label"],
                "description": meta["description"],
                "source": source,
                "chart_html": Markup(chart_html),
            }
        )
    return render_template("_chart_demo_section.html", items=items)


def chart_demo_has_charts(settings: DnaSettings) -> bool:
    return any(spec is not None for spec in chart_demo_specs(settings).values())
