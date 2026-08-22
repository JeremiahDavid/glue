"""Fiscal / calendar period attribution for DNA compile."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any


@dataclass(frozen=True)
class PeriodAttrs:
    fiscal_year: int
    fiscal_period: int
    period_key: str
    prior_year_period_key: str


def parse_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        if "T" in text:
            return datetime.fromisoformat(text).date()
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def period_attrs_for_date(
    value: date,
    *,
    fiscal_year_start_month: int = 1,
    period_grain: str = "month",
) -> PeriodAttrs:
    start = max(1, min(12, fiscal_year_start_month))
    if start == 1:
        fiscal_year = value.year
        month_offset = value.month - 1
    elif value.month >= start:
        fiscal_year = value.year + 1
        month_offset = value.month - start
    else:
        fiscal_year = value.year
        month_offset = value.month - start + 12

    if period_grain == "quarter":
        fiscal_period = month_offset // 3 + 1
        period_key = f"FY{fiscal_year}-Q{fiscal_period:02d}"
        prior_year_period_key = f"FY{fiscal_year - 1}-Q{fiscal_period:02d}"
    else:
        fiscal_period = month_offset + 1
        period_key = f"FY{fiscal_year}-P{fiscal_period:02d}"
        prior_year_period_key = f"FY{fiscal_year - 1}-P{fiscal_period:02d}"

    return PeriodAttrs(
        fiscal_year=fiscal_year,
        fiscal_period=fiscal_period,
        period_key=period_key,
        prior_year_period_key=prior_year_period_key,
    )


def attach_period_columns(
    rows: list[dict[str, Any]],
    *,
    date_column: str,
    fiscal_year_start_month: int = 1,
    period_grain: str = "month",
) -> list[dict[str, Any]]:
    stamped: list[dict[str, Any]] = []
    for row in rows:
        enriched = dict(row)
        parsed = parse_date(row.get(date_column))
        if parsed is None:
            enriched["fiscal_year"] = None
            enriched["fiscal_period"] = None
            enriched["period_key"] = None
            enriched["prior_year_period_key"] = None
        else:
            attrs = period_attrs_for_date(
                parsed,
                fiscal_year_start_month=fiscal_year_start_month,
                period_grain=period_grain,
            )
            enriched["fiscal_year"] = attrs.fiscal_year
            enriched["fiscal_period"] = attrs.fiscal_period
            enriched["period_key"] = attrs.period_key
            enriched["prior_year_period_key"] = attrs.prior_year_period_key
        stamped.append(enriched)
    return stamped
