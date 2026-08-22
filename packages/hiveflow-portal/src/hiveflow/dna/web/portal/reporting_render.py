"""Config-driven reporting renderers — tables, charts, sections, and pages."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable

from hiveflow.dna.settings import DnaSettings
from hiveflow.dna.store import read_production_output
from hiveflow.dna.web.charts import ChartSeries, ChartSpec, chart_mount_html
from hiveflow.dna.web.charts.gold import (
    REVENUE_OUTPUT_ID,
    aggregate_revenue_by_month,
    format_month_label,
    posting_month,
)
from hiveflow.dna.web.templating import render_template
from hiveflow.dna.web.theme import empty_state, escape

DEFAULT_TABLE_LIMIT = 500
DEFAULT_CHART_MONTHS = 12
DEFAULT_RANKED_LIMIT = 10

# Fallback column specs when reporting YAML omits columns (key, label, numeric).
_DEFAULT_FACT_COLUMNS: dict[str, tuple[tuple[str, str, bool], ...]] = {
    REVENUE_OUTPUT_ID: (
        ("postingDate", "Posting date", False),
        ("customerNumber", "Customer #", False),
        ("customerName", "Customer", False),
        ("documentId", "Document", False),
        ("sequence", "Line", True),
        ("quantity", "Qty", True),
        ("unitPrice", "Unit price", True),
        ("netAmount", "Amount", True),
    ),
}

# Auto dim-join when ranked_table omits explicit dim_join (output id substring → spec).
_RANKED_DIM_DEFAULTS: dict[str, dict[str, Any]] = {
    "customer": {
        "output": "out_dim_customers",
        "id_column": "customerId",
        "dim_id_column": "id",
        "label_columns": ("displayName", "number"),
        "title_column": "Customer",
    },
    "item": {
        "output": "out_dim_items",
        "id_column": "itemId",
        "dim_id_column": "id",
        "label_columns": ("displayName", "number"),
        "title_column": "Item",
    },
}

_PILLAR_EYEBROWS = {
    "executive": "Executive",
    "sales": "Sales",
    "operations": "Operations",
    "finance": "Finance",
    "inventory": "Inventory",
    "developer": "Developer",
}


def page_eyebrow(page: dict[str, Any]) -> str:
    pillar = str(page.get("pillar") or "").strip().lower()
    if pillar in _PILLAR_EYEBROWS:
        return _PILLAR_EYEBROWS[pillar]
    return "Report"


def page_has_content(page: dict[str, Any]) -> bool:
    sections = page.get("sections")
    tables = page.get("tables")
    charts = page.get("charts")
    return bool(
        (isinstance(sections, list) and sections)
        or (isinstance(tables, list) and tables)
        or (isinstance(charts, list) and charts)
    )


def _format_cell(value: Any, *, numeric: bool = False) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:,.2f}"
    if numeric and isinstance(value, (int, float)):
        return f"{value:,.2f}"
    return str(value)


def _parse_columns(
    table_config: dict[str, Any],
    *,
    source_output: str,
    sample_row: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    raw = table_config.get("columns")
    if isinstance(raw, list) and raw:
        columns: list[dict[str, Any]] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            key = str(item.get("key") or item.get("column") or "").strip()
            if not key:
                continue
            columns.append(
                {
                    "key": key,
                    "label": str(item.get("label") or key),
                    "numeric": bool(item.get("numeric")),
                }
            )
        if columns:
            return columns

    defaults = _DEFAULT_FACT_COLUMNS.get(source_output)
    if defaults:
        return [
            {"key": key, "label": label, "numeric": numeric}
            for key, label, numeric in defaults
        ]

    if sample_row:
        return [
            {
                "key": key,
                "label": key.replace("_", " ").title(),
                "numeric": isinstance(sample_row.get(key), (int, float)),
            }
            for key in sample_row
        ]
    return []


def _parse_sort(table_config: dict[str, Any]) -> list[tuple[str, bool]]:
    raw = table_config.get("sort")
    if not isinstance(raw, list):
        return []
    specs: list[tuple[str, bool]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        column = str(item.get("column") or item.get("key") or "").strip()
        if not column:
            continue
        direction = str(item.get("direction") or "asc").strip().lower()
        specs.append((column, direction != "desc"))
    return specs


def _apply_sort_limit(
    rows: list[dict[str, Any]],
    table_config: dict[str, Any],
) -> tuple[list[dict[str, Any]], bool]:
    sort_specs = _parse_sort(table_config)
    if sort_specs:

        def sort_key(row: dict[str, Any]) -> tuple[Any, ...]:
            values: list[Any] = []
            for column, ascending in sort_specs:
                value = row.get(column)
                if isinstance(value, (int, float)):
                    values.append(value if ascending else -value)
                else:
                    text = str(value or "")
                    values.append(text if ascending else text[::-1])
            return tuple(values)

        rows = sorted(rows, key=sort_key)

    try:
        limit = int(table_config.get("limit") or DEFAULT_TABLE_LIMIT)
    except (TypeError, ValueError):
        limit = DEFAULT_TABLE_LIMIT
    truncated = len(rows) > limit
    if limit > 0:
        rows = rows[:limit]
    return rows, truncated


def _dim_join_defaults_for(source_output: str, dim_join: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Match ranked output / id_column to known BC dim defaults (customer/item)."""
    id_column = str((dim_join or {}).get("id_column") or "")
    dim_output = str((dim_join or {}).get("output") or "")
    for token, spec in _RANKED_DIM_DEFAULTS.items():
        if id_column and id_column == spec["id_column"]:
            return dict(spec)
        if dim_output and dim_output == spec["output"]:
            return dict(spec)
        if token in source_output:
            return dict(spec)
    return None


