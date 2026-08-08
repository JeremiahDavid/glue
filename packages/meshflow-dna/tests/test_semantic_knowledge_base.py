"""Tests for connector knowledge bases and silver-backed structure proposal."""

from __future__ import annotations

from pathlib import Path

import pytest

from meshflow.dna.init_client import init_client_governance
from meshflow.dna.semantic_init import run_semantic_init
from meshflow.dna.semantic_knowledge_base import (
    load_connector_manifest,
    load_merged_semantic_hints,
    merge_semantic_hints,
)
from meshflow.dna.semantic_model import ensure_semantic_model_seed, load_semantic_model_draft
from meshflow.dna.semantic_structure import propose_semantic_structure
from meshflow.dna.settings import DnaSettings
from meshflow.dna.store import write_yaml_artifact
from meshflow.ingest.storage import write_parquet_local
from meshflow.storage.paths import governance_semantic_overrides_key, prefix_path, silver_entity_prefix


@pytest.fixture
def seeded_settings(tmp_path: Path) -> DnaSettings:
    settings = DnaSettings(source="dbc", data_dir=tmp_path, company="POC")
    init_client_governance(settings, company="POC")
    ensure_semantic_model_seed(settings)
    return settings


def test_connector_manifest_loads_for_dbc() -> None:
    manifest = load_connector_manifest("dbc")
    assert manifest["source"] == "dbc"
    assert "docs/dbc-data-model.md" in list(manifest.get("documentation") or [])


def test_tenant_overrides_merge_with_connector_hints(seeded_settings: DnaSettings) -> None:
    connector = {
        "entities": [
            {"silver_entity": "customers", "role": "dimension", "description": "Standard"},
        ],
        "relationships": [],
        "column_hints": {"customerId": {"concepts": ["customer_id"]}},
    }
    tenant = {
        "entities": [
            {"silver_entity": "customers", "description": "Client-specific naming"},
            {"silver_entity": "custom_metrics", "role": "fact"},
        ],
        "column_hints": {"backlogAmount": {"concepts": ["backlog_amount"]}},
    }
    merged = merge_semantic_hints(connector, tenant)
    customer = next(item for item in merged["entities"] if item["silver_entity"] == "customers")
    assert customer["role"] == "dimension"
    assert customer["description"] == "Client-specific naming"
    assert any(item["silver_entity"] == "custom_metrics" for item in merged["entities"])
    assert merged["column_hints"]["customerId"]["concepts"] == ["customer_id"]
    assert merged["column_hints"]["backlogAmount"]["concepts"] == ["backlog_amount"]


def test_propose_semantic_structure_includes_all_silver_tables(seeded_settings: DnaSettings) -> None:
    for entity in ("customers", "vendors", "purchase_orders"):
        out_dir = prefix_path(
            seeded_settings.data_dir,
            silver_entity_prefix(seeded_settings.source, entity),
        )
        write_parquet_local(out_dir, "data.parquet", [{"id": f"{entity}-1"}])

    hints = load_merged_semantic_hints(seeded_settings)
    structure = propose_semantic_structure(seeded_settings, hints)
    silver_entities = {item["silver_entity"] for item in structure["entities"]}
    assert {"customers", "vendors", "purchase_orders"}.issubset(silver_entities)


def test_init_uses_tenant_override_entity_role(seeded_settings: DnaSettings) -> None:
    out_dir = prefix_path(
        seeded_settings.data_dir,
        silver_entity_prefix(seeded_settings.source, "vendors"),
    )
    write_parquet_local(out_dir, "data.parquet", [{"id": "v1", "displayName": "Supplier"}])

    key = governance_semantic_overrides_key(seeded_settings.dna_config_id)
    write_yaml_artifact(
        seeded_settings,
        key,
        {
            "entities": [
                {
                    "silver_entity": "vendors",
                    "role": "dimension",
                    "description": "Preferred vendor master for this client",
                }
            ]
        },
    )

    result = run_semantic_init(seeded_settings, username="tester", enable_llm_tagging=False)
    assert result["status"] == "initialized"
    draft = load_semantic_model_draft(seeded_settings)
    vendor = next(item for item in draft["entities"] if item["silver_entity"] == "vendors")
    assert vendor["role"] == "dimension"
    assert "client" in vendor["description"].lower()
