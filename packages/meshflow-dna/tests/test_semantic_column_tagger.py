"""Tests for LLM column tagging helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from meshflow.dna.init_client import init_client_governance
from meshflow.dna.semantic_column_tagger import (
    apply_entity_scoped_tags_to_attributes,
    apply_llm_tags_to_attributes,
    humanize_column_tag,
    suggest_column_tags,
)
from meshflow.dna.semantic_model import ensure_semantic_model_seed
from meshflow.dna.settings import DnaSettings
from meshflow.ingest.storage import write_parquet_local
from meshflow.storage.paths import prefix_path, silver_entity_prefix


@pytest.fixture
def seeded_settings(tmp_path: Path) -> DnaSettings:
    settings = DnaSettings(source="dbc", data_dir=tmp_path, company="POC")
    init_client_governance(settings, company="POC")
    ensure_semantic_model_seed(settings)
    return settings


def test_humanize_column_tag_parses_label_response(seeded_settings: DnaSettings) -> None:
    def mock_invoke(_system: str, _user: str) -> str:
        return (
            '{"label": "Customer Name", "notes": "Display name for the customer", '
            '"role": "dimension"}'
        )

    suggestion = humanize_column_tag(
        seeded_settings,
        entity="customers",
        column="displayName",
        concept_id="customer_name",
        profile={
            "entity": "customers",
            "column": "displayName",
            "inferred_dtype": "string",
            "null_rate": 0.0,
            "distinct_count": 10,
            "sample_values": ["Acme", "Beta"],
        },
        invoke_fn=mock_invoke,
    )
    assert suggestion.concepts == ["customer_name"]
    assert suggestion.label == "Customer Name"
    assert "customer" in suggestion.notes.lower()


def test_humanize_column_tag_humanizes_purchase_order_number(seeded_settings: DnaSettings) -> None:
    def mock_invoke(_system: str, _user: str) -> str:
        return (
            '{"label": "Purchase Order Number", '
            '"notes": "Reference to the related purchase order on this purchase invoice", '
            '"role": "identifier"}'
        )

    suggestion = humanize_column_tag(
        seeded_settings,
        entity="purchase_invoices",
        column="orderNumber",
        concept_id="purchase_invoices_order_number",
        profile={
            "entity": "purchase_invoices",
            "column": "orderNumber",
            "inferred_dtype": "string",
            "null_rate": 0.0,
            "distinct_count": 3,
            "sample_values": ["PO-1", "PO-2"],
        },
        invoke_fn=mock_invoke,
        entity_context="Posted purchase invoice headers",
    )
    assert suggestion.concepts == ["purchase_invoices_order_number"]
    assert suggestion.label == "Purchase Order Number"


def test_suggest_column_tags_assigns_id_and_humanizes_label(seeded_settings: DnaSettings) -> None:
    def mock_invoke(_system: str, _user: str) -> str:
        return (
            '{"label": "Invoice Line Status", "notes": "Posted invoice line status", '
            '"role": "status"}'
        )

    suggestion = suggest_column_tags(
        seeded_settings,
        entity="sales_invoice_lines",
        profile={
            "entity": "sales_invoice_lines",
            "column": "status",
            "inferred_dtype": "string",
            "null_rate": 0.0,
            "distinct_count": 3,
            "sample_values": ["Open", "Posted"],
        },
        invoke_fn=mock_invoke,
        entity_context="Posted sales invoice lines",
    )
    assert suggestion.concepts == ["sales_invoice_lines_status"]
    assert suggestion.label == "Invoice Line Status"


def test_apply_entity_scoped_tags_replaces_stale_generic_concepts() -> None:
    attributes = [
        {
            "entity": "purchase_invoices",
            "column": "orderNumber",
            "status": "proposed",
            "concepts": ["document_number"],
        }
    ]
    tagged = apply_entity_scoped_tags_to_attributes(attributes, entity_names={"purchase_invoices"})
    assert tagged == 1
    assert attributes[0]["concepts"] == ["purchase_invoices_order_number"]


def test_apply_llm_tags_uses_deterministic_tags_when_llm_disabled(
    seeded_settings: DnaSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MESHFLOW_SEMANTIC_LLM_TAGGING", "0")

    attributes = [
        {
            "entity": "purchase_invoices",
            "column": "invoiceDate",
            "status": "proposed",
            "concepts": ["posting_date"],
        }
    ]
    result = apply_llm_tags_to_attributes(
        seeded_settings,
        attributes,
        entity_names={"purchase_invoices"},
    )
    assert result["reason"] == "llm_disabled"
    assert result["tagged_count"] == 1
    assert attributes[0]["concepts"] == ["purchase_invoices_invoice_date"]
    assert result["concept_labels"]["purchase_invoices_invoice_date"]


def test_apply_llm_tags_humanizes_every_tagged_column(
    seeded_settings: DnaSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MESHFLOW_SEMANTIC_LLM_TAGGING", "1")
    monkeypatch.setenv("MESHFLOW_SEMANTIC_LLM_TAG_LIMIT", "5")

    out_dir = prefix_path(
        seeded_settings.data_dir,
        silver_entity_prefix(seeded_settings.source, "purchase_invoices"),
    )
    write_parquet_local(
        out_dir,
        "data.parquet",
        [{"id": "1", "orderNumber": "PO-1"}],
    )

    def mock_invoke(_system: str, _user: str) -> str:
        return (
            '{"label": "Purchase Order Number", '
            '"notes": "Reference to the related purchase order on this purchase invoice", '
            '"role": "identifier"}'
        )

    attributes = [
        {"entity": "purchase_invoices", "column": "orderNumber", "status": "proposed"},
    ]
    result = apply_llm_tags_to_attributes(
        seeded_settings,
        attributes,
        entity_names={"purchase_invoices"},
        invoke_fn=mock_invoke,
    )
    assert result["tagged_count"] == 1
    assert result["humanized_count"] == 1
    assert attributes[0]["concepts"] == ["purchase_invoices_order_number"]
    assert attributes[0]["tagged_by"] == "llm"
    assert result["concept_labels"]["purchase_invoices_order_number"] == "Purchase Order Number"
