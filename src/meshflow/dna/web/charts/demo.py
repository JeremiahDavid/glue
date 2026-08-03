"""Sample chart specs for the portal chart catalog demo page."""

from __future__ import annotations

from meshflow.dna.web.charts.catalog import CHART_TYPE_CATALOG, ChartSeries, ChartSpec
from meshflow.dna.web.charts.render import chart_mount_html
from meshflow.dna.web.theme import escape

_DEMO_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun")
_DEMO_CUSTOMERS = ("Acme Corp", "Northwind", "Contoso", "Fabrikam", "Tailspin")
_DEMO_PRODUCTS = ("Hardware", "Services", "Subscriptions", "Support")


def chart_demo_specs() -> list[ChartSpec]:
    """Return one representative spec per catalog chart type."""
    months = list(_DEMO_MONTHS)
    return [
        ChartSpec(
            chart_type="bar",
            title="Monthly revenue",
            subtitle="Vertical bars · compact currency",
            aria_label="Bar chart demo: monthly revenue",
            value_format="compact_currency",
            categories=months,
            series=[ChartSeries(name="Revenue", values=[82000, 91000, 88000, 97000, 102000, 108000])],
        ),
        ChartSpec(
            chart_type="line",
            title="Open orders",
            subtitle="Line · smooth trend",
            aria_label="Line chart demo: open orders",
            value_format="number",
            smooth=True,
            categories=months,
            series=[ChartSeries(name="Orders", values=[142, 156, 149, 168, 175, 181])],
        ),
        ChartSpec(
            chart_type="area",
            title="Inventory on hand",
            subtitle="Filled area · units",
            aria_label="Area chart demo: inventory on hand",
            value_format="number",
            smooth=True,
            categories=months,
            series=[ChartSeries(name="Units", values=[4200, 4050, 4380, 4510, 4475, 4620])],
        ),
        ChartSpec(
            chart_type="horizontal_bar",
            title="Top customers",
            subtitle="Horizontal bar · currency",
            aria_label="Horizontal bar chart demo: top customers",
            value_format="currency",
            height=300,
            categories=list(_DEMO_CUSTOMERS),
            series=[ChartSeries(name="Revenue", values=[245000, 198000, 176000, 152000, 131000])],
        ),
        ChartSpec(
            chart_type="stacked_bar",
            title="Revenue by region",
            subtitle="Stacked bar · multi-series",
            aria_label="Stacked bar chart demo: revenue by region",
            value_format="compact_currency",
            categories=months,
            series=[
                ChartSeries(name="North", values=[28000, 31000, 29500, 33000, 34500, 36000]),
                ChartSeries(name="South", values=[22000, 24500, 23800, 25200, 26800, 27500]),
                ChartSeries(name="West", values=[32000, 35500, 34700, 38800, 40800, 44500]),
            ],
            show_legend=True,
        ),
        ChartSpec(
            chart_type="pie",
            title="Revenue mix",
            subtitle="Pie · share of total",
            aria_label="Pie chart demo: revenue mix",
            value_format="currency",
            height=300,
            categories=list(_DEMO_PRODUCTS),
            series=[ChartSeries(name="Revenue", values=[420000, 310000, 280000, 95000])],
        ),
        ChartSpec(
            chart_type="donut",
            title="Revenue mix",
            subtitle="Donut · center cutout",
            aria_label="Donut chart demo: revenue mix",
            value_format="currency",
            height=300,
            categories=list(_DEMO_PRODUCTS),
            series=[ChartSeries(name="Revenue", values=[420000, 310000, 280000, 95000])],
        ),
        ChartSpec(
            chart_type="combo",
            title="Revenue vs target",
            subtitle="Combo · bar + line on shared axis",
            aria_label="Combo chart demo: revenue versus target",
            value_format="compact_currency",
            smooth=True,
            categories=months,
            series=[
                ChartSeries(name="Revenue", values=[82000, 91000, 88000, 97000, 102000, 108000]),
                ChartSeries(name="Target", values=[85000, 90000, 90000, 95000, 100000, 105000]),
            ],
            show_legend=True,
        ),
    ]


def chart_demo_section_html() -> str:
    """Render all catalog chart types for the portal demo page."""
    items = []
    for spec in chart_demo_specs():
        meta = CHART_TYPE_CATALOG[spec.chart_type]
        items.append(
            f"""
        <article class="chart-demo-item card">
          <div class="chart-demo-meta">
            <div class="chart-demo-type">{escape(spec.chart_type)}</div>
            <h2 class="chart-demo-label">{escape(meta["label"])}</h2>
            <p class="chart-demo-desc">{escape(meta["description"])}</p>
          </div>
          {chart_mount_html(spec, css_class="hive-chart chart-demo-mount")}
        </article>
        """
        )
    return f'<div class="chart-demo-grid">{"".join(items)}</div>'
