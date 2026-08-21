"""Validate connector knowledge YAML against the connector-knowledge JSON schema."""

from __future__ import annotations

import json
from functools import lru_cache
from importlib.resources import files
from typing import Any

import jsonschema

_SCHEMA_RESOURCE = "schema/connector-knowledge.schema.json"
_DEFAULT_OUTPUT_COLUMN = "_row_key"


@lru_cache(maxsize=1)
def _load_schema() -> dict[str, Any]:
    text = files("meshflow.dna").joinpath(_SCHEMA_RESOURCE).read_text(encoding="utf-8")
    return json.loads(text)


def validate_connector_knowledge(payload: dict[str, Any]) -> None:
    """Raise jsonschema.ValidationError when payload is invalid."""
    jsonschema.validate(payload, _load_schema())
    _validate_entity_key_consistency(payload)


def _validate_entity_key_consistency(payload: dict[str, Any]) -> None:
    for item in payload.get("entities") or []:
        if not isinstance(item, dict):
            continue
        silver = str(item.get("silver_entity") or "").strip()
        natural = item.get("natural_key_columns") or []
        derivation = item.get("key_derivation")
        if not isinstance(natural, list):
            raise ValueError(f"entities[{silver}].natural_key_columns must be a list")
        if derivation is not None and not isinstance(derivation, dict):
            raise ValueError(f"entities[{silver}].key_derivation must be a mapping")
        if derivation:
            columns = derivation.get("columns") or []
            if not columns:
                raise ValueError(f"entities[{silver}].key_derivation.columns is required")
            if natural and list(natural) != list(columns):
                raise ValueError(
                    f"entities[{silver}]: natural_key_columns must match key_derivation.columns"
                )
            output_column = str(derivation.get("output_column") or _DEFAULT_OUTPUT_COLUMN).strip()
            primary_key = str(item.get("primary_key") or "").strip()
            if primary_key and primary_key != output_column:
                raise ValueError(
                    f"entities[{silver}]: primary_key must equal key_derivation.output_column "
                    f"({output_column!r}) when key_derivation is set"
                )


def normalize_entity_key_config(item: dict[str, Any]) -> dict[str, Any] | None:
    """Return a normalized silver key config for one entity, or None when not configured."""
    derivation = item.get("key_derivation")
    if not isinstance(derivation, dict):
        return None
    columns = [str(column).strip() for column in derivation.get("columns") or [] if str(column).strip()]
    if not columns:
        return None
    method = str(derivation.get("method") or "hash").strip().lower()
    if method not in {"hash", "concat"}:
        raise ValueError(f"key_derivation.method must be hash or concat for {item.get('silver_entity')}")
    output_column = str(derivation.get("output_column") or _DEFAULT_OUTPUT_COLUMN).strip()
    natural = item.get("natural_key_columns")
    natural_columns = (
        [str(column).strip() for column in natural if str(column).strip()]
        if isinstance(natural, list)
        else columns
    )
    return {
        "natural_key_columns": natural_columns,
        "key_derivation": {
            "method": method,
            "columns": columns,
            "separator": str(derivation.get("separator") or "|"),
            "output_column": output_column,
        },
        "primary_key": str(item.get("primary_key") or output_column).strip() or output_column,
    }


def entity_key_configs_from_hints(hints: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Map silver_entity -> normalized key config from connector knowledge."""
    configs: dict[str, dict[str, Any]] = {}
    for item in hints.get("entities") or []:
        if not isinstance(item, dict):
            continue
        silver = str(item.get("silver_entity") or "").strip().lower()
        if not silver:
            continue
        normalized = normalize_entity_key_config(item)
        if normalized:
            configs[silver] = normalized
    return configs
