"""Integration test for LLM tag generation save path."""

from __future__ import annotations

from pathlib import Path

import pytest

from meshflow.dna.init_client import init_client_governance
from meshflow.dna.semantic_column_tagger import _entity_context_by_name, apply_llm_tags_to_attributes
from meshflow.dna.semantic_init import enrich_semantic_model_llm_tags, run_semantic_init
from meshflow.dna.semantic_model import ensure_semantic_model_seed, load_semantic_model_draft, save_semantic_model_draft
from meshflow.dna.settings import DnaSettings
from meshflow.dna.web.portal.semantics.init_service import run_portal_rerun_tag_generation
from meshflow.ingest.storage import write_parquet_local
from meshflow.storage.paths import prefix_path, silver_entity_prefix


@pytest.fixture
def seeded_settings(tmp_path: Path) -> DnaSettings:
    settings = DnaSettings(source="dbc", data_dir=tmp_path, company="POC")
    init_client_governance(settings, company="POC")
    ensure_semantic_model_seed(settings)
    out = prefix_path(settings.data_dir, silver_entity_prefix(settings.source, "purchase_invoices"))
    write_parquet_local(
        out,
        "data.parquet",
        [
            {
                "id": "1",
                "number": "PI-1",
                "orderNumber": "PO-9",
                "invoiceDate": "2026-01-01",
                "status": "Open",
            }
        ],
    )
    run_semantic_init(settings, username="test", enable_llm_tagging=False)
    return settings


def test_enrich_semantic_model_llm_tags_saves_entity_scoped_tags(seeded_settings: DnaSettings) -> None:
    def mock_invoke(_system: str, _user: str) -> str:
        return (
            '{"label": "Purchase Order Number", '
            '"notes": "Reference to the related purchase order on this purchase invoice", '
            '"role": "identifier"}'
        )

    draft = load_semantic_model_draft(seeded_settings)
    for attribute in draft.get("attributes") or []:
        if isinstance(attribute, dict) and attribute.get("entity") == "purchase_invoices":
            attribute.pop("concepts", None)
            attribute.pop("tagged_by", None)
            attribute.pop("citation", None)

    entities = {
        str(entity.get("silver_entity") or "").strip().lower()
        for entity in draft.get("entities") or []
        if isinstance(entity, dict) and str(entity.get("silver_entity") or "").strip()
    }
    concept_labels: dict[str, str] = {}
    apply_llm_tags_to_attributes(
        seeded_settings,
        list(draft.get("attributes") or []),
        entity_names=entities,
        invoke_fn=mock_invoke,
        entity_context_by_name=_entity_context_by_name(draft.get("entities")),
        concept_labels=concept_labels,
    )
    draft["concept_labels"] = concept_labels
    save_semantic_model_draft(seeded_settings, draft, username="test")

    result = enrich_semantic_model_llm_tags(seeded_settings, username="test")
    assert result["status"] == "enriched"
    saved = load_semantic_model_draft(seeded_settings)
    tagged = next(
        a
        for a in saved.get("attributes") or []
        if a.get("entity") == "purchase_invoices" and a.get("column") == "orderNumber"
    )
    assert tagged.get("concepts") == ["purchase_invoices_order_number"]
    assert saved.get("concept_labels", {}).get("purchase_invoices_order_number") == "Purchase Order Number"


def test_portal_rerun_tag_generation_sync(seeded_settings: DnaSettings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "meshflow.dna.web.portal.semantics.init_service._on_lambda",
        lambda: False,
    )

    draft = load_semantic_model_draft(seeded_settings)
    for attribute in draft.get("attributes") or []:
        if isinstance(attribute, dict) and attribute.get("entity") == "purchase_invoices":
            attribute["concepts"] = ["document_status"]
    save_semantic_model_draft(seeded_settings, draft, username="test")

    result = run_portal_rerun_tag_generation(
        seeded_settings,
        username="admin@test.com",
        company="POC",
    )
    assert result.get("status") == "enriched"
    assert result.get("workflow", {}).get("tagging_status") == "completed"
    saved = load_semantic_model_draft(seeded_settings)
    status_attr = next(
        a
        for a in saved.get("attributes") or []
        if a.get("entity") == "purchase_invoices" and a.get("column") == "status"
    )
    assert status_attr.get("concepts") == ["purchase_invoices_status"]
