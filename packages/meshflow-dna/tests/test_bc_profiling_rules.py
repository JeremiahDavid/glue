"""Tests for Microsoft Learn BC profiling rules."""

from __future__ import annotations

from meshflow.dna.bc_profiling_rules import (
    load_profiling_rules,
    merge_profiling_rules_into_hints,
    parse_ms_learn_entity_page,
    slug_to_silver_entity,
)
from meshflow.dna.semantic_knowledge_base import load_connector_standard_hints


SAMPLE_MARKDOWN = """
# salesInvoiceLine resource type - Business Central | Microsoft Learn

Represents a sales invoice line in Business Central.

## Navigation

| Navigation | Return Type | Description |
| --- | --- | --- |
| [salesInvoice](dynamics_salesinvoice) | salesInvoice | Gets the salesinvoice of the salesInvoiceLine. |
| [item](dynamics_item) | item | Gets the item of the salesInvoiceLine. |

## Properties

| Property | Type | Description |
| --- | --- | --- |
| id | GUID | The unique ID of the sales invoice line. Non-editable. |
| documentId | GUID | The ID of the parent sales invoice line. |
| itemId | GUID | The ID of the item in the sales invoice line. |
| quantity | decimal | The quantity of the item in the sales invoice line. |
| unitPrice | decimal | Specifies the price for one unit of the item. |
| netAmount | decimal | The net amount is the amount including all discounts. |
"""


def test_slug_to_silver_entity_maps_bc_resources() -> None:
    assert slug_to_silver_entity("dynamics_customer") == "customers"
    assert slug_to_silver_entity("dynamics_salesinvoiceline") == "sales_invoice_lines"
    assert slug_to_silver_entity("dynamics_generalledgerentry") == "general_ledger_entries"


def test_parse_ms_learn_entity_page_extracts_keys_and_hints() -> None:
    parsed = parse_ms_learn_entity_page(SAMPLE_MARKDOWN, slug="dynamics_salesinvoiceline")
    assert parsed["silver_entity"] == "sales_invoice_lines"
    assert parsed["primary_key"] == "id"
    assert parsed["role"] == "fact"
    fk_columns = {item["column"] for item in parsed["foreign_keys"]}
    assert {"documentId", "itemId"}.issubset(fk_columns)
    assert parsed["column_hints"]["quantity"]["role"] == "measure"
    assert parsed["column_hints"]["itemId"]["role"] == "foreign_key"


def test_generated_profiling_rules_file_loads() -> None:
    rules = load_profiling_rules("dbc")
    assert rules.get("source") == "dbc"
    assert int(rules.get("entity_count") or 0) >= 70
    entities = {item["silver_entity"] for item in rules.get("entities") or []}
    assert "customers" in entities
    assert "sales_invoice_lines" in entities
    assert len(rules.get("relationships") or []) >= 50
    assert len(rules.get("entities") or []) >= 70
    entity_hints = rules.get("entity_column_hints") or {}
    if entity_hints:
        assert len(entity_hints) >= 50
    else:
        # Legacy generated file may still expose global column_hints until rescraped.
        assert len(rules.get("column_hints") or {}) >= 100


def test_connector_hints_merge_profiling_rules() -> None:
    hints = load_connector_standard_hints("dbc")
    entities = {item["silver_entity"] for item in hints.get("entities") or []}
    assert "vendors" in entities
    assert "purchase_orders" in entities
    assert hints.get("profiling_rules", {}).get("entity_count", 0) >= 70
    invoice_line = next(item for item in hints["entities"] if item["silver_entity"] == "sales_invoice_lines")
    assert invoice_line.get("role") == "fact"
    assert any(fk.get("column") == "documentId" for fk in invoice_line.get("foreign_keys") or [])


def test_manual_hints_override_scraped_entity_description() -> None:
    connector = {
        "entities": [{"silver_entity": "customers", "description": "Hand-tuned customer master"}],
        "relationships": [],
    }
    profiling = {
        "entities": [
            {
                "silver_entity": "customers",
                "description": "Scraped description",
                "role": "dimension",
                "primary_key": "id",
            }
        ],
        "relationships": [],
        "entity_column_hints": {
            "customers": {"customerId": {"role": "foreign_key", "concepts": ["customer_id"]}},
        },
    }
    merged = merge_profiling_rules_into_hints(connector, profiling)
    customer = next(item for item in merged["entities"] if item["silver_entity"] == "customers")
    assert customer["description"] == "Hand-tuned customer master"
    assert merged["entity_column_hints"]["customers"]["customerId"]["role"] == "foreign_key"
