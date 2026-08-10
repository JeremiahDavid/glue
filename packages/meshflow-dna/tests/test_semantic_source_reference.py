"""Tests for approved-build source reference profiles and consensus weighting."""

from __future__ import annotations

from pathlib import Path

import pytest

from meshflow.dna.init_client import init_client_governance
from meshflow.dna.semantic_init import run_semantic_init
from meshflow.dna.semantic_key_profiler import propose_keys_from_profiling
from meshflow.dna.semantic_model import ensure_semantic_model_seed, publish_semantic_model
from meshflow.dna.semantic_source_reference import (
    apply_reference_consensus_to_key_proposals,
    build_source_consensus,
    extract_reference_profile,
    load_source_semantic_consensus,
    record_approved_semantic_build,
)
from meshflow.dna.settings import DnaSettings
from meshflow.ingest.storage import write_parquet_local
from meshflow.storage.paths import prefix_path, silver_entity_prefix


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
        "sales_shipment_lines": [{"id": "sl1", "itemId": "i1", "quantity": 1}],
    }
    for entity, rows in entities.items():
        out_dir = prefix_path(settings.data_dir, silver_entity_prefix(settings.source, entity))
        write_parquet_local(out_dir, "data.parquet", rows)


def _approve_for_publish(settings: DnaSettings, username: str = "admin@test.com") -> None:
    from meshflow.dna.semantic_model import (
        build_relationships_from_approved_keys,
        load_semantic_model_draft,
        publish_semantic_model,
        resolve_question,
        save_semantic_model_draft,
    )

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
            resolve_question(
                settings,
                str(question["id"]),
                username=username,
                resolution="Use posting date per starter pack.",
                choice="posting_date",
            )
    draft = load_semantic_model_draft(settings)
    for rel in draft.get("relationships") or []:
        rel["status"] = "approved"
    for attribute in draft.get("attributes") or []:
        if attribute.get("concepts") and str(attribute.get("status") or "") == "proposed":
            attribute["status"] = "approved"
    save_semantic_model_draft(settings, draft, username=username)


@pytest.fixture
def seeded_settings(tmp_path: Path) -> DnaSettings:
    settings = DnaSettings(source="dbc", data_dir=tmp_path, company="POC")
    init_client_governance(settings, company="POC")
    ensure_semantic_model_seed(settings)
    return settings


def test_extract_reference_profile_from_published_model() -> None:
    model = {
        "source": "dbc",
        "entities": [
            {"silver_entity": "customers", "role": "dimension", "primary_key": "id", "status": "approved"},
        ],
        "attributes": [
            {
                "entity": "sales_invoice_lines",
                "column": "customerId",
                "role": "foreign_key",
                "fk_target_entity": "customers",
                "fk_target_column": "id",
                "status": "approved",
            },
            {
                "entity": "sales_invoice_lines",
                "column": "netAmount",
                "concepts": ["revenue_amount"],
                "role": "measure",
                "status": "approved",
            },
        ],
        "relationships": [
            {
                "from_entity": "sales_invoice_lines",
                "from_column": "customerId",
                "to_entity": "customers",
                "to_column": "id",
                "cardinality": "many_to_one",
                "status": "approved",
            }
        ],
    }
    profile = extract_reference_profile(model, pack_id="poc_dna_config", version="0.1.1", published_by="tester")
    assert profile["primary_keys"]["customers"] == "id"
    assert profile["foreign_keys"]["sales_invoice_lines"][0]["column"] == "customerId"
    assert profile["column_tags"][0]["concepts"] == ["revenue_amount"]


def test_consensus_weights_common_elements_higher() -> None:
    profiles = [
        extract_reference_profile(
            {
                "source": "dbc",
                "entities": [{"silver_entity": "customers", "primary_key": "id"}],
                "attributes": [],
                "relationships": [],
            },
            pack_id="a_dna_config",
            version="0.1.0",
            published_by="a",
        ),
        extract_reference_profile(
            {
                "source": "dbc",
                "entities": [{"silver_entity": "customers", "primary_key": "id"}],
                "attributes": [],
                "relationships": [],
            },
            pack_id="b_dna_config",
            version="0.1.0",
            published_by="b",
        ),
        extract_reference_profile(
            {
                "source": "dbc",
                "entities": [{"silver_entity": "customers", "primary_key": "number"}],
                "attributes": [],
                "relationships": [],
            },
            pack_id="c_dna_config",
            version="0.1.0",
            published_by="c",
        ),
    ]
    consensus = build_source_consensus(profiles)
    assert consensus["build_count"] == 3
    assert consensus["primary_keys"]["customers"]["column"] == "id"
    assert consensus["primary_keys"]["customers"]["ratio"] == pytest.approx(0.6667, rel=1e-3)
    assert consensus["primary_keys"]["customers"]["weight"] > 0.5


def test_publish_records_source_reference(seeded_settings: DnaSettings) -> None:
    _seed_minimal_silver(seeded_settings)
    run_semantic_init(seeded_settings, username="admin@test.com", enable_llm_tagging=False)
    _approve_for_publish(seeded_settings)
    published = publish_semantic_model(seeded_settings, username="admin@test.com")
    assert published.get("source_reference", {}).get("build_count") == 1
    consensus = load_source_semantic_consensus(seeded_settings)
    assert consensus is not None
    assert int(consensus.get("build_count") or 0) == 1


def test_profiling_uses_reference_consensus(seeded_settings: DnaSettings) -> None:
    entities = {
        "customers": [{"id": "c1", "number": "N1"}, {"id": "c2", "number": "N2"}],
        "sales_invoice_lines": [{"id": "l1", "customerId": "c1", "itemId": "i1"}],
        "items": [{"id": "i1", "number": "ITEM1"}],
    }
    for entity, rows in entities.items():
        out_dir = prefix_path(
            seeded_settings.data_dir,
            silver_entity_prefix(seeded_settings.source, entity),
        )
        write_parquet_local(out_dir, "data.parquet", rows)

    record_approved_semantic_build(
        seeded_settings,
        {
            "source": "dbc",
            "entities": [{"silver_entity": "customers", "primary_key": "id", "role": "dimension"}],
            "attributes": [
                {
                    "entity": "sales_invoice_lines",
                    "column": "customerId",
                    "role": "foreign_key",
                    "fk_target_entity": "customers",
                    "fk_target_column": "id",
                    "status": "approved",
                }
            ],
            "relationships": [],
        },
        pack_id="other_dna_config",
        version="1.0.0",
        username="other",
    )

    proposals = propose_keys_from_profiling(
        seeded_settings,
        list(entities),
        {"entities": [{"silver_entity": "customers", "primary_key": "number"}]},
    )
    assert proposals["primary_keys"]["customers"]["column"] == "id"
    assert "reference" in proposals["primary_keys"]["customers"].get("citation", "")


def test_apply_reference_boosts_fk_confidence() -> None:
    proposals = {
        "primary_keys": {},
        "foreign_keys": {"sales_invoice_lines": []},
        "conflicts": [],
    }
    consensus = {
        "build_count": 2,
        "primary_keys": {},
        "foreign_keys": {
            "sales_invoice_lines": [
                {
                    "column": "customerId",
                    "to_entity": "customers",
                    "to_column": "id",
                    "count": 2,
                    "ratio": 1.0,
                    "weight": 1.0,
                }
            ]
        },
    }
    merged = apply_reference_consensus_to_key_proposals(proposals, consensus, source="dbc")
    fk = merged["foreign_keys"]["sales_invoice_lines"][0]
    assert fk["column"] == "customerId"
    assert fk["confidence"] >= 0.9
