"""Tests for BC entity_properties → property tags derivation."""

from __future__ import annotations

import json

from hiveflow.dna.source_docs.tags import (
    build_entity_property_tags,
    enrich_property_tags,
    entity_properties_prompt_yaml,
    field_specific_tag,
    split_camel_case,
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


def test_split_camel_case_and_field_specific_tag() -> None:
    assert split_camel_case("sellToCountry") == ["sell", "To", "Country"]
    assert split_camel_case("sellToPostCode") == ["sell", "To", "Post", "Code"]
    assert split_camel_case("VATBusinessPostingGroup") == [
        "VAT",
        "Business",
        "Posting",
        "Group",
    ]
    assert field_specific_tag("sellToCountry") == "sell to country"
    assert field_specific_tag("sellToPostCode") == "sell to postal code"
    assert field_specific_tag("billToCustomerNumber") == "bill to customer number"
    assert field_specific_tag("documentId") == "document id"


def test_enrich_property_tags_adds_specific_and_fk() -> None:
    tags = enrich_property_tags(
        "sellToCountry",
        ["sell to address", "company location"],
    )
    assert tags[0] == "sell to country"
    assert "sell to address" in tags
    assert "company location" in tags

    fk_tags = enrich_property_tags(
        "itemId",
        ["item reference"],
        is_foreign_key=True,
    )
    assert fk_tags[:2] == ["item id", "foreign key"]
    assert "item reference" in fk_tags


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
    assert "field-specific tag" in captured["system"]
    assert "foreign key" in captured["system"]
    assert "5 words or less" in captured["system"]
    assert "entity_properties:" in captured["user"]
    assert "billToCustomerNumber" in captured["user"]


def test_build_entity_property_tags_shape() -> None:
    catalog = {
        "source": "dbc",
        "tables": [
            {
                "silver_entity": "sales_invoices",
                "bc_resource_slug": "salesinvoice",
                "description": "A sales invoice object.",
                "ms_learn_url": "https://example.test/salesinvoice",
                "properties": [
                    {"name": "status", "type": "string", "description": "Status of the invoice."},
                    {
                        "name": "sellToCountry",
                        "type": "string",
                        "description": "Sell-to country.",
                    },
                    {
                        "name": "sellToPostCode",
                        "type": "string",
                        "description": "Sell-to postal code.",
                    },
                    {
                        "name": "customerId",
                        "type": "guid",
                        "description": "The ID of the customer.",
                    },
                ],
            }
        ],
    }

    def fake_invoke(_system: str, _user: str) -> str:
        return json.dumps(
            {
                "properties": [
                    {"name": "status", "tags": ["invoice status"]},
                    {
                        "name": "sellToCountry",
                        "tags": ["sell to address", "company location"],
                    },
                    {
                        "name": "sellToPostCode",
                        "tags": ["sell to address", "company location"],
                    },
                    {"name": "customerId", "tags": ["customer reference"]},
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
    assert payload["tagged_property_count"] == 4
    entity = payload["tables"][0]
    assert entity["silver_entity"] == "sales_invoices"
    by_name = {row["name"]: row["tags"] for row in entity["properties"]}
    assert by_name["status"][0] == "status"
    assert "invoice status" in by_name["status"]
    assert by_name["sellToCountry"][0] == "sell to country"
    assert "sell to address" in by_name["sellToCountry"]
    assert by_name["sellToPostCode"][0] == "sell to postal code"
    assert "company location" in by_name["sellToPostCode"]
    assert by_name["customerId"][:2] == ["customer id", "foreign key"]
    assert "customer reference" in by_name["customerId"]
    assert "type" not in entity["properties"][0]
    assert "description" not in entity["properties"][0]
