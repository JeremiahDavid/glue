"""Silver column profiling for LLM-assisted semantic tagging."""

from __future__ import annotations

import math
from datetime import date, datetime
from typing import Any

from meshflow.dna.field_semantics import discover_silver_columns, preview_silver_entity
from meshflow.dna.settings import DnaSettings


def _sample_values(values: list[Any], *, limit: int = 5) -> list[str]:
    seen: list[str] = []
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.append(text[:120])
        if len(seen) >= limit:
            break
    return seen


def _infer_dtype(values: list[Any]) -> str:
    if not values:
        return "unknown"
    boolish = all(isinstance(value, bool) for value in values)
    if boolish:
        return "boolean"
    numeric = 0
    for value in values:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            numeric += 1
            continue
        try:
            float(str(value))
            numeric += 1
        except ValueError:
            pass
    if numeric >= max(1, int(len(values) * 0.8)):
        return "number"
    dateish = 0
    for value in values:
        if isinstance(value, (date, datetime)):
            dateish += 1
            continue
        text = str(value).strip()
        if len(text) >= 8 and text[4:5] == "-" and text[7:8] == "-":
            dateish += 1
    if dateish >= max(1, int(len(values) * 0.6)):
        return "date"
    return "string"


def profile_silver_column(
    settings: DnaSettings,
    entity: str,
    column: str,
    *,
    rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Profile one silver column using sample rows and simple stats."""
    entity_name = entity.strip().lower()
    column_name = column.strip()
    sample_rows = rows if rows is not None else preview_silver_entity(settings, entity_name, limit=500)
    values = [
        row.get(column_name)
        for row in sample_rows
        if isinstance(row, dict) and column_name in row
    ]
    non_null = [value for value in values if value is not None and str(value).strip() != ""]
    row_count = len(sample_rows)
    non_null_count = len(non_null)
    null_rate = 0.0
    if values:
        null_rate = round(1.0 - (non_null_count / len(values)), 4)
    distinct = {str(value) for value in non_null}
    return {
        "entity": entity_name,
        "column": column_name,
        "row_count": row_count,
        "non_null_count": non_null_count,
        "null_rate": null_rate,
        "distinct_count": len(distinct),
        "sample_values": _sample_values(non_null),
        "inferred_dtype": _infer_dtype(non_null),
    }


def profile_entity_columns(
    settings: DnaSettings,
    entity: str,
    *,
    columns: list[str] | None = None,
    rows: list[dict[str, Any]] | None = None,
    row_limit: int = 500,
) -> dict[str, dict[str, Any]]:
    """Profile all (or selected) columns for a silver entity."""
    entity_name = entity.strip().lower()
    column_names = columns or discover_silver_columns(settings, entity_name)
    sample_rows = rows if rows is not None else preview_silver_entity(settings, entity_name, limit=row_limit)
    return {
        column: profile_silver_column(settings, entity_name, column, rows=sample_rows)
        for column in column_names
    }


def profile_summary_text(profile: dict[str, Any]) -> str:
    """Compact human-readable profile for LLM prompts."""
    samples = ", ".join(profile.get("sample_values") or []) or "(none)"
    null_pct = int(float(profile.get("null_rate") or 0) * 100)
    entity = profile.get("entity") or ""
    return (
        f"entity={entity} column={profile.get('column')} "
        f"dtype={profile.get('inferred_dtype')} null_rate={null_pct}% "
        f"distinct={profile.get('distinct_count')} samples={samples}"
    )
