"""Normalize silver column names for Athena/Hive unquoted identifiers."""

from __future__ import annotations

import re
from typing import Any

_NON_IDENT_CHARS = re.compile(r"[^a-zA-Z0-9_]+")
_MULTI_UNDERSCORE = re.compile(r"_+")


def normalize_silver_column_name(name: str) -> str:
    """Return a SQL-safe column name that does not require quoting in Athena."""
    raw = str(name or "").strip()
    if not raw:
        return "_"

    if raw.startswith("@"):
        raw = raw[1:]

    normalized = raw.replace(".", "_")
    normalized = _NON_IDENT_CHARS.sub("_", normalized)
    normalized = _MULTI_UNDERSCORE.sub("_", normalized).strip("_")
    if not normalized:
        normalized = "_"
    if normalized[0].isdigit():
        normalized = f"_{normalized}"
    return normalized


def normalize_silver_row(row: dict[str, Any]) -> dict[str, Any]:
    """Rename row keys to silver-safe identifiers, resolving rare collisions."""
    normalized: dict[str, Any] = {}
    for key, value in row.items():
        target = normalize_silver_column_name(key)
        if target in normalized:
            suffix = 2
            candidate = f"{target}_{suffix}"
            while candidate in normalized:
                suffix += 1
                candidate = f"{target}_{suffix}"
            target = candidate
        normalized[target] = value
    return normalized


def normalize_silver_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [normalize_silver_row(row) for row in rows]
