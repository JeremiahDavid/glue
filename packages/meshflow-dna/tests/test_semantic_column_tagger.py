"""Tests for LLM column tagging helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from meshflow.dna.init_client import init_client_governance
from meshflow.dna.semantic_column_tagger import (
    apply_llm_tags_to_attributes,
    suggest_column_tags,
)
from meshflow.dna.semantic_model import ensure_semantic_model_seed
from meshflow.dna.settings import DnaSettings


@pytest.fixture
def seeded_settings(tmp_path: Path) -> DnaSettings:
    settings = DnaSettings(source="dbc", data_dir=tmp_path, company="POC")
    init_client_governance(settings, company="POC")
    ensure_semantic_model_seed(settings)
    return settings


def test_suggest_column_tags_parses_json_response(seeded_settings: DnaSettings) -> None:
    def mock_invoke(_system: str, _user: str) -> str:
        return (
            '{"concepts": ["customer_name"], "confidence": 0.92, '
            '"notes": "Display name column", "citation": "Customers", "role": "dimension"}'
        )

    suggestion = suggest_column_tags(
        seeded_settings,
        entity="customers",
        profile={
            "entity": "customers",
            "column": "displayName",
            "inferred_dtype": "string",
            "null_rate": 0.0,
            "distinct_count": 10,
            "sample_values": ["Acme", "Beta"],
        },
        invoke_fn=mock_invoke,
    )
    assert suggestion.concepts == ["customer_name"]
    assert suggestion.confidence >= 0.9


def test_apply_llm_tags_skips_low_confidence(seeded_settings: DnaSettings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MESHFLOW_SEMANTIC_LLM_TAGGING", "1")
    monkeypatch.setenv("MESHFLOW_SEMANTIC_LLM_TAG_LIMIT", "5")

    from meshflow.ingest.storage import write_parquet_local
    from meshflow.storage.paths import prefix_path, silver_entity_prefix

    out_dir = prefix_path(
        seeded_settings.data_dir,
        silver_entity_prefix(seeded_settings.source, "customers"),
    )
    write_parquet_local(out_dir, "data.parquet", [{"id": "c1", "displayName": "Acme"}])

    def mock_invoke(_system: str, _user: str) -> str:
        return '{"concepts": ["customer_name"], "confidence": 0.2, "notes": "unsure"}'

    attributes = [
        {"entity": "customers", "column": "displayName", "status": "proposed"},
    ]
    result = apply_llm_tags_to_attributes(
        seeded_settings,
        attributes,
        entity_names={"customers"},
        invoke_fn=mock_invoke,
    )
    assert result["tagged_count"] == 0
    assert not attributes[0].get("concepts")
