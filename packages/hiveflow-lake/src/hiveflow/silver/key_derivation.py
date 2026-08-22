"""Derive stable row keys in silver from connector natural-key column sets."""

from __future__ import annotations

import hashlib
from functools import lru_cache
from typing import Any

_DEFAULT_OUTPUT_COLUMN = "_row_key"
_COMPONENT_SEP = "\x1f"


def normalize_key_component(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def derive_row_key(row: dict[str, Any], *, method: str, columns: list[str], separator: str = "|") -> str | None:
    """Return a deterministic key for one row, or None when required components are missing."""
    parts = [normalize_key_component(row.get(column)) for column in columns]
    if any(not part for part in parts):
        return None
    if method == "concat":
        return separator.join(parts)
    digest = hashlib.sha256(_COMPONENT_SEP.join(parts).encode("utf-8")).hexdigest()
    return digest


def apply_key_derivation_to_row(row: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    derivation = config.get("key_derivation") or {}
    columns = [str(column).strip() for column in derivation.get("columns") or [] if str(column).strip()]
    if not columns:
        return row
    method = str(derivation.get("method") or "hash").strip().lower()
    separator = str(derivation.get("separator") or "|")
    output_column = str(derivation.get("output_column") or _DEFAULT_OUTPUT_COLUMN).strip()
    derived = derive_row_key(row, method=method, columns=columns, separator=separator)
    if derived is None:
        return row
    updated = dict(row)
    updated[output_column] = derived
    return updated


def apply_key_derivation_to_rows(rows: list[dict[str, Any]], config: dict[str, Any]) -> list[dict[str, Any]]:
    if not config:
        return rows
    return [apply_key_derivation_to_row(row, config) for row in rows]


@lru_cache(maxsize=16)
def load_entity_key_configs(source: str) -> dict[str, dict[str, Any]]:
    """Load per-entity key derivation config from connector profiling rules when available."""
    connector = source.strip().lower()
    payload = _load_connector_profiling_rules(connector)
    if not payload:
        return {}
    return _entity_key_configs_without_schema(payload)


def entity_key_config(source: str, entity_name: str) -> dict[str, Any] | None:
    return load_entity_key_configs(source).get(entity_name.strip().lower())


def _entity_key_configs_without_schema(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    configs: dict[str, dict[str, Any]] = {}
    for item in payload.get("entities") or []:
        if not isinstance(item, dict):
            continue
        silver = str(item.get("silver_entity") or "").strip().lower()
        derivation = item.get("key_derivation")
        if not silver or not isinstance(derivation, dict):
            continue
        columns = [str(column).strip() for column in derivation.get("columns") or [] if str(column).strip()]
        if not columns:
            continue
        method = str(derivation.get("method") or "hash").strip().lower()
        output_column = str(derivation.get("output_column") or _DEFAULT_OUTPUT_COLUMN).strip()
        configs[silver] = {
            "natural_key_columns": list(item.get("natural_key_columns") or columns),
            "key_derivation": {
                "method": method,
                "columns": columns,
                "separator": str(derivation.get("separator") or "|"),
                "output_column": output_column,
            },
            "primary_key": str(item.get("primary_key") or output_column).strip() or output_column,
        }
    return configs


def _load_connector_profiling_rules(source: str) -> dict[str, Any]:
    try:
        from importlib.resources import files

        import yaml

        path = files("meshflow.dna").joinpath("packs", "connector_knowledge", source, "profiling_rules.yaml")
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (ImportError, FileNotFoundError, ModuleNotFoundError, TypeError):
        return {}