def _resolve_dim_join(table_config: dict[str, Any], *, source_output: str) -> dict[str, Any] | None:
    dim_join = table_config.get("dim_join")
    if isinstance(dim_join, dict) and dim_join.get("output"):
        # Packs often set label_columns but omit dim_id_column; out_dim_* PKs are `id`,
        # while ranking rows use customerId/itemId — fill gaps from known defaults.
        resolved = dict(dim_join)
        defaults = _dim_join_defaults_for(source_output, resolved)
        if defaults:
            for key, value in defaults.items():
                if key == "label_columns" and resolved.get("label_columns"):
                    continue
                if key == "title_column" and resolved.get("title_column"):
                    continue
                if not resolved.get(key):
                    resolved[key] = value
        return resolved
    defaults = _dim_join_defaults_for(source_output)
    return dict(defaults) if defaults else None


def generic_table_html(
    settings: DnaSettings,
    table_config: dict[str, Any],
    *,
    empty_title: str = "No rows yet",
    empty_detail: str = "Data appears here after DNA publish completes.",
) -> str:
    source = str(table_config.get("source_output") or "").strip()
    if not source:
        return empty_state("No source configured", "Add source_output to the table binding.")

    all_rows = read_production_output(settings, source)
    rows, truncated = _apply_sort_limit(list(all_rows), table_config)
    sample = rows[0] if rows else (all_rows[0] if all_rows else None)
    columns = _parse_columns(table_config, source_output=source, sample_row=sample)

    dim_join = _resolve_dim_join(table_config, source_output=source)
    if dim_join and rows and "value_cy" in (rows[0] if rows else {}):
        return _ranked_yoy_table_from_config(rows, settings=settings, dim_join=dim_join)

    if not rows:
        return empty_state(empty_title, empty_detail)
    if not columns:
        return empty_state("No columns configured", "Add columns to the table binding in reporting config.")

    body_rows = [
        [
            {"value": _format_cell(row.get(col["key"]), numeric=col["numeric"]), "numeric": col["numeric"]}
            for col in columns
        ]
        for row in rows
    ]

    note = ""
    if truncated:
        limit = int(table_config.get("limit") or DEFAULT_TABLE_LIMIT)
        note = f"Showing latest {limit} rows"

    return render_template("portal/_generic_table.html", columns=columns, rows=body_rows, note=note)


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def aggregate_chart_series(
    rows: list[dict[str, Any]],
    *,
    dimension_column: str,
    measure_column: str,
    aggregation: str = "sum",
    grain: str | None = None,
    limit: int | None = None,
) -> list[tuple[str, float]]:
    """Group rows by dimension and aggregate measure — month grain uses YYYY-MM keys."""
    if grain == "month":
        totals: dict[str, float] = defaultdict(float)
        for row in rows:
            month = posting_month(row.get(dimension_column))
            amount = _safe_float(row.get(measure_column))
            if month is None:
                continue
            if aggregation == "count":
                totals[month] += 1.0
            elif amount is not None:
                totals[month] += amount
        months = sorted(totals)
        if limit and len(months) > limit:
            months = months[-limit:]
        return [(month, totals[month]) for month in months]

    totals: dict[str, float] = defaultdict(float)
    for row in rows:
        dim = str(row.get(dimension_column) or "").strip()
        if not dim:
            continue
        if aggregation == "count":
            totals[dim] += 1.0
        else:
            amount = _safe_float(row.get(measure_column))
            if amount is None:
                continue
            totals[dim] += amount

    ranked = sorted(totals.items(), key=lambda item: item[1], reverse=True)
    if limit:
        ranked = ranked[:limit]
    return ranked


