"""Tests for profile-driven PK/FK inference."""

from __future__ import annotations

from pathlib import Path

import pytest

from meshflow.dna.init_client import init_client_governance
from meshflow.dna.semantic_init import run_semantic_init
from meshflow.dna.semantic_key_profiler import (
    propose_keys_from_profiling,
    propose_relationships_from_approved_keys,
    value_overlap_ratio,
)
from meshflow.dna.semantic_model import ensure_semantic_model_seed, load_semantic_model_draft
from meshflow.dna.settings import DnaSettings
from meshflow.ingest.storage import write_parquet_local
from meshflow.storage.paths import prefix_path, silver_entity_prefix


@pytest.fixture
def seeded_settings(tmp_path: Path) -> DnaSettings:
    settings = DnaSettings(source="dbc", data_dir=tmp_path, company="POC")
    init_client_governance(settings, company="POC")
    ensure_semantic_model_seed(settings)
    return settings


def _seed_order_to_cash(settings: DnaSettings) -> None:
    entities = {
        "customers": [{"id": "c1", "number": "C001"}, {"id": "c2", "number": "C002"}],
        "items": [{"id": "i1", "number": "ITEM1"}],
        "sales_invoice_lines": [
            {"id": "l1", "documentId": "inv1", "customerId": "c1", "itemId": "i1", "netAmount": 100.0},
            {"id": "l2", "documentId": "inv1", "customerId": "c2", "itemId": "i1", "netAmount": 50.0},
        ],
    }
    for entity, rows in entities.items():
        out_dir = prefix_path(settings.data_dir, silver_entity_prefix(settings.source, entity))
        write_parquet_local(out_dir, "data.parquet", rows)


def test_value_overlap_ratio_matches_fk_values(seeded_settings: DnaSettings) -> None:
    _seed_order_to_cash(seeded_settings)
    ratio = value_overlap_ratio(
        seeded_settings,
        from_entity="sales_invoice_lines",
        from_column="customerId",
        to_entity="customers",
        to_column="id",
    )
    assert ratio == 1.0


def test_propose_keys_from_profiling_prefers_id_pk(seeded_settings: DnaSettings) -> None:
    _seed_order_to_cash(seeded_settings)
    proposals = propose_keys_from_profiling(
        seeded_settings,
        ["customers", "items", "sales_invoice_lines"],
        {"entities": [{"silver_entity": "customers", "primary_key": "number"}]},
    )
    assert proposals["primary_keys"]["customers"]["column"] == "id"
    assert any(c["id"] == "conflict_pk_customers" for c in proposals["conflicts"])
    fk_cols = {item["column"] for item in proposals["foreign_keys"]["sales_invoice_lines"]}
    assert "customerId" in fk_cols
    assert "itemId" in fk_cols


def test_init_step1_leaves_relationships_empty(seeded_settings: DnaSettings) -> None:
    _seed_order_to_cash(seeded_settings)
    result = run_semantic_init(seeded_settings, username="tester", enable_llm_tagging=False)
    assert result["status"] == "initialized"
    draft = load_semantic_model_draft(seeded_settings)
    assert draft.get("relationships") == []
    customer = next(e for e in draft["entities"] if e["silver_entity"] == "customers")
    assert customer.get("primary_key") == "id"
    fk_attrs = [
        a for a in draft["attributes"] if a.get("role") == "foreign_key" and a.get("entity") == "sales_invoice_lines"
    ]
    assert any(a["column"] == "customerId" for a in fk_attrs)


def test_relationships_from_approved_keys(seeded_settings: DnaSettings) -> None:
    _seed_order_to_cash(seeded_settings)
    run_semantic_init(seeded_settings, username="tester", enable_llm_tagging=False)
    draft = load_semantic_model_draft(seeded_settings)
    for entity in draft["entities"]:
        if entity.get("primary_key"):
            entity["primary_key_status"] = "approved"
    for attribute in draft["attributes"]:
        if attribute.get("role") == "foreign_key":
            attribute["status"] = "approved"
    relationships = propose_relationships_from_approved_keys(
        seeded_settings,
        entities=draft["entities"],
        attributes=draft["attributes"],
    )
    joins = {
        (r["from_entity"], r["from_column"], r["to_entity"]) for r in relationships
    }
    assert ("sales_invoice_lines", "customerId", "customers") in joins
    assert ("sales_invoice_lines", "itemId", "items") in joins
