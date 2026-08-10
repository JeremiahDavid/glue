"""Tests for source semantic model draft/publish and init workflow."""

from __future__ import annotations

from pathlib import Path

import pytest

from meshflow.dna.init_client import init_client_governance
from meshflow.dna.semantic_init import run_semantic_init
from meshflow.dna.semantic_model import (
    approve_proposed_keys,
    build_relationships_from_approved_keys,
    draft_differs_from_production,
    ensure_semantic_model_seed,
    evaluate_publish_readiness,
    generate_relationships_from_keys,
    load_production_semantic_model,
    load_semantic_model_draft,
    load_semantic_model_workflow,
    load_source_semantic_pack,
    publish_semantic_model,
    resolve_question,
    merge_preserved_questions,
    save_semantic_model_draft,
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
    assert result["relationship_count"] == 0

    draft = load_semantic_model_draft(seeded_settings)
    workflow = load_semantic_model_workflow(seeded_settings)
    assert workflow.get("init_completed") is True
    assert workflow.get("current_step") == "keys"
    assert any(str(e.get("role") or "") == "fact" for e in draft.get("entities") or [])


def _approve_for_publish(settings: DnaSettings, username: str = "admin@test.com") -> None:
    draft = load_semantic_model_draft(settings)
    for entity in draft.get("entities") or []:
        if entity.get("primary_key"):
            entity["primary_key_status"] = "approved"
        if str(entity.get("role") or "") == "fact":
            entity["status"] = "approved"
    for attribute in draft.get("attributes") or []:
        if str(attribute.get("role") or "") == "foreign_key":
            attribute["status"] = "approved"
    save_semantic_model_draft(settings, draft, username=username)
    build_relationships_from_approved_keys(settings, username=username)

    for question in load_semantic_model_draft(settings).get("questions") or []:
        if question.get("blocks_publish"):
            action = question.get("action") if isinstance(question.get("action"), dict) else {}
            choices = action.get("choices") or []
            first_choice = choices[0] if choices and isinstance(choices[0], dict) else {}
            resolve_question(
                settings,
                str(question["id"]),
                username=username,
                choice=str(first_choice.get("id") or ""),
                resolution="Resolved for publish test." if not first_choice else "",
            )

    draft = load_semantic_model_draft(settings)
    for rel in draft.get("relationships") or []:
        rel["status"] = "approved"
    for attribute in draft.get("attributes") or []:
        if attribute.get("concepts") and str(attribute.get("status") or "") == "proposed":
            attribute["status"] = "approved"
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
    _approve_for_publish(seeded_settings)
    draft = load_semantic_model_draft(seeded_settings)
    entity_id = str((draft.get("entities") or [{}])[0].get("id") or "")
    rel_id = str((draft.get("relationships") or [{}])[0].get("id") or "")
    assert entity_id and rel_id, "expected relationships after key approval workflow"

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


def test_generate_relationships_from_proposed_keys(seeded_settings: DnaSettings) -> None:
    _seed_minimal_silver(seeded_settings)
    run_semantic_init(seeded_settings, username="admin@test.com", enable_llm_tagging=False)

    result = generate_relationships_from_keys(seeded_settings, username="admin@test.com")
    draft = load_semantic_model_draft(seeded_settings)
    assert result["keys_approved"]["primary_keys_approved"] >= 1
    assert result["added"] >= 1
    assert draft.get("relationships")
    _seed_minimal_silver(seeded_settings)
    run_semantic_init(seeded_settings, username="admin@test.com", enable_llm_tagging=False)

    draft = load_semantic_model_draft(seeded_settings)
    draft.setdefault("questions", []).append(
        {
            "id": "conflict_pk_customers",
            "text": "Primary key for customers: profiling suggests 'id' but documentation specifies 'number'.",
            "status": "open",
            "action": {
                "type": "primary_key",
                "entity": "customers",
                "choices": [
                    {"id": "profile", "label": "Assign PK: id", "value": "id"},
                    {"id": "documentation", "label": "Assign PK: number", "value": "number"},
                ],
            },
        }
    )
    save_semantic_model_draft(seeded_settings, draft, username="admin@test.com")

    resolve_question(
        seeded_settings,
        "conflict_pk_customers",
        username="admin@test.com",
        choice="documentation",
    )
    draft = load_semantic_model_draft(seeded_settings)
    customer = next(e for e in draft["entities"] if e.get("silver_entity") == "customers")
    assert customer.get("primary_key") == "number"
    assert customer.get("primary_key_status") == "approved"
    resolved = next(q for q in draft["questions"] if q.get("id") == "conflict_pk_customers")
    assert resolved.get("status") == "resolved"


def test_approve_proposed_keys(seeded_settings: DnaSettings) -> None:
    _seed_minimal_silver(seeded_settings)
    run_semantic_init(seeded_settings, username="admin@test.com", enable_llm_tagging=False)

    draft = load_semantic_model_draft(seeded_settings)
    assert any(
        str(entity.get("primary_key_status") or "") == "proposed"
        for entity in draft.get("entities") or []
        if isinstance(entity, dict)
    )

    result = approve_proposed_keys(seeded_settings, username="admin@test.com")
    assert result["primary_keys_approved"] >= 1

    seeded_entities = {
        "customers",
        "items",
        "sales_invoices",
        "sales_invoice_lines",
        "sales_orders",
        "sales_order_lines",
        "sales_shipment_lines",
    }
    draft = load_semantic_model_draft(seeded_settings)
    for entity in draft.get("entities") or []:
        if not isinstance(entity, dict) or not str(entity.get("primary_key") or "").strip():
            continue
        silver = str(entity.get("silver_entity") or "")
        if silver in seeded_entities:
            assert str(entity.get("primary_key_status") or "") == "approved"
        else:
            assert str(entity.get("primary_key_status") or "") == "proposed"
    for attribute in draft.get("attributes") or []:
        if not isinstance(attribute, dict):
            continue
        if str(attribute.get("role") or "") != "foreign_key":
            continue
        assert str(attribute.get("status") or "") == "approved"


def test_resolve_column_tag_question_applies_concepts(seeded_settings: DnaSettings) -> None:
    _seed_minimal_silver(seeded_settings)
    run_semantic_init(seeded_settings, username="admin@test.com", enable_llm_tagging=False)

    resolve_question(
        seeded_settings,
        "q_revenue_date",
        username="admin@test.com",
        choice="posting_date",
    )
    draft = load_semantic_model_draft(seeded_settings)
    tagged = next(
        a
        for a in draft.get("attributes") or []
        if a.get("entity") == "sales_invoice_lines" and a.get("column") == "postingDate"
    )
    assert tagged.get("concepts") == ["posting_date"]
    assert tagged.get("status") == "approved"
    resolved = next(q for q in draft["questions"] if q.get("id") == "q_revenue_date")
    assert resolved.get("status") == "resolved"


def test_merge_preserved_questions_keeps_resolved(seeded_settings: DnaSettings) -> None:
    _seed_minimal_silver(seeded_settings)
    run_semantic_init(seeded_settings, username="admin@test.com", enable_llm_tagging=False)
    resolve_question(
        seeded_settings,
        "q_revenue_date",
        username="admin@test.com",
        choice="posting_date",
    )

    proposed = [
        {
            "id": "q_revenue_date",
            "text": "Should revenue period attribution use posting date or document date?",
            "status": "open",
        },
        {
            "id": "conflict_pk_customers",
            "text": "Primary key conflict",
            "status": "open",
        },
    ]
    existing = load_semantic_model_draft(seeded_settings).get("questions") or []
    merged = merge_preserved_questions(proposed, existing)
    revenue = next(q for q in merged if q.get("id") == "q_revenue_date")
    assert revenue.get("status") == "resolved"
    assert next(q for q in merged if q.get("id") == "conflict_pk_customers").get("status") == "open"