def _chart_dimension_measure(chart_config: dict[str, Any]) -> tuple[str, str, str, str | None, int]:
    dimension = chart_config.get("dimension")
    measure = chart_config.get("measure")
    dim_column = "postingDate"
    measure_column = "netAmount"
    aggregation = "sum"
    grain: str | None = "month"
    if isinstance(dimension, dict):
        dim_column = str(dimension.get("column") or dim_column)
        grain = str(dimension.get("grain") or grain) or None
    elif isinstance(dimension, str) and dimension.strip():
        dim_column = dimension.strip()

    if isinstance(measure, dict):
        measure_column = str(measure.get("column") or measure_column)
        aggregation = str(measure.get("aggregation") or aggregation)
    elif isinstance(measure, str) and measure.strip():
        measure_column = measure.strip()

    try:
        limit = int(chart_config.get("limit") or DEFAULT_CHART_MONTHS)
    except (TypeError, ValueError):
        limit = DEFAULT_CHART_MONTHS
    return dim_column, measure_column, aggregation, grain, limit


def _trend_summary_html(monthly: list[tuple[str, float]]) -> str:
    total = sum(amount for _month, amount in monthly)
    average = total / len(monthly) if monthly else 0.0
    peak_month, peak_amount = max(monthly, key=lambda item: item[1]) if monthly else ("—", 0.0)
    peak_label = format_month_label(peak_month) if monthly else "—"

    cards = [
        {"label": "Period total", "value": f"{total:,.2f}", "meta": "Sum of aggregated measure"},
        {
            "label": "Monthly average",
            "value": f"{average:,.2f}",
            "meta": f"Across {len(monthly)} month{'s' if len(monthly) != 1 else ''}",
        },
        {"label": "Peak month", "value": f"{peak_amount:,.2f}", "meta": peak_label},
    ]
    return render_template("portal/_trend_summary.html", cards=cards)


