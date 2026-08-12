"""Tests for field semantics draft/publish workflow."""

from __future__ import annotations

from pathlib import Path

import pytest

from meshflow.dna.field_semantics import (
    catalog_concept_ids,
    discard_field_semantics_draft,
    draft_differs_from_production,
    ensure_field_semantics_seed,
    filter_catalog_concepts,
    load_field_semantics_draft,
    load_operational_concept_catalog,
    load_production_field_semantics,
    publish_field_semantics,
    save_field_semantics_draft,
    slugify_concept_id,
    validate_field_semantics_schema,
)
from meshflow.dna.init_client import init_client_governance
from meshflow.dna.settings import DnaSettings


@pytest.fixture
def seeded_settings(tmp_path: Path) -> DnaSettings:
    settings = DnaSettings(source="dbc", data_dir=tmp_path, company="POC")
    init_client_governance(settings, company="POC")
    return settings


def test_operational_concept_catalog_loads() -> None:
    catalog = load_operational_concept_catalog()
    assert catalog.get("categories")
    assert catalog.get("concepts")
    assert any(item.get("id") == "bill_to_customer" for item in catalog["concepts"])


def test_filter_catalog_concepts_resolves_aliases_and_drops_unknown() -> None:
    assert filter_catalog_concepts(["customer_id", "invoice_date"]) == ["customer_id", "posting_date"]
    assert filter_catalog_concepts(["starting_date"]) == []
    assert "customer_id" in catalog_concept_ids()


def test_init_client_seeds_field_semantics(seeded_settings: DnaSettings) -> None:
    draft = load_field_semantics_draft(seeded_settings)
    assert draft["status"] == "draft"
    assert draft["source"] == "dbc"
    assert draft["mappings"] == []


def test_save_and_publish_field_semantics(seeded_settings: DnaSettings) -> None:
    draft = load_field_semantics_draft(seeded_settings)
    draft["mappings"] = [
        {
            "silver_entity": "sales_invoice_lines",
            "column": "lineAmount",
            "concepts": ["revenue_amount"],
            "notes": "Primary revenue field",
        }
    ]
    saved = save_field_semantics_draft(seeded_settings, draft, username="admin@test.com")
    assert saved["mappings"][0]["concepts"] == ["revenue_amount"]
    assert draft_differs_from_production(seeded_settings)

    published = publish_field_semantics(seeded_settings, username="admin@test.com")
    assert published["status"] == "production"
    assert published["version"] == "1.0.1"

    production = load_production_field_semantics(seeded_settings)
    assert production is not None
    assert production["mappings"][0]["column"] == "lineAmount"
    assert not draft_differs_from_production(seeded_settings)


def test_custom_concept_validation(seeded_settings: DnaSettings) -> None:
    draft = load_field_semantics_draft(seeded_settings)
    draft["custom_concepts"] = [{"id": "freight_allocation", "label": "Freight allocation", "category": "cost"}]
    draft["mappings"] = [
        {
            "silver_entity": "sales_invoice_lines",
            "column": "amount",
            "concepts": ["freight_allocation"],
        }
    ]
    saved = save_field_semantics_draft(seeded_settings, draft, username="admin@test.com")
    validate_field_semantics_schema(saved)
    assert saved["custom_concepts"][0]["id"] == "freight_allocation"


def test_unknown_concept_rejected(seeded_settings: DnaSettings) -> None:
    draft = load_field_semantics_draft(seeded_settings)
    draft["mappings"] = [
        {
            "silver_entity": "customers",
            "column": "id",
            "concepts": ["not_a_real_concept"],
        }
    ]
    with pytest.raises(ValueError, match="Unknown concept"):
        save_field_semantics_draft(seeded_settings, draft, username="admin@test.com")


def test_discard_field_semantics_draft(seeded_settings: DnaSettings) -> None:
    draft = load_field_semantics_draft(seeded_settings)
    draft["mappings"] = [
        {
            "silver_entity": "customers",
            "column": "id",
            "concepts": ["primary_key"],
        }
    ]
    save_field_semantics_draft(seeded_settings, draft, username="admin@test.com")
    publish_field_semantics(seeded_settings, username="admin@test.com")

    mutated = load_field_semantics_draft(seeded_settings)
    mutated["mappings"].append(
        {
            "silver_entity": "items",
            "column": "id",
            "concepts": ["primary_key"],
        }
    )
    save_field_semantics_draft(seeded_settings, mutated, username="admin@test.com")
    assert draft_differs_from_production(seeded_settings)

    discard_field_semantics_draft(seeded_settings, username="admin@test.com")
    assert not draft_differs_from_production(seeded_settings)



def test_slugify_concept_id() -> None:
    assert slugify_concept_id("Freight Allocation") == "freight_allocation"


def test_ensure_field_semantics_seed_idempotent(seeded_settings: DnaSettings) -> None:
    first = ensure_field_semantics_seed(seeded_settings)
    second = ensure_field_semantics_seed(seeded_settings)
    assert first["status"] in {"initialized", "skipped"}
    assert second["status"] == "skipped"
