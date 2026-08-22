"""Gold-layer aggregations for portal charts."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from hiveflow.dna.settings import DnaSettings
from hiveflow.dna.store import read_production_output

REVENUE_OUTPUT_ID = "out_fact_revenue_lines"
ITEMS_OUTPUT_ID = "out_dim_items"

_MONTH_NAMES = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
DEFAULT_MONTH_LIMIT = 6
DEFAULT_TOP_CUSTOMERS = 5
DEFAULT_STACKED_CUSTOMERS = 3
DEFAULT_TOP_ITEMS = 4


def posting_month(posting_date: Any) -> str | None:
    if posting_date is None:
        return None
    text = str(posting_date).strip()
    if len(text) >= 7 and text[4] == "-":
        return text[:7]
    return None


def format_month_label(month_key: str) -> str:
    year, month = month_key.split("-", 1)
    return f"{_MONTH_NAMES[int(month) - 1]} '{year[2:]}"


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _month_keys(rows: list[dict[str, Any]], *, limit: int = DEFAULT_MONTH_LIMIT) -> list[str]:
    months = sorted({posting_month(row.get("postingDate")) for row in rows} - {None})
    if limit and len(months) > limit:
        months = months[-limit:]
    return months


def aggregate_revenue_by_month(
    rows: list[dict[str, Any]],
    *,
    limit: int = DEFAULT_MONTH_LIMIT,
) -> list[tuple[str, float]]:
    totals: dict[str, float] = defaultdict(float)
    for row in rows:
        month = posting_month(row.get("postingDate"))
        amount = _safe_float(row.get("netAmount"))
        if month is None or amount is None:
            continue
        totals[month] += amount

    months = sorted(totals)
    if limit and len(months) > limit:
        months = months[-limit:]
    return [(month, totals[month]) for month in months]


def aggregate_count_by_month(
    rows: list[dict[str, Any]],
    *,
    limit: int = DEFAULT_MONTH_LIMIT,
) -> list[tuple[str, float]]:
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        month = posting_month(row.get("postingDate"))
        if month is None:
            continue
        counts[month] += 1

    months = sorted(counts)
    if limit and len(months) > limit:
        months = months[-limit:]
    return [(month, float(counts[month])) for month in months]


def aggregate_sum_by_month(
    rows: list[dict[str, Any]],
    column: str,
    *,
    limit: int = DEFAULT_MONTH_LIMIT,
) -> list[tuple[str, float]]:
    totals: dict[str, float] = defaultdict(float)
    for row in rows:
        month = posting_month(row.get("postingDate"))
        value = _safe_float(row.get(column))
        if month is None or value is None:
            continue
        totals[month] += value

    months = sorted(totals)
    if limit and len(months) > limit:
        months = months[-limit:]
    return [(month, totals[month]) for month in months]


def aggregate_top_customers(
    rows: list[dict[str, Any]],
    *,
    limit: int = DEFAULT_TOP_CUSTOMERS,
) -> list[tuple[str, float]]:
    totals: dict[str, float] = defaultdict(float)
    labels: dict[str, str] = {}
    for row in rows:
        customer_id = str(row.get("customerId") or row.get("customerNumber") or "").strip()
        if not customer_id:
            continue
        amount = _safe_float(row.get("netAmount"))
        if amount is None:
            continue
        totals[customer_id] += amount
        name = str(row.get("customerName") or row.get("customerNumber") or customer_id).strip()
        labels[customer_id] = name

    ranked = sorted(totals.items(), key=lambda item: item[1], reverse=True)
    if limit:
        ranked = ranked[:limit]
    return [(labels[customer_id], amount) for customer_id, amount in ranked]


def aggregate_revenue_by_item(
    rows: list[dict[str, Any]],
    items: list[dict[str, Any]],
    *,
    limit: int = DEFAULT_TOP_ITEMS,
) -> list[tuple[str, float]]:
    item_labels = {
        str(item.get("id")): str(item.get("displayName") or item.get("number") or item.get("id"))
        for item in items
        if item.get("id") is not None
    }
    totals: dict[str, float] = defaultdict(float)
    for row in rows:
        item_id = str(row.get("itemId") or "").strip()
        if not item_id:
            continue
        amount = _safe_float(row.get("netAmount"))
        if amount is None:
            continue
        totals[item_id] += amount

    ranked = sorted(totals.items(), key=lambda item: item[1], reverse=True)
    top = ranked[:limit] if limit else ranked
    remainder = sum(amount for _item_id, amount in ranked[limit:]) if limit else 0.0

    result = [(item_labels.get(item_id, item_id), amount) for item_id, amount in top]
    if remainder > 0:
        result.append(("Other", remainder))
    return result


def aggregate_stacked_customer_revenue(
    rows: list[dict[str, Any]],
    *,
    month_limit: int = DEFAULT_MONTH_LIMIT,
    customer_limit: int = DEFAULT_STACKED_CUSTOMERS,
) -> tuple[list[str], list[tuple[str, list[float]]]]:
    months = _month_keys(rows, limit=month_limit)
    if not months:
        return [], []

    customer_totals: dict[str, float] = defaultdict(float)
    customer_labels: dict[str, str] = {}
    for row in rows:
        customer_id = str(row.get("customerId") or row.get("customerNumber") or "").strip()
        if not customer_id:
            continue
        amount = _safe_float(row.get("netAmount"))
        if amount is None:
            continue
        customer_totals[customer_id] += amount
        customer_labels[customer_id] = str(
            row.get("customerName") or row.get("customerNumber") or customer_id
        ).strip()

    top_ids = [
        customer_id
        for customer_id, _amount in sorted(customer_totals.items(), key=lambda item: item[1], reverse=True)[
            :customer_limit
        ]
    ]
    if not top_ids:
        return [], []

    month_index = {month: index for index, month in enumerate(months)}
    series_values: dict[str, list[float]] = {customer_id: [0.0] * len(months) for customer_id in top_ids}
    other_values = [0.0] * len(months)

    for row in rows:
        month = posting_month(row.get("postingDate"))
        if month not in month_index:
            continue
        amount = _safe_float(row.get("netAmount"))
        if amount is None:
            continue
        customer_id = str(row.get("customerId") or row.get("customerNumber") or "").strip()
        index = month_index[month]
        if customer_id in series_values:
            series_values[customer_id][index] += amount
        else:
            other_values[index] += amount

    categories = [format_month_label(month) for month in months]
    series = [(customer_labels[customer_id], series_values[customer_id]) for customer_id in top_ids]
    if any(value > 0 for value in other_values):
        series.append(("Other", other_values))
    return categories, series


def rolling_average(values: list[float], window: int = 3) -> list[float]:
    if not values:
        return []
    result: list[float] = []
    for index in range(len(values)):
        start = max(0, index - window + 1)
        chunk = values[start : index + 1]
        result.append(sum(chunk) / len(chunk))
    return result


def load_revenue_lines(settings: DnaSettings) -> list[dict[str, Any]]:
    return read_production_output(settings, REVENUE_OUTPUT_ID)


def load_items(settings: DnaSettings) -> list[dict[str, Any]]:
    return read_production_output(settings, ITEMS_OUTPUT_ID)
