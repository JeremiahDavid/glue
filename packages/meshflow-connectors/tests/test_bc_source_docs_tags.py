"""Tests for BC entity_properties → property tags derivation."""

from __future__ import annotations

import json

from meshflow.bc.source_docs_tags import (
    build_entity_property_tags,
    entity_properties_prompt_yaml,
    tag_entity_properties,
)


def test_entity_properties_prompt_yaml_includes_descriptions() -> None:
    yaml_text = entity_properties_prompt_yaml(
        {
            "silver_entity": "sales_orders",
            "description": "A sales order object in Dynamics 365 Business Central.",
            "properties": [
                {
                    "name": "status",
                    "type": "string",
                    "description": "Specifies the status of the sales order.",
                }
            ],
        }
    )
    assert "silver_entity: sales_orders" in yaml_text
    assert "name: status" in yaml_text
    assert "Specifies the status of the sales order." in yaml_text


def test_tag_entity_properties_uses_requested_prompt() -> None:
    captured: dict[str, str] = {}

    def fake_invoke(system: str, user_message: str) -> str:
        captured["system"] = system
        captured["user"] = user_message
        return json.dumps(
            {
                "properties": [
                    {"name": "status", "tags": ["order status"]},
                    {
                        "name": "billToCustomerNumber",
                        "tags": ["bill to customer", "customer account number"],
                    },
                ]
            }
        )

    tags = tag_entity_properties(
        {
            "silver_entity": "sales_orders",
            "description": "A sales order.",
            "properties": [
                {"name": "status", "type": "string", "description": "Order status."},
                {
                    "name": "billToCustomerNumber",
                    "type": "string",
                    "description": "Bill-to customer number.",
                },
            ],
        },
        invoke_fn=fake_invoke,
    )
    assert tags["status"] == ["order status"]
    assert tags["billToCustomerNumber"] == ["bill to customer", "customer account number"]
    assert "Generate tags for each property" in captured["system"]
    assert "5 words or less" in captured["system"]
    assert "entity_properties:" in captured["user"]
    assert "billToCustomerNumber" in captured["user"]


def test_build_entity_property_tags_shape() -> None:
    catalog = {
        "source": "dbc",
        "tables": [
            {
                "silver_entity": "sales_orders",
                "bc_resource_slug": "salesorder",
                "description": "A sales order object.",
                "ms_learn_url": "https://example.test/salesorder",
                "properties": [
                    {"name": "status", "type": "string", "description": "Status of the order."},
                    {
                        "name": "billToCustomerNumber",
                        "type": "string",
                        "description": "Bill-to customer.",
                    },
                ],
            }
        ],
    }

    def fake_invoke(_system: str, _user: str) -> str:
        return json.dumps(
            {
                "properties": [
                    {"name": "status", "tags": ["order status"]},
                    {"name": "billToCustomerNumber", "tags": ["bill to customer"]},
                ]
            }
        )

    payload = build_entity_property_tags(
        catalog,
        invoke_fn=fake_invoke,
        sourced_from="s3://hiveflowai-source-documentation/dbc/entity_properties.yaml",
    )
    assert payload["kind"] == "ms_learn_entity_property_tags"
    assert payload["table_count"] == 1
    assert payload["tagged_property_count"] == 2
    entity = payload["tables"][0]
    assert entity["silver_entity"] == "sales_orders"
    assert entity["properties"] == [
        {"name": "status", "tags": ["order status"]},
        {"name": "billToCustomerNumber", "tags": ["bill to customer"]},
    ]
    assert "type" not in entity["properties"][0]
    assert "description" not in entity["properties"][0]
