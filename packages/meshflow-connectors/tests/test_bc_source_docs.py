"""Tests for Microsoft Learn BC source documentation scrape."""

from __future__ import annotations

from meshflow.bc.source_docs import (
    build_source_properties_catalog,
    extract_entity_properties_doc,
    slug_to_silver_entity,
    source_docs_object_key,
)

SAMPLE_MARKDOWN = """
# salesInvoiceLine resource type - Business Central | Microsoft Learn

Represents a sales invoice line in Business Central.

## Properties

| Property | Type | Description |
| --- | --- | --- |
| id | GUID | The unique ID of the sales invoice line. Non-editable. |
| documentId | GUID | The ID of the parent sales invoice. |
| itemId | GUID | The ID of the item in the sales invoice line. |
| quantity | decimal | The quantity of the item in the sales invoice line. |
| unitPrice | decimal | Specifies the price for one unit of the item. |
| netAmount | decimal | The net amount is the amount including all discounts. |
| lastModifiedDateTime | datetime | The last datetime the sales invoice line was modified. |
"""


def test_slug_to_silver_entity_maps_bc_resources() -> None:
    assert slug_to_silver_entity("dynamics_customer") == "customers"
    assert slug_to_silver_entity("dynamics_salesinvoiceline") == "sales_invoice_lines"


def test_extract_entity_properties_doc_keeps_full_properties_table() -> None:
    doc = extract_entity_properties_doc(SAMPLE_MARKDOWN, slug="dynamics_salesinvoiceline")
    assert doc["silver_entity"] == "sales_invoice_lines"
    assert doc["property_count"] == 7
    by_name = {row["name"]: row for row in doc["properties"]}
    assert by_name["quantity"]["type"] == "decimal"
    assert "quantity of the item" in by_name["quantity"]["description"]
    assert by_name["documentId"]["type"] == "GUID"
    assert "parent sales invoice" in by_name["documentId"]["description"]


def test_build_source_properties_catalog_shape() -> None:
    catalog = build_source_properties_catalog(
        {"dynamics_salesinvoiceline": SAMPLE_MARKDOWN},
        source="dbc",
        failures=[],
    )
    assert catalog["source"] == "dbc"
    assert catalog["kind"] == "ms_learn_entity_properties"
    assert catalog["entity_count"] == 1
    assert catalog["property_count"] == 7
    assert catalog["entities"][0]["silver_entity"] == "sales_invoice_lines"
    assert source_docs_object_key("dbc") == "dbc/entity_properties.yaml"
