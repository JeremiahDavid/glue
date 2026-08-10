"""Tests for join and primary-key statistics."""

from __future__ import annotations

from pathlib import Path

import pytest

from meshflow.dna.init_client import init_client_governance
from meshflow.dna.semantic_join_stats import (
    assert_primary_key_unique,
    compute_join_stats,
    compute_primary_key_stats,
    format_join_stats_summary,
    format_pk_stats_summary,
)
from meshflow.dna.semantic_model import (
    add_relationship_to_draft,
    build_relationships_from_approved_keys,
    ensure_semantic_model_seed,
    load_semantic_model_draft,
    save_semantic_model_draft,
)
from meshflow.dna.settings import DnaSettings
from meshflow.ingest.storage import write_parquet_local
from meshflow.storage.paths import prefix_path, silver_entity_prefix


@pytest.fixture
def seeded_settings(tmp_path: Path) -> DnaSettings:
    settings = DnaSettings(source="dbc", data_dir=tmp_path, company="POC")
    init_client_governance(settings, company="POC")
    customers = [{"id": "c1", "number": "C001"}]
    invoices = [{"id": "inv1", "customerId": "c1"}, {"id": "inv2", "customerId": "missing"}]
    for entity, rows in {"customers": customers, "sales_invoices": invoices}.items():
        out_dir = prefix_path(settings.data_dir, silver_entity_prefix(settings.source, entity))
        write_parquet_local(out_dir, "data.parquet", rows)
    return settings


def test_compute_primary_key_stats_detects_duplicates(seeded_settings: DnaSettings) -> None:
    out_dir = prefix_path(
        seeded_settings.data_dir,
        silver_entity_prefix(seeded_settings.source, "dupes"),
    )
    write_parquet_local(out_dir, "data.parquet", [{"id": "x"}, {"id": "x"}])
    stats = compute_primary_key_stats(seeded_settings, "dupes", "id")
    assert stats["pk_unique"] is False
    assert stats["duplicate_value_count"] == 1


def test_assert_primary_key_unique_rejects_bad_key(seeded_settings: DnaSettings) -> None:
    out_dir = prefix_path(
        seeded_settings.data_dir,
        silver_entity_prefix(seeded_settings.source, "dupes"),
    )
    write_parquet_local(out_dir, "data.parquet", [{"id": "x"}, {"id": "x"}])
    with pytest.raises(ValueError, match="not unique"):
        assert_primary_key_unique(seeded_settings, "dupes", "id")


def test_compute_join_stats_from_silver(seeded_settings: DnaSettings) -> None:
    stats = compute_join_stats(
        seeded_settings,
        from_entity="sales_invoices",
        from_column="customerId",
        to_entity="customers",
        to_column="id",
    )
    assert stats["fk_non_null_count"] == 2
    assert stats["matched_count"] == 1
    assert stats["orphan_count"] == 1
    assert stats["pk_unique"] is True
    assert "Match" in format_join_stats_summary(stats)
    assert "100%" in format_join_stats_summary(stats)


def test_format_pk_stats_summary_percent_or_unknown() -> None:
    unique_stats = {"pk_unique": True, "row_count": 10, "distinct_count": 10}
    assert format_pk_stats_summary(unique_stats) == "100% unique"
    assert format_pk_stats_summary({"pk_unique": False, "row_count": 10}) == "No known PK"


def test_build_relationships_only_from_approved_keys(seeded_settings: DnaSettings) -> None:
    ensure_semantic_model_seed(seeded_settings)
    draft = load_semantic_model_draft(seeded_settings)
    entity_names = {str(entity.get("silver_entity") or "") for entity in draft.get("entities") or []}
    for silver in ("customers", "sales_invoices"):
        if silver not in entity_names:
            draft.setdefault("entities", []).append(
                {
                    "id": f"ent_{silver}",
                    "silver_entity": silver,
                    "role": "reference",
                    "status": "proposed",
                }
            )
    for entity in draft.get("entities") or []:
        if str(entity.get("silver_entity") or "") == "customers":
            entity["primary_key"] = "id"
            entity["primary_key_status"] = "approved"
            entity["pk_stats"] = compute_primary_key_stats(seeded_settings, "customers", "id")
        if str(entity.get("silver_entity") or "") == "sales_invoices":
            entity["primary_key"] = "id"
            entity["primary_key_status"] = "approved"
            entity["pk_stats"] = compute_primary_key_stats(seeded_settings, "sales_invoices", "id")
    draft["attributes"] = [
        {
            "entity": "sales_invoices",
            "column": "customerId",
            "role": "foreign_key",
            "status": "approved",
            "fk_target_entity": "customers",
            "fk_target_column": "id",
        }
    ]
    save_semantic_model_draft(seeded_settings, draft, username="admin@test.com")

    result = build_relationships_from_approved_keys(seeded_settings, username="admin@test.com")
    assert result["added"] == 1
    rel = load_semantic_model_draft(seeded_settings)["relationships"][0]
    assert rel["join_stats"]["orphan_count"] == 1


def test_add_relationship_requires_approved_keys(seeded_settings: DnaSettings) -> None:
    ensure_semantic_model_seed(seeded_settings)
    with pytest.raises(ValueError, match="approved foreign key"):
        add_relationship_to_draft(
            seeded_settings,
            relationship={
                "id": "rel_test",
                "from_entity": "sales_invoices",
                "from_column": "customerId",
                "to_entity": "customers",
                "to_column": "id",
                "cardinality": "many_to_one",
                "status": "proposed",
            },
            username="admin@test.com",
        )
