"""Tests for source semantic model draft/publish and init workflow."""

from __future__ import annotations

from pathlib import Path

import pytest

from meshflow.dna.init_client import init_client_governance
from meshflow.dna.semantic_init import run_semantic_init
from meshflow.dna.semantic_model import (
    draft_differs_from_production,
    ensure_semantic_model_seed,
    evaluate_publish_readiness,
    load_production_semantic_model,
    load_semantic_model_draft,
    load_semantic_model_workflow,
    load_source_semantic_pack,
    publish_semantic_model,
    resolve_question,
    semantic_model_publish_gate,
    update_entity_status,
    update_relationship_status,
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


def _seed_minimal_silver(settings: DnaSettings) -> None:
    entities = {
        "customers": [{"id": "c1", "number": "C001", "displayName": "Acme"}],
        "items": [{"id": "i1", "number": "ITEM1", "displayName": "Widget"}],
        "sales_invoices": [{"id": "inv1", "customerId": "c1", "postingDate": "2024-01-15"}],
        "sales_invoice_lines": [
            {
                "id": "l1",
                "documentId": "inv1",
                "customerId": "c1",
                "itemId": "i1",
                "netAmount": 100.0,
                "postingDate": "2024-01-15",
            }
        ],
        "sales_orders": [{"id": "o1", "customerId": "c1", "orderDate": "2024-01-01"}],
        "sales_order_lines": [
            {
                "id": "ol1",
                "documentId": "o1",
                "customerId": "c1",
                "lineAmount": 50.0,
                "orderDate": "2024-01-01",
            }
        ],
        "sales_shipment_lines": [
            {"id": "sl1", "itemId": "i1", "quantity": 1},
        ],
    }
    for entity, rows in entities.items():
        out_dir = prefix_path(settings.data_dir, silver_entity_prefix(settings.source, entity))
        write_parquet_local(out_dir, "data.parquet", rows)


def test_source_semantic_pack_loads() -> None:
    pack = load_source_semantic_pack("dbc")
    assert pack is not None
    assert pack.get("entities")
    assert pack.get("relationships")


def test_init_client_seeds_semantic_model(seeded_settings: DnaSettings) -> None:
    draft = load_semantic_model_draft(seeded_settings)
    assert draft["status"] == "draft"
    assert draft["source"] == "dbc"


def test_semantic_init_profiles_silver(seeded_settings: DnaSettings) -> None:
    _seed_minimal_silver(seeded_settings)
    result = run_semantic_init(seeded_settings, username="admin@test.com")
    assert result["status"] == "initialized"
    assert result["entity_count"] >= 1
    assert result["relationship_count"] >= 1

    draft = load_semantic_model_draft(seeded_settings)
    workflow = load_semantic_model_workflow(seeded_settings)
    assert workflow.get("init_completed") is True
    assert any(str(e.get("role") or "") == "fact" for e in draft.get("entities") or [])


def _approve_for_publish(settings: DnaSettings, username: str = "admin@test.com") -> None:
    draft = load_semantic_model_draft(settings)
    for entity in draft.get("entities") or []:
        if str(entity.get("role") or "") == "fact":
            update_entity_status(settings, str(entity["id"]), "approved", username=username)
    for rel in draft.get("relationships") or []:
        update_relationship_status(settings, str(rel["id"]), "approved", username=username)
    for question in draft.get("questions") or []:
        if question.get("blocks_publish"):
            resolve_question(
                settings,
                str(question["id"]),
                username=username,
                resolution="Use posting date per starter pack.",
            )
    draft = load_semantic_model_draft(settings)
    for attribute in draft.get("attributes") or []:
        if attribute.get("concepts") and str(attribute.get("status") or "") == "proposed":
            attribute["status"] = "approved"
    from meshflow.dna.semantic_model import save_semantic_model_draft

    save_semantic_model_draft(settings, draft, username=username)


def test_publish_semantic_model(seeded_settings: DnaSettings) -> None:
    _seed_minimal_silver(seeded_settings)
    run_semantic_init(seeded_settings, username="admin@test.com")
    _approve_for_publish(seeded_settings)

    readiness = evaluate_publish_readiness(load_semantic_model_draft(seeded_settings))
    assert readiness["ready"], readiness.get("errors")

    published = publish_semantic_model(seeded_settings, username="admin@test.com")
    assert published["status"] == "production"
    assert published["version"] == "0.1.1"

    production = load_production_semantic_model(seeded_settings)
    assert production is not None
    assert not draft_differs_from_production(seeded_settings)


def test_gold_gate_blocks_until_published(seeded_settings: DnaSettings) -> None:
    _seed_minimal_silver(seeded_settings)
    run_semantic_init(seeded_settings, username="admin@test.com")

    gate = semantic_model_publish_gate(seeded_settings)
    assert gate.get("ready") is False
    assert gate.get("errors")

    _approve_for_publish(seeded_settings)
    publish_semantic_model(seeded_settings, username="admin@test.com")

    gate = semantic_model_publish_gate(seeded_settings)
    assert gate.get("ready") is True


def test_update_item_status_after_review(seeded_settings: DnaSettings) -> None:
    _seed_minimal_silver(seeded_settings)
    run_semantic_init(seeded_settings, username="admin@test.com")
    draft = load_semantic_model_draft(seeded_settings)
    entity_id = str((draft.get("entities") or [{}])[0].get("id") or "")
    rel_id = str((draft.get("relationships") or [{}])[0].get("id") or "")
    assert entity_id and rel_id

    update_entity_status(seeded_settings, entity_id, "rejected", username="admin@test.com")
    update_relationship_status(seeded_settings, rel_id, "approved", username="admin@test.com")

    draft = load_semantic_model_draft(seeded_settings)
    entity = next(e for e in draft["entities"] if e["id"] == entity_id)
    rel = next(r for r in draft["relationships"] if r["id"] == rel_id)
    assert entity["status"] == "rejected"
    assert rel["status"] == "approved"

    update_entity_status(seeded_settings, entity_id, "approved", username="admin@test.com")
    update_relationship_status(seeded_settings, rel_id, "proposed", username="admin@test.com")

    draft = load_semantic_model_draft(seeded_settings)
    entity = next(e for e in draft["entities"] if e["id"] == entity_id)
    rel = next(r for r in draft["relationships"] if r["id"] == rel_id)
    assert entity["status"] == "approved"
    assert rel["status"] == "proposed"