def generic_chart_html(
    settings: DnaSettings,
    chart_config: dict[str, Any],
    *,
    empty_title: str = "No chart data yet",
    empty_detail: str = "Data appears here after DNA publish completes.",
) -> tuple[str, bool]:
    source = str(chart_config.get("source_output") or "").strip()
    if not source:
        return empty_state("No source configured", "Add source_output to the chart binding."), False

    rows = read_production_output(settings, source)
    dim_column, measure_column, aggregation, grain, limit = _chart_dimension_measure(chart_config)

    if source == REVENUE_OUTPUT_ID and grain == "month":
        empty_title = "No revenue trend yet"
        empty_detail = "Posted invoice lines with posting dates appear here after DNA publish completes."
    else:
        empty_title = empty_title or "No chart data yet"
        empty_detail = empty_detail or "Data appears here after DNA publish completes."
    # Backward compat: revenue trend pages without dimension/measure use legacy aggregator.
    if (
        source == REVENUE_OUTPUT_ID
        and dim_column == "postingDate"
        and measure_column == "netAmount"
        and grain == "month"
        and aggregation == "sum"
        and not chart_config.get("dimension")
        and not chart_config.get("measure")
    ):
        monthly = aggregate_revenue_by_month(rows, limit=limit)
    else:
        monthly = aggregate_chart_series(
            rows,
            dimension_column=dim_column,
            measure_column=measure_column,
            aggregation=aggregation,
            grain=grain,
            limit=limit,
        )

    chart_type = str(chart_config.get("type") or "bar").strip().lower()
    if chart_type not in {"bar", "line"}:
        chart_type = "bar"

    title = str(chart_config.get("title") or "Chart")
    show_summary = chart_config.get("show_summary")
    if show_summary is None and grain == "month":
        show_summary = True

    parts: list[str] = []
    if show_summary and monthly:
        parts.append(_trend_summary_html(monthly))

    if not monthly:
        parts.append(empty_state(empty_title, empty_detail))
        return "".join(parts), False

    categories = [
        format_month_label(key) if grain == "month" and len(key) == 7 and key[4] == "-" else key
        for key, _value in monthly
    ]
    spec = ChartSpec(
        chart_type=chart_type,
        title=title,
        aria_label=title,
        value_format="compact_currency",
        height=320,
        categories=categories,
        series=[ChartSeries(name=title, values=[value for _key, value in monthly])],
    )
    css = "hive-chart card revenue-trend-chart" if grain == "month" else "hive-chart card"
    parts.append(chart_mount_html(spec, css_class=css))
    return "".join(parts), True


def _ranked_yoy_table_from_config(
    rows: list[dict[str, Any]],
    *,
    settings: DnaSettings,
    dim_join: dict[str, Any],
) -> str:
    from hiveflow.dna.web.portal.kpi_display import (
        dimension_label_lookup,
        format_kpi_display_value,
        kpi_format_from_row,
        pct_change_badge,
    )

    dim_output = str(dim_join.get("output") or "")
    id_column = str(dim_join.get("id_column") or "")
    label_columns = tuple(
        str(item) for item in (dim_join.get("label_columns") or ()) if item
    )
    title_column = str(dim_join.get("title_column") or "Name")
    dim_id_column = str(dim_join.get("dim_id_column") or "").strip() or None

    if not rows:
        return empty_state(
            "No ranking data yet",
            "Rankings appear after DNA publish with sufficient activity.",
        )

    labels = dimension_label_lookup(
        settings,
        dim_output,
        id_column,
        label_columns,
        dim_id_column=dim_id_column,
    )
    format_spec = kpi_format_from_row(rows[0]) if rows else None
    body_rows = []
    for row in rows:
        dim_id = str(row.get(id_column) or "")
        name = labels.get(dim_id, dim_id or "—")
        cy_text, _ = format_kpi_display_value(row.get("value_cy"), format_spec=format_spec)
        py_text, _ = format_kpi_display_value(row.get("value_py"), format_spec=format_spec)
        delta_text, _ = format_kpi_display_value(row.get("delta"), format_spec=format_spec)
        pct_text, pct_class = pct_change_badge(row.get("pct_change"))
        body_rows.append(
            {
                "name": name,
                "cy": cy_text,
                "py": py_text,
                "delta": delta_text,
                "pct": pct_text,
                "pct_class": pct_class,
            }
        )
    return render_template("portal/_ranked_yoy_table.html", title_column=title_column, rows=body_rows)


