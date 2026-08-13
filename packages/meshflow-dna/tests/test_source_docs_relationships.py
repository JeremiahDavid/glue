"""Tests for BC entity_properties → relationships derivation."""

from __future__ import annotations

import json

from meshflow.bc.source_docs_relationships import (
    build_entity_relationships,
    classify_property_key_role,
    extract_table_keys,
    line_table_header_base,
    resolve_document_id_target,
    resolve_fk_targets,
)


def test_classify_property_key_role_unique_id_is_pk_only_for_id_field() -> None:
    assert (
        classify_property_key_role(
            "The unique ID of the sales invoice line.",
            field_name="id",
        )
        == "pk"
    )
    assert (
        classify_property_key_role(
            "Specifies the Unique ID for this record.",
            field_name="id",
        )
        == "pk"
    )
    assert (
        classify_property_key_role(
            "The unique ID of the journal template.",
            field_name="journalTemplateId",
        )
        == "fk"
    )


def test_classify_property_key_role_plain_id_is_fk_for_id_suffix_fields() -> None:
    assert (
        classify_property_key_role(
            "The ID of the parent sales invoice.",
            field_name="documentId",
        )
        == "fk"
    )
    assert (
        classify_property_key_role(
            "The ID of the item in the sales invoice line.",
            field_name="itemId",
        )
        == "fk"
    )
    assert (
        classify_property_key_role(
            "The ID of the parent sales invoice.",
            field_name="parentReference",
        )
        is None
    )


def test_classify_property_key_role_ignores_non_id_descriptions() -> None:
    assert (
        classify_property_key_role(
            "The quantity of the item in the sales invoice line.",
            field_name="quantity",
        )
        is None
    )


def test_extract_table_keys_treats_other_unique_id_fields_as_fks() -> None:
    entity = {
        "silver_entity": "general_journal_lines",
        "properties": [
            {"name": "id", "description": "The unique ID of the general journal line."},
            {
                "name": "journalTemplateId",
                "description": "The unique ID of the journal template.",
            },
            {
                "name": "journalBatchId",
                "description": "The unique ID of the journal batch.",
            },
            {"name": "accountId", "description": "The ID of the G/L account."},
        ],
    }
    keys = extract_table_keys(entity)
    assert keys["PK"] == "id"
    assert [row["field"] for row in keys["foreign_keys"]] == [
        "journalTemplateId",
        "journalBatchId",
        "accountId",
    ]


def test_extract_table_keys_from_properties() -> None:
    entity = {
        "silver_entity": "sales_invoice_lines",
        "properties": [
            {"name": "id", "description": "The unique ID of the sales invoice line."},
            {"name": "documentId", "description": "The ID of the parent sales invoice."},
            {"name": "itemId", "description": "The ID of the item in the sales invoice line."},
            {"name": "quantity", "description": "The quantity of the item."},
        ],
    }
    keys = extract_table_keys(entity)
    assert keys["PK"] == "id"
    assert [row["field"] for row in keys["foreign_keys"]] == ["documentId", "itemId"]


def test_resolve_fk_targets_uses_minimal_description_prompt() -> None:
    captured: dict[str, str] = {}

    def fake_invoke(system: str, user_message: str) -> str:
        captured["system"] = system
        captured["user"] = user_message
        return json.dumps({"targets": {"1": "sales_invoices", "2": "items"}})

    resolved = resolve_fk_targets(
        [
            {"description": "The ID of the parent sales invoice."},
            {"description": "The ID of the item in the sales invoice line."},
        ],
        allowed_tables=["sales_invoice_lines", "sales_invoices", "items"],
        invoke_fn=fake_invoke,
    )
    assert resolved == {1: "sales_invoices", 2: "items"}
    assert "Allowed tables:" in captured["user"]
    assert "1. The ID of the parent sales invoice." in captured["user"]
    assert "documentId" not in captured["user"]
    assert "sales_invoice_lines" in captured["user"]


def test_line_table_header_base_strips_line_suffix() -> None:
    assert line_table_header_base("sales_order_line") == "sales_order"
    assert line_table_header_base("sales_order_lines") == "sales_order"
    assert line_table_header_base("journal_lines") == "journal"
    assert line_table_header_base("sales_orders") == ""


def test_resolve_document_id_target_maps_to_header_table() -> None:
    allowed = ["sales_order_lines", "sales_orders", "items"]
    assert resolve_document_id_target("sales_order_lines", allowed_tables=allowed) == "sales_orders"
    assert resolve_document_id_target("sales_order_line", allowed_tables=allowed) == "sales_orders"


def test_build_entity_relationships_shape() -> None:
    catalog = {
        "source": "dbc",
        "tables": [
            {
                "silver_entity": "items",
                "properties": [
                    {"name": "id", "description": "The unique ID of the item."},
                    {"name": "number", "description": "The item number."},
                ],
            },
            {
                "silver_entity": "sales_invoices",
                "properties": [
                    {"name": "id", "description": "The unique ID of the sales invoice."},
                ],
            },
            {
                "silver_entity": "sales_invoice_lines",
                "properties": [
                    {"name": "id", "description": "The unique ID of the sales invoice line."},
                    {"name": "documentId", "description": "The ID of the parent sales invoice."},
                    {"name": "itemId", "description": "The ID of the item in the sales invoice line."},
                ],
            },
        ],
    }
    captured: dict[str, str] = {}

    def fake_invoke(_system: str, user_message: str) -> str:
        captured["user"] = user_message
        # documentId is resolved deterministically; only itemId goes to the model.
        return json.dumps({"targets": {"1": "items"}})

    payload = build_entity_relationships(
        catalog,
        invoke_fn=fake_invoke,
        sourced_from="s3://hiveflowai-source-documentation/dbc/entity_properties.yaml",
    )
    assert payload["kind"] == "ms_learn_entity_relationships"
    assert payload["sourced_from"].endswith("dbc/entity_properties.yaml")
    assert payload["relationship_count"] == 2
    lines = payload["tables"]["sales_invoice_lines"]
    assert lines["PK"] == "id"
    assert lines["relationships"] == [
        {"target": "sales_invoices", "PK": "id", "FK": "documentId"},
        {"target": "items", "PK": "id", "FK": "itemId"},
    ]
    assert payload["tables"]["items"]["relationships"] == []
    assert "parent sales invoice" not in captured["user"]
    assert "item in the sales invoice line" in captured["user"]
