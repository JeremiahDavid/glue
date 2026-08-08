"""Tests for automatic semantic init when silver is present."""

from __future__ import annotations

from pathlib import Path

import pytest

from meshflow.dna.init_client import init_client_governance
from meshflow.dna.semantic_init import maybe_auto_semantic_init, run_semantic_init
from meshflow.dna.semantic_model import ensure_semantic_model_seed, load_semantic_model_workflow
from meshflow.dna.settings import DnaSettings
from meshflow.ingest.storage import write_parquet_local
from meshflow.storage.paths import prefix_path, silver_entity_prefix


@pytest.fixture
def seeded_settings(tmp_path: Path) -> DnaSettings:
    settings = DnaSettings(source="dbc", data_dir=tmp_path, company="POC")
    init_client_governance(settings, company="POC")
    ensure_semantic_model_seed(settings)
    return settings


def test_maybe_auto_semantic_init_skips_without_silver(
    seeded_settings: DnaSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "meshflow.dna.semantic_init.list_silver_entities",
        lambda _settings: [],
    )
    result = maybe_auto_semantic_init(seeded_settings)
    assert result["status"] == "skipped"
    assert result["reason"] == "no_silver_entities"


def test_maybe_auto_semantic_init_runs_once(
    seeded_settings: DnaSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MESHFLOW_SEMANTIC_LLM_TAGGING", "0")
    out_dir = prefix_path(
        seeded_settings.data_dir,
        silver_entity_prefix(seeded_settings.source, "customers"),
    )
    write_parquet_local(out_dir, "data.parquet", [{"id": "c1", "displayName": "Acme"}])

    first = maybe_auto_semantic_init(seeded_settings)
    assert first["status"] == "initialized"
    workflow = load_semantic_model_workflow(seeded_settings)
    assert workflow.get("init_completed") is True

    second = maybe_auto_semantic_init(seeded_settings)
    assert second["status"] == "skipped"
    assert second["reason"] == "init_already_completed"


def test_run_semantic_init_can_skip_llm(
    seeded_settings: DnaSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    out_dir = prefix_path(
        seeded_settings.data_dir,
        silver_entity_prefix(seeded_settings.source, "customers"),
    )
    write_parquet_local(out_dir, "data.parquet", [{"id": "c1", "displayName": "Acme"}])

    def _boom(*_args, **_kwargs):
        raise AssertionError("LLM tagging should be skipped")

    monkeypatch.setattr(
        "meshflow.dna.semantic_column_tagger.apply_llm_tags_to_attributes",
        _boom,
    )
    result = run_semantic_init(seeded_settings, username="tester", enable_llm_tagging=False)
    assert result["status"] == "initialized"
    assert result["llm_tagging"]["reason"] == "disabled"
