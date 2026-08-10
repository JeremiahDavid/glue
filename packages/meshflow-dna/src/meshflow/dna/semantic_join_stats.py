"""Profile-driven join and primary-key statistics from silver data."""

from __future__ import annotations

from typing import Any

from meshflow.dna.field_semantics import preview_silver_entity
from meshflow.dna.settings import DnaSettings

_DEFAULT_ROW_LIMIT = 5000


def _normalized_cell(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def compute_primary_key_stats(
    settings: DnaSettings,
    entity: str,
    column: str,
    *,
    row_limit: int = _DEFAULT_ROW_LIMIT,
) -> dict[str, Any]:
    """Return uniqueness stats for a candidate primary key across the full sampled table."""
    entity_name = entity.strip().lower()
    column_name = column.strip()
    rows = preview_silver_entity(settings, entity_name, limit=row_limit)
    row_count = len(rows)
    values: list[str] = []
    null_count = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        normalized = _normalized_cell(row.get(column_name))
        if normalized is None:
            null_count += 1
        else:
            values.append(normalized)

    distinct_count = len(set(values))
    non_null_count = len(values)
    duplicate_value_count = max(0, non_null_count - distinct_count)
    pk_unique = row_count > 0 and null_count == 0 and distinct_count == row_count

    return {
        "row_count": row_count,
        "non_null_count": non_null_count,
        "null_count": null_count,
        "distinct_count": distinct_count,
        "duplicate_value_count": duplicate_value_count,
        "pk_unique": pk_unique,
        "null_rate": round(null_count / row_count, 4) if row_count else 0.0,
        "distinct_ratio": round(distinct_count / row_count, 4) if row_count else 0.0,
    }


def assert_primary_key_unique(
    settings: DnaSettings,
    entity: str,
    column: str,
    *,
    row_limit: int = _DEFAULT_ROW_LIMIT,
) -> dict[str, Any]:
    stats = compute_primary_key_stats(settings, entity, column, row_limit=row_limit)
    if stats["row_count"] == 0:
        raise ValueError(
            f"Cannot approve primary key {entity}.{column} — no silver rows found for this entity."
        )
    if not stats["pk_unique"]:
        raise ValueError(
            f"Primary key {entity}.{column} is not unique across the table "
            f"({stats['distinct_count']} distinct / {stats['row_count']} rows, "
            f"{stats['null_count']} nulls)."
        )
    return stats


def compute_join_stats(
    settings: DnaSettings,
    *,
    from_entity: str,
    from_column: str,
    to_entity: str,
    to_column: str,
    row_limit: int = _DEFAULT_ROW_LIMIT,
) -> dict[str, Any]:
    """Perform the proposed join in memory and return match/orphan/PK uniqueness stats."""
    from_name = from_entity.strip().lower()
    to_name = to_entity.strip().lower()
    from_col = from_column.strip()
    to_col = to_column.strip()

    from_rows = preview_silver_entity(settings, from_name, limit=row_limit)
    to_rows = preview_silver_entity(settings, to_name, limit=row_limit)

    from_row_count = len(from_rows)
    to_row_count = len(to_rows)

    fk_values: list[str] = []
    fk_null_count = 0
    for row in from_rows:
        if not isinstance(row, dict):
            continue
        normalized = _normalized_cell(row.get(from_col))
        if normalized is None:
            fk_null_count += 1
        else:
            fk_values.append(normalized)

    pk_values: list[str] = []
    pk_set: set[str] = set()
    pk_null_count = 0
    for row in to_rows:
        if not isinstance(row, dict):
            continue
        normalized = _normalized_cell(row.get(to_col))
        if normalized is None:
            pk_null_count += 1
        else:
            pk_values.append(normalized)
            pk_set.add(normalized)

    fk_non_null_count = len(fk_values)
    matched_count = sum(1 for value in fk_values if value in pk_set)
    orphan_count = fk_non_null_count - matched_count
    to_pk_distinct_count = len(pk_set)
    pk_unique = to_row_count > 0 and pk_null_count == 0 and to_pk_distinct_count == to_row_count

    return {
        "from_row_count": from_row_count,
        "to_row_count": to_row_count,
        "fk_non_null_count": fk_non_null_count,
        "fk_null_count": fk_null_count,
        "fk_null_rate": round(fk_null_count / from_row_count, 4) if from_row_count else 0.0,
        "matched_count": matched_count,
        "match_rate": round(matched_count / fk_non_null_count, 4) if fk_non_null_count else 0.0,
        "orphan_count": orphan_count,
        "orphan_rate": round(orphan_count / fk_non_null_count, 4) if fk_non_null_count else 0.0,
        "to_pk_distinct_count": to_pk_distinct_count,
        "to_pk_null_count": pk_null_count,
        "to_pk_duplicate_row_count": max(0, to_row_count - to_pk_distinct_count - pk_null_count),
        "pk_unique": pk_unique,
    }


def format_join_stats_summary(stats: dict[str, Any]) -> str:
    if not stats:
        return ""
    match_pct = int(round(float(stats.get("match_rate") or 0.0) * 100))
    orphan_pct = int(round(float(stats.get("orphan_rate") or 0.0) * 100))
    pk_label = "100%" if stats.get("pk_unique") else "No known PK"
    return f"Match {match_pct}% · Orphans {orphan_pct}% · Target PK {pk_label}"


def format_pk_stats_summary(stats: dict[str, Any]) -> str:
    if not stats:
        return ""
    if int(stats.get("row_count") or 0) == 0:
        return "Empty table"
    if stats.get("pk_unique"):
        return "100% unique"
    return "No known PK"