def _layout_compare_kpi_grid(section: dict[str, Any], *, settings: DnaSettings) -> str:
    from hiveflow.dna.web.portal.kpi_display import compare_kpi_cards_html, filter_kpi_rows

    bindings = section.get("bindings") if isinstance(section.get("bindings"), list) else []
    parts: list[str] = []
    for binding in bindings:
        if not isinstance(binding, dict):
            continue
        source = str(binding.get("source_output") or "out_executive_kpis")
        filt = binding.get("filter") if isinstance(binding.get("filter"), dict) else {}
        window = str(filt.get("window") or "")
        kpi_ids = [str(item) for item in binding.get("kpi_ids") or [] if item]
        rows = read_production_output(settings, source)
        rows = filter_kpi_rows(rows, kpi_ids=kpi_ids, window=window or None)
        parts.append(compare_kpi_cards_html(rows, kpi_ids=kpi_ids, settings=settings))
    return "".join(parts) if parts else empty_state("No bindings configured", "")


def _layout_kpi_grid(section: dict[str, Any], *, settings: DnaSettings) -> str:
    from hiveflow.dna.web.portal.kpi_display import filter_kpi_rows, kpi_cards_html

    bindings = section.get("bindings") if isinstance(section.get("bindings"), list) else []
    parts: list[str] = []
    for binding in bindings:
        if not isinstance(binding, dict):
            continue
        source = str(binding.get("source_output") or "out_executive_snapshot")
        kpi_ids = [str(item) for item in binding.get("kpi_ids") or [] if item]
        rows = read_production_output(settings, source)
        rows = filter_kpi_rows(rows, kpi_ids=kpi_ids)
        parts.append(kpi_cards_html(rows, settings=settings))
    return "".join(parts) if parts else empty_state("No bindings configured", "")


def _layout_ranked_table(section: dict[str, Any], *, settings: DnaSettings) -> str:
    table = section.get("table") if isinstance(section.get("table"), dict) else {}
    source = str(table.get("source_output") or "")
    rows = read_production_output(settings, source) if source else []
    try:
        limit = int(table.get("limit") or DEFAULT_RANKED_LIMIT)
    except (TypeError, ValueError):
        limit = DEFAULT_RANKED_LIMIT
    rows = rows[:limit]
    dim_join = _resolve_dim_join(table, source_output=source)
    if dim_join:
        return _ranked_yoy_table_from_config(rows, settings=settings, dim_join=dim_join)
    return generic_table_html(settings, table)


def _layout_ranked_table_group(section: dict[str, Any], *, settings: DnaSettings) -> str:
    tables = section.get("tables") if isinstance(section.get("tables"), list) else []
    html = ""
    for index, table in enumerate(tables):
        if not isinstance(table, dict):
            continue
        sub_title = str(table.get("title") or f"Table {index + 1}")
        html += f'<div class="pack-history-subtitle">{escape(sub_title)}</div>'
        html += _layout_ranked_table({"table": table}, settings=settings)
    return html or empty_state("No tables configured", "")


def _layout_table(section: dict[str, Any], *, settings: DnaSettings) -> str:
    table = section.get("table") if isinstance(section.get("table"), dict) else section
    return generic_table_html(settings, table)


def _layout_chart(section: dict[str, Any], *, settings: DnaSettings) -> tuple[str, bool]:
    chart = section.get("chart") if isinstance(section.get("chart"), dict) else section
    return generic_chart_html(settings, chart)


LayoutHandler = Callable[..., str | tuple[str, bool]]

LAYOUT_REGISTRY: dict[str, LayoutHandler] = {
    "compare_kpi_grid": _layout_compare_kpi_grid,
    "kpi_grid": _layout_kpi_grid,
    "ranked_table": _layout_ranked_table,
    "ranked_table_group": _layout_ranked_table_group,
    "table": _layout_table,
}


def render_section(section: dict[str, Any], *, settings: DnaSettings) -> tuple[str, bool]:
    """Render one reporting section; returns (html, use_charts)."""
    title = str(section.get("title") or "Section")
    layout = str(section.get("layout") or "").strip()
    html = f'<section class="section"><div class="section-title">{escape(title)}</div>'
    use_charts = False

    if layout == "chart":
        body, use_charts = _layout_chart(section, settings=settings)
        html += body
    elif layout in LAYOUT_REGISTRY:
        handler = LAYOUT_REGISTRY[layout]
        result = handler(section, settings=settings)
        if isinstance(result, tuple):
            body, use_charts = result
            html += body
        else:
            html += result
    else:
        html += empty_state("Unsupported section layout", f"Layout {layout!r} is not implemented.")

    html += "</section>"
    return html, use_charts


