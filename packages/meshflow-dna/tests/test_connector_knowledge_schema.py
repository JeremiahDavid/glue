"""Tests for connector knowledge schema validation and key config helpers."""

from __future__ import annotations

import pytest

from meshflow.dna.bc_profiling_rules import load_profiling_rules
from meshflow.dna.connector_knowledge_schema import (
    entity_key_configs_from_hints,
    normalize_entity_key_config,
    validate_connector_knowledge,
)


def test_load_profiling_rules_validates_against_schema() -> None:
    rules = load_profiling_rules("dbc")
    assert rules.get("source") == "dbc"
    trial = next(item for item in rules["entities"] if item["silver_entity"] == "trial_balances")
    assert trial["primary_key"] == "_row_key"
    assert trial["natural_key_columns"] == ["accountId", "dateFilter"]


def test_normalize_entity_key_config() -> None:
    config = normalize_entity_key_config(
        {
            "silver_entity": "trial_balances",
            "natural_key_columns": ["accountId", "dateFilter"],
            "key_derivation": {
                "method": "hash",
                "columns": ["accountId", "dateFilter"],
                "output_column": "_row_key",
            },
            "primary_key": "_row_key",
        }
    )
    assert config is not None
    assert config["primary_key"] == "_row_key"


def test_validate_rejects_mismatched_primary_key_and_derivation() -> None:
    with pytest.raises(ValueError, match="primary_key must equal"):
        validate_connector_knowledge(
            {
                "entities": [
                    {
                        "silver_entity": "trial_balances",
                        "natural_key_columns": ["accountId", "dateFilter"],
                        "key_derivation": {
                            "method": "hash",
                            "columns": ["accountId", "dateFilter"],
                            "output_column": "_row_key",
                        },
                        "primary_key": "id",
                    }
                ]
            }
        )


def test_entity_key_configs_from_hints() -> None:
    configs = entity_key_configs_from_hints(
        {
            "entities": [
                {
                    "silver_entity": "trial_balances",
                    "natural_key_columns": ["accountId", "dateFilter"],
                    "key_derivation": {
                        "method": "concat",
                        "columns": ["accountId", "dateFilter"],
                        "separator": "|",
                        "output_column": "_row_key",
                    },
                    "primary_key": "_row_key",
                }
            ]
        }
    )
    assert "trial_balances" in configs
    assert configs["trial_balances"]["key_derivation"]["method"] == "concat"
