"""Tests for latest per-source profiling baseline."""

from __future__ import annotations

from pathlib import Path

import pytest

from meshflow.dna.init_client import init_client_governance
from meshflow.dna.semantic_init import run_semantic_init
from meshflow.dna.semantic_knowledge_base import load_tenant_semantic_overrides, merge_semantic_hints
from meshflow.dna.semantic_model import ensure_semantic_model_seed, publish_semantic_model
from meshflow.dna.semantic_source_profile import (
    build_latest_source_profile,
    ensure_latest_source_profile,
    latest_profile_to_hints,
    load_latest_source_profile,
    load_profiling_baseline_hints,
    rebuild_latest_source_profile,
)
from meshflow.dna.settings import DnaSettings
from meshflow.ingest.storage import write_parquet_local
from meshflow.storage.paths import prefix_path, silver_entity_prefix


@pytest.fixture
def seeded_settings(tmp_path: Path) -> DnaSettings:
    settings = DnaSettings(source="dbc", data_dir=tmp_path, company="POC")
    init_client_governance(settings, company="POC")
    ensure_semantic_model_seed(settings)
    return settings


def _seed_customers(settings: DnaSettings) -> None:
    out_dir = prefix_path(settings.data_dir, silver_entity_prefix(settings.source, "customers"))
    write_parquet_local(out_dir, "data.parquet", [{"id": "c1", "number": "C001"}])


def test_build_latest_profile_from_documentation(seeded_settings: DnaSettings) -> None:
    profile = build_latest_source_profile(seeded_settings)
    assert profile["baseline"] == "latest_source_profile"
    assert profile["documentation_included"] is True
    assert int(profile.get("approved_build_count") or 0) == 0
    assert len(profile.get("entities") or []) >= 70
    assert len(profile.get("column_hints") or {}) >= 100


def test_ensure_builds_once_then_reuses(seeded_settings: DnaSettings) -> None:
    first = ensure_latest_source_profile(seeded_settings)
    assert first["built"] is True
    second = ensure_latest_source_profile(seeded_settings)
    assert second["built"] is False
    assert load_latest_source_profile(seeded_settings) is not None


def test_init_reads_latest_profile_not_live_docs_merge(
    seeded_settings: DnaSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_customers(seeded_settings)
    ensure_latest_source_profile(seeded_settings)

    def _fail_docs(*_args, **_kwargs):
        raise AssertionError("init should not rebuild documentation baseline during profiling")

    monkeypatch.setattr(
        "meshflow.dna.semantic_source_profile._documentation_baseline",
        _fail_docs,
    )
    result = run_semantic_init(seeded_settings, username="tester", enable_llm_tagging=False)
    assert result["status"] == "initialized"
    assert result["baseline_profile"]["built"] is False


def test_publish_rebuilds_latest_profile(
    seeded_settings: DnaSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_customers(seeded_settings)
    ensure_latest_source_profile(seeded_settings)
    before = load_latest_source_profile(seeded_settings)
    assert before is not None
    before_at = before.get("generated_at")

    run_semantic_init(seeded_settings, username="tester", enable_llm_tagging=False)
    from meshflow.dna.semantic_model import load_semantic_model_draft, save_semantic_model_draft

    draft = load_semantic_model_draft(seeded_settings)
    for entity in draft.get("entities") or []:
        entity["status"] = "approved"
        entity["primary_key_status"] = "approved"
    for attribute in draft.get("attributes") or []:
        attribute["status"] = "approved"
    for rel in draft.get("relationships") or []:
        rel["status"] = "approved"
    save_semantic_model_draft(seeded_settings, draft, username="tester")

    from meshflow.dna import semantic_model as semantic_model_module

    monkeypatch.setattr(
        semantic_model_module,
        "evaluate_publish_readiness",
        lambda _draft: {"ready": True, "errors": []},
    )
    publish_semantic_model(seeded_settings, username="tester")

    after = load_latest_source_profile(seeded_settings)
    assert after is not None
    assert int(after.get("approved_build_count") or 0) >= 1
    assert after.get("generated_at") != before_at


def test_load_profiling_baseline_hints_shape(seeded_settings: DnaSettings) -> None:
    rebuild_latest_source_profile(seeded_settings)
    hints = load_profiling_baseline_hints(seeded_settings)
    assert hints["baseline"] == "latest_source_profile"
    merged = merge_semantic_hints(hints, load_tenant_semantic_overrides(seeded_settings))
    assert merged["baseline"] == "latest_source_profile"
    converted = latest_profile_to_hints(load_latest_source_profile(seeded_settings) or {})
    assert converted["entities"]
