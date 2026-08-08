"""Tests for semantic model → DNA pack codegen."""

from __future__ import annotations

from pathlib import Path

import pytest

from meshflow.dna.init_client import init_client_governance
from meshflow.dna.semantic_codegen import apply_semantic_model_to_dna_pack, codegen_dna_sections
from meshflow.dna.semantic_model import ensure_semantic_model_seed
from meshflow.dna.settings import DnaSettings
from meshflow.dna.workflow import load_production_pack


@pytest.fixture
def seeded_settings(tmp_path: Path) -> DnaSettings:
    settings = DnaSettings(source="dbc", data_dir=tmp_path, company="POC")
    init_client_governance(settings, company="POC")
    ensure_semantic_model_seed(settings)
    return settings


def _sample_model() -> dict:
    return {
        "entities": [
            {
                "id": "ent_customers",
                "silver_entity": "customers",
                "role": "dimension",
                "grain": "customer",
                "primary_key": "id",
                "status": "approved",
            },
            {
                "id": "ent_sales_invoice_lines",
                "silver_entity": "sales_invoice_lines",
                "role": "fact",
                "grain": "line",
                "primary_key": "id",
                "status": "approved",
            },
        ],
        "relationships": [
            {
                "id": "rel_invoice_line_customer",
                "from_entity": "sales_invoice_lines",
                "from_column": "customerId",
                "to_entity": "customers",
                "to_column": "id",
                "cardinality": "many_to_one",
                "status": "approved",
            }
        ],
        "attributes": [
            {
                "entity": "customers",
                "column": "displayName",
                "concepts": ["customer_name"],
                "status": "approved",
            },
            {
                "entity": "sales_invoice_lines",
                "column": "netAmount",
                "concepts": ["revenue"],
                "status": "proposed",
            },
        ],
    }


def test_codegen_dna_sections_maps_join_ids_and_dimensions() -> None:
    sections = codegen_dna_sections(_sample_model())
    assert len(sections["entities"]) == 2
    assert sections["joins"][0]["id"] == "join_invoice_line_customer"
    assert sections["joins"][0]["left_entity"] == "ent_sales_invoice_lines"
    assert sections["dimensions"][0]["id"] == "dim_customer_name"
    assert sections["dimensions"][0]["entity_id"] == "ent_customers"
    # Fact-line revenue tags are not promoted to dimensions.
    assert all(dim["entity_id"] != "ent_sales_invoice_lines" for dim in sections["dimensions"])


def test_apply_semantic_model_to_dna_pack_bumps_version(seeded_settings: DnaSettings) -> None:
    before = load_production_pack(seeded_settings)
    result = apply_semantic_model_to_dna_pack(
        seeded_settings,
        _sample_model(),
        username="admin@test.com",
    )
    assert result["status"] == "synced"
    assert result["entity_count"] == 2
    assert result["join_count"] == 1
    after = load_production_pack(seeded_settings)
    assert after.version != before.version
    assert any(e.id == "ent_customers" for e in after.entities)
