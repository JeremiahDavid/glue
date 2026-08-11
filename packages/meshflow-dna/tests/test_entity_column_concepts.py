"""Tests for entity-scoped column tag resolution."""

from __future__ import annotations

from pathlib import Path

import pytest

from meshflow.dna.field_semantics import (
    entity_column_concept_id,
    entity_column_concept_label,
    resolve_entity_column_concepts,
)
from meshflow.dna.init_client import init_client_governance
from meshflow.dna.semantic_structure import build_attributes_for_entities
from meshflow.dna.settings import DnaSettings


@pytest.fixture
def seeded_settings(tmp_path: Path) -> DnaSettings:
    settings = DnaSettings(source="dbc", data_dir=tmp_path, company="POC")
    init_client_governance(settings, company="POC")
    return settings


def test_display_name_maps_to_entity_specific_catalog_concepts() -> None:
    assert resolve_entity_column_concepts("customers", "displayName") == ["customer_name"]
    assert resolve_entity_column_concepts("items", "displayName") == ["item_name"]
    assert resolve_entity_column_concepts("vendors", "displayName") == ["vendor_name"]


def test_display_name_on_other_entities_uses_entity_scoped_id() -> None:
    assert resolve_entity_column_concepts("job_queue_entries", "displayName") == [
        "job_queue_entries_display_name"
    ]


def test_number_maps_to_entity_specific_catalog_concepts() -> None:
    assert resolve_entity_column_concepts("customers", "number") == ["customer_number"]
    assert resolve_entity_column_concepts("items", "number") == ["item_number"]


def test_purchase_invoice_fields_use_entity_scoped_concepts() -> None:
    assert resolve_entity_column_concepts("purchase_invoices", "invoiceDate") == [
        "purchase_invoices_invoice_date"
    ]
    assert resolve_entity_column_concepts("purchase_invoices", "number") == [
        "purchase_invoices_number"
    ]
    assert resolve_entity_column_concepts("purchase_invoices", "orderNumber") == [
        "purchase_invoices_order_number"
    ]
    assert resolve_entity_column_concepts("purchase_invoices", "status") == ["purchase_invoices_status"]


def test_purchase_invoice_order_number_label() -> None:
    assert entity_column_concept_label("purchase_invoices", "orderNumber") == "Purchase Order Number"


def test_line_amount_uses_entity_scoped_concept() -> None:
    concept_id = entity_column_concept_id("purchase_credit_memo_lines", "NetAmount")
    assert concept_id == "purchase_credit_memo_lines_net_amount"
    assert resolve_entity_column_concepts("purchase_credit_memo_lines", "NetAmount") == [concept_id]


def test_global_hint_concepts_are_ignored() -> None:
    hint = {"concepts": ["customer_name"], "role": "dimension"}
    assert resolve_entity_column_concepts("items", "displayName", hint=hint) == ["item_name"]
    status_hint = {"concepts": ["document_status"], "role": "status"}
    assert resolve_entity_column_concepts("purchase_invoices", "status", hint=status_hint) == [
        "purchase_invoices_status"
    ]
    date_hint = {"concepts": ["posting_date"], "role": "date"}
    assert resolve_entity_column_concepts("purchase_invoices", "invoiceDate", hint=date_hint) == [
        "purchase_invoices_invoice_date"
    ]


def test_entity_column_labels() -> None:
    assert entity_column_concept_label("items", "displayName") == "Item Name"
    assert entity_column_concept_label("purchase_credit_memo_lines", "NetAmount") == (
        "Purchase Credit Memo Net Amount"
    )


def test_build_attributes_for_entities_assigns_entity_scoped_tags(seeded_settings) -> None:
    from meshflow.ingest.storage import write_parquet_local
    from meshflow.storage.paths import prefix_path, silver_entity_prefix

    for entity, rows in {
        "customers": [{"id": "c1", "number": "C001", "displayName": "Acme"}],
        "items": [{"id": "i1", "number": "ITEM1", "displayName": "Widget"}],
    }.items():
        out_dir = prefix_path(seeded_settings.data_dir, silver_entity_prefix(seeded_settings.source, entity))
        write_parquet_local(out_dir, "data.parquet", rows)

    attributes = build_attributes_for_entities(
        seeded_settings,
        entity_names={"customers", "items"},
        existing_pairs=set(),
        source="dbc",
    )
    by_pair = {(a["entity"], a["column"]): a for a in attributes}
    assert by_pair[("customers", "displayName")]["concepts"] == ["customer_name"]
    assert by_pair[("items", "displayName")]["concepts"] == ["item_name"]
    assert by_pair[("customers", "number")]["concepts"] == ["customer_number"]
    assert by_pair[("items", "number")]["concepts"] == ["item_number"]


def test_build_attributes_for_entities_uses_per_entity_column_hints_for_roles(seeded_settings) -> None:
    from meshflow.ingest.storage import write_parquet_local
    from meshflow.storage.paths import prefix_path, silver_entity_prefix

    for entity, rows in {
        "sales_invoice_lines": [{"id": "l1", "status": "Open"}],
        "purchase_invoice_lines": [{"id": "l2", "status": "Posted"}],
    }.items():
        out_dir = prefix_path(seeded_settings.data_dir, silver_entity_prefix(seeded_settings.source, entity))
        write_parquet_local(out_dir, "data.parquet", rows)

    attributes = build_attributes_for_entities(
        seeded_settings,
        entity_names={"sales_invoice_lines", "purchase_invoice_lines"},
        entity_column_hints={
            "sales_invoice_lines": {
                "status": {"role": "status"},
            }
        },
        existing_pairs=set(),
        source="dbc",
    )
    by_pair = {(a["entity"], a["column"]): a for a in attributes}
    assert by_pair[("sales_invoice_lines", "status")]["concepts"] == ["sales_invoice_lines_status"]
    assert by_pair[("sales_invoice_lines", "status")]["role"] == "status"
    assert by_pair[("purchase_invoice_lines", "status")]["concepts"] == ["purchase_invoice_lines_status"]
