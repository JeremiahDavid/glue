"""KPI card formatting and gold-backed KPI section helpers."""

from __future__ import annotations

from typing import Any

from meshflow.dna.settings import DnaSettings
from meshflow.dna.store import read_production_output
from meshflow.dna.web.theme import empty_state, escape

_SCALE_DIVISORS = {
    "none": 1.0,
    "thousands": 1_000.0,
    "millions": 1_000_000.0,
    "billions": 1_000_000_000.0,
}
_SCALE_SUFFIXES = {
    "thousands": "K",
    "millions": "M",
    "billions": "B",
}


def kpi_format_from_row(row: dict[str, Any]) -> dict[str, Any] | None:
    format_type = row.get("format_type")
    if not format_type:
        return None
    try:
        places = int(row.get("format_decimal_places", 2))
    except (TypeError, ValueError):
        places = 2
    return {
        "type": str(format_type),
        "decimal_places": max(0, min(places, 6)),
        "scale": str(row.get("format_scale") or "none"),
    }


def kpi_format_lookup(settings: DnaSettings | None) -> dict[str, dict[str, Any]]:
    """Pinned DNA pack formats keyed by kpi_id."""
    if settings is None:
        return {}
    try:
        from meshflow.dna.workflow import load_production_pack

        pack = load_production_pack(settings)
    except Exception:  # noqa: BLE001 — fall back to gold row format fields
        return {}
    lookup: dict[str, dict[str, Any]] = {}
    for kpi in pack.kpis:
        if kpi.format is None:
            continue
        lookup[kpi.id] = {
            "type": kpi.format.type,
            "decimal_places": int(kpi.format.decimal_places),
            "scale": kpi.format.scale,
        }
    return lookup


def format_kpi_display_value(
    value: Any,
    *,
    format_spec: dict[str, Any] | None = None,
    unit: str = "",
) -> tuple[str, str]:
    """Return (formatted_number, unit_suffix) for a KPI card value."""
    if value is None:
        return "—", unit
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value), unit

    fmt = format_spec or {}
    format_type = str(fmt.get("type") or "number").strip().lower()
    try:
        places = int(fmt.get("decimal_places", 2))
    except (TypeError, ValueError):
        places = 2
    places = max(0, min(places, 6))
    scale = str(fmt.get("scale") or "none").strip().lower()
    divisor = _SCALE_DIVISORS.get(scale, 1.0)
    display = number / divisor if divisor else number
    scale_suffix = _SCALE_SUFFIXES.get(scale, "")

    if format_type == "percent":
        if abs(number) <= 1:
            text = f"{number * 100:.{places}f}%"
        else:
            text = f"{display:.{places}f}%"
        return text, unit

    pattern = f"{{:,.{places}f}}"
    body = pattern.format(display)
    if format_type == "currency":
        text = f"${body}{scale_suffix}"
        return text, "" if str(unit).strip().lower() in {"", "currency", "usd", "$"} else unit
    if scale_suffix:
        return f"{body}{scale_suffix}", unit
    return body, unit


def pct_change_badge(value: Any) -> tuple[str, str]:
    if value is None:
        return "—", "neutral"
    try:
        pct = float(value)
    except (TypeError, ValueError):
        return "—", "neutral"
    sign = "+" if pct > 0 else ""
    css = "positive" if pct > 0 else "negative" if pct < 0 else "neutral"
    return f"{sign}{pct * 100:.1f}%", css


def kpi_cards_html(
    rows: list[dict[str, Any]],
    *,
    settings: DnaSettings | None = None,
) -> str:
    if not rows:
        return empty_state(
            "No metrics published yet",
            "Run DNA publish after silver consolidate to populate certified KPI snapshots.",
        )

    format_by_id = kpi_format_lookup(settings)
    cards = []
    for row in rows:
        kpi_id = str(row.get("kpi_id") or "")
        format_spec = format_by_id.get(kpi_id) or kpi_format_from_row(row)
        value_text, unit = format_kpi_display_value(
            row.get("value", 0),
            format_spec=format_spec,
            unit=str(row.get("unit") or ""),
        )
        unit_html = f'<span class="unit">{escape(unit)}</span>' if unit else ""
        cards.append(
            f"""
            <article class="card kpi-card">
              <div class="kpi-label">{escape(row.get("kpi_name", row.get("kpi_id")))}</div>
              <div class="kpi-value">{escape(value_text)}{unit_html}</div>
              <div class="kpi-meta">{escape(row.get("definition", ""))}</div>
              <div class="kpi-id">{escape(row.get("kpi_id"))} · pack {escape(row.get("pack_id"))} v{escape(row.get("pack_version"))}</div>
            </article>
            """
        )
    return f'<div class="grid">{"".join(cards)}</div>'


def compare_kpi_cards_html(
    rows: list[dict[str, Any]],
    *,
    kpi_ids: list[str] | None = None,
    settings: DnaSettings | None = None,
) -> str:
    if not rows:
        return empty_state(
            "No comparison metrics yet",
            "Run DNA publish to populate executive KPI outputs.",
        )

    format_by_id = kpi_format_lookup(settings)
    allowed = {item for item in (kpi_ids or []) if item}
    cards = []
    for row in rows:
        kpi_id = str(row.get("kpi_id") or "")
        if allowed and kpi_id not in allowed:
            continue
        format_spec = format_by_id.get(kpi_id) or kpi_format_from_row(row)
        unit = str(row.get("unit") or "")
        cy_text, cy_unit = format_kpi_display_value(
            row.get("value_cy"),
            format_spec=format_spec,
            unit=unit,
        )
        py_text, _py_unit = format_kpi_display_value(
            row.get("value_py"),
            format_spec=format_spec,
            unit=unit,
        )
        pct_text, pct_class = pct_change_badge(row.get("pct_change"))
        unit_html = f'<span class="unit">{escape(cy_unit)}</span>' if cy_unit else ""
        cards.append(
            f"""
            <article class="card kpi-card kpi-compare-card">
              <div class="kpi-label">{escape(row.get("kpi_name", kpi_id))}</div>
              <div class="kpi-value">{escape(cy_text)}{unit_html}</div>
              <div class="kpi-compare-meta">
                <span class="kpi-prior">PY {escape(py_text)}</span>
                <span class="kpi-delta {pct_class}">{escape(pct_text)}</span>
              </div>
            </article>
            """
        )
    if not cards:
        return empty_state("No metrics in this section", "Check reporting section bindings and DNA publish.")
    return f'<div class="grid">{"".join(cards)}</div>'


def dimension_label_lookup(
    settings: DnaSettings,
    output_id: str,
    id_column: str,
    label_columns: tuple[str, ...],
    *,
    dim_id_column: str | None = None,
) -> dict[str, str]:
    dim_key = dim_id_column or id_column
    rows = read_production_output(settings, output_id)
    labels: dict[str, str] = {}
    for row in rows:
        key = str(row.get(dim_key) or "")
        if not key:
            continue
        parts = [str(row.get(column) or "").strip() for column in label_columns]
        label = " · ".join(part for part in parts if part) or key
        labels[key] = label
    return labels


def filter_kpi_rows(
    rows: list[dict[str, Any]],
    *,
    kpi_ids: list[str] | None = None,
    window: str | None = None,
) -> list[dict[str, Any]]:
    allowed = {item for item in (kpi_ids or []) if item}
    filtered: list[dict[str, Any]] = []
    for row in rows:
        kpi_id = str(row.get("kpi_id") or "")
        if allowed and kpi_id not in allowed:
            continue
        if window and str(row.get("window") or "") != window:
            continue
        filtered.append(row)
    return filtered
