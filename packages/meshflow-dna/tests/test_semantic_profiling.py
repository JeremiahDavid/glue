"""Tests for silver column profiling."""

from __future__ import annotations

from pathlib import Path

import pytest

from meshflow.dna.init_client import init_client_governance
from meshflow.dna.semantic_profiling import profile_entity_columns, profile_silver_column
from meshflow.dna.semantic_model import ensure_semantic_model_seed
from meshflow.dna.settings import DnaSettings
from meshflow.ingest.storage import write_parquet_local
from meshflow.storage.paths import prefix_path, silver_entity_prefix


@pytest.fixture
def seeded_settings(tmp_path: Path) -> DnaSettings:
    settings = DnaSettings(source="dbc", data_dir=tmp_path, company="POC")
    init_client_governance(settings, company="POC")
    ensure_semantic_model_seed(settings)
    return settings


def test_profile_silver_column_computes_stats(seeded_settings: DnaSettings) -> None:
    out_dir = prefix_path(
        seeded_settings.data_dir,
        silver_entity_prefix(seeded_settings.source, "customers"),
    )
    write_parquet_local(
        out_dir,
        "data.parquet",
        [
            {"id": "c1", "displayName": "Acme", "number": "C001"},
            {"id": "c2", "displayName": "Beta", "number": None},
        ],
    )
    profile = profile_silver_column(seeded_settings, "customers", "displayName")
    assert profile["distinct_count"] == 2
    assert profile["inferred_dtype"] == "string"
    assert profile["null_rate"] == 0.0

    profiles = profile_entity_columns(seeded_settings, "customers")
    assert "displayName" in profiles