def render_page_body(page: dict[str, Any], *, settings: DnaSettings) -> tuple[str, bool]:
    """Render all sections/tables/charts for a configured page."""
    sections = page.get("sections") if isinstance(page.get("sections"), list) else []
    tables = page.get("tables") if isinstance(page.get("tables"), list) else []
    charts = page.get("charts") if isinstance(page.get("charts"), list) else []

    parts: list[str] = []
    use_charts = False

    if sections:
        for section in sections:
            if not isinstance(section, dict):
                continue
            section_html, section_charts = render_section(section, settings=settings)
            parts.append(section_html)
            use_charts = use_charts or section_charts
        return "".join(parts), use_charts

    for table in tables:
        if not isinstance(table, dict):
            continue
        title = str(table.get("title") or "")
        section_open = f'<section class="section">'
        if title:
            section_open += f'<div class="section-title">{escape(title)}</div>'
        table_html = generic_table_html(settings, table)
        parts.append(f"{section_open}{table_html}</section>")

    for chart in charts:
        if not isinstance(chart, dict):
            continue
        title = str(chart.get("title") or "")
        section_open = '<section class="section">'
        if title and not chart.get("show_summary"):
            section_open += f'<div class="section-title">{escape(title)}</div>'
        chart_html, chart_uses = generic_chart_html(settings, chart)
        parts.append(f"{section_open}{chart_html}</section>")
        use_charts = use_charts or chart_uses

    if parts:
        return "".join(parts), use_charts

    return (
        empty_state(
            "No content configured",
            "Add sections, tables, or charts to this page in the reporting pack.",
        ),
        False,
    )


def query_table(settings: DnaSettings, table_config: dict[str, Any]) -> dict[str, Any]:
    """Return table rows and metadata (shared by HTML renderers and JSON API)."""
    source = str(table_config.get("source_output") or "").strip()
    if not source:
        raise ValueError("table config requires source_output")

    all_rows = read_production_output(settings, source)
    rows, truncated = _apply_sort_limit(list(all_rows), table_config)
    sample = rows[0] if rows else (all_rows[0] if all_rows else None)
    columns = _parse_columns(table_config, source_output=source, sample_row=sample)
    return {
        "source_output": source,
        "row_count": len(all_rows),
        "truncated": truncated,
        "columns": columns,
        "rows": rows,
    }


def query_chart(settings: DnaSettings, chart_config: dict[str, Any]) -> dict[str, Any]:
    """Return aggregated chart series (shared by HTML renderers and JSON API)."""
    source = str(chart_config.get("source_output") or "").strip()
    if not source:
        raise ValueError("chart config requires source_output")

    rows = read_production_output(settings, source)
    dim_column, measure_column, aggregation, grain, limit = _chart_dimension_measure(chart_config)

    if (
        source == REVENUE_OUTPUT_ID
        and dim_column == "postingDate"
        and measure_column == "netAmount"
        and grain == "month"
        and aggregation == "sum"
        and not chart_config.get("dimension")
        and not chart_config.get("measure")
    ):
        series_pairs = aggregate_revenue_by_month(rows, limit=limit)
    else:
        series_pairs = aggregate_chart_series(
            rows,
            dimension_column=dim_column,
            measure_column=measure_column,
            aggregation=aggregation,
            grain=grain,
            limit=limit,
        )

    chart_type = str(chart_config.get("type") or "bar").strip().lower()
    if chart_type not in {"bar", "line"}:
        chart_type = "bar"

    return {
        "source_output": source,
        "row_count": len(rows),
        "chart_type": chart_type,
        "title": str(chart_config.get("title") or ""),
        "dimension": {"column": dim_column, "grain": grain},
        "measure": {"column": measure_column, "aggregation": aggregation},
        "series": [{"key": key, "value": value} for key, value in series_pairs],
    }
