"""Tests for DNA Catalog silver discovery helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from meshflow.dna.field_semantics import discover_silver_columns, list_silver_entities, preview_silver_entity
from meshflow.dna.settings import DnaSettings
from meshflow.ingest.storage import write_parquet_local
from meshflow.storage.paths import prefix_path, silver_entity_prefix


@pytest.fixture
def settings(tmp_path: Path) -> DnaSettings:
    return DnaSettings(source="dbc", data_dir=tmp_path, company="POC")


def test_list_silver_entities_returns_catalog_names(settings: DnaSettings) -> None:
    names = list_silver_entities(settings)
    assert isinstance(names, list)
    assert all(isinstance(name, str) and name for name in names)


def test_discover_and_preview_silver_entity(settings: DnaSettings) -> None:
    out = prefix_path(settings.data_dir, silver_entity_prefix(settings.source, "customers"))
    write_parquet_local(
        out,
        "data.parquet",
        [{"id": "c1", "displayName": "Acme"}, {"id": "c2", "displayName": "Beta"}],
    )
    columns = discover_silver_columns(settings, "customers")
    assert "id" in columns
    assert "displayName" in columns
    rows = preview_silver_entity(settings, "customers", limit=1)
    assert len(rows) == 1
    assert rows[0]["id"] == "c1"
