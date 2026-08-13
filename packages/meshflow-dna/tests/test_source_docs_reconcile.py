"""Tests for reconciling gold source-docs with silver schema profiles."""

from __future__ import annotations

from meshflow.dna.source_docs.reconcile import (
    reconcile_entity_properties,
    reconcile_entity_relationships,
    reconcile_entity_property_tags,
    reconcile_gold_artifacts,
)


def _profile() -> dict:
    return {
        "kind": "silver_schema_profile",
        "source": "dbc",
        "generated_at": "2026-01-01T00:00:00Z",
        "tables": [
            {
                "silver_entity": "customers",
                "glue_table": "silver_dbc_customers",
                "columns": [
                    {"name": "id", "type": "string", "origin": "api"},
                    {"name": "displayName", "type": "string", "origin": "api"},
                ],
            },
            {
                "silver_entity": "sales_orders",
                "glue_table": "silver_dbc_sales_orders",
                "columns": [
                    {"name": "id", "type": "string", "origin": "api"},
                    {"name": "customerId", "type": "string", "origin": "api"},
                    {"name": "amount", "type": "double", "origin": "api"},
                ],
            },
            {
                "silver_entity": "sales_invoice_lines",
                "glue_table": "silver_dbc_sales_invoice_lines",
                "columns": [
                    {"name": "id", "type": "string", "origin": "api"},
                    {"name": "header_id", "type": "string", "origin": "unpack"},
                ],
            },
        ],
    }


def test_reconcile_entity_properties_maps_odata_annotation_to_silver_column() -> None:
    profile = {
        "kind": "silver_schema_profile",
        "source": "dbc",
        "tables": [
            {
                "silver_entity": "customers",
                "columns": [
                    {"name": "id", "type": "string", "origin": "api"},
                    {"name": "odata_etag", "type": "string", "origin": "api"},
                ],
            }
        ],
    }
    gold = {
        "source": "dbc",
        "kind": "ms_learn_entity_properties",
        "tables": [
            {
                "silver_entity": "customers",
                "properties": [
                    {"name": "@odata.etag", "type": "string", "description": "OData concurrency token"},
                ],
            }
        ],
    }
    reconciled = reconcile_entity_properties(gold, profile)
    props = {p["name"]: p for p in reconciled["tables"][0]["properties"]}
    assert props["@odata.etag"]["silver_column"] == "odata_etag"
    assert props["@odata.etag"]["in_silver"] is True
    assert len(reconciled["tables"][0]["properties"]) == 2


def test_reconcile_entity_properties_maps_and_adds_silver_only() -> None:
    gold = {
        "source": "dbc",
        "kind": "ms_learn_entity_properties",
        "tables": [
            {
                "silver_entity": "customers",
                "properties": [
                    {"name": "customerName", "type": "string", "description": "doc only"},
                    {"name": "displayName", "type": "string", "description": "shown name"},
                ],
            }
        ],
    }
    reconciled = reconcile_entity_properties(gold, _profile())
    table = reconciled["tables"][0]
    props = {p["name"]: p for p in table["properties"]}
    assert props["customerName"]["in_silver"] is False
    assert props["customerName"]["origin"] == "documentation_only"
    assert props["displayName"]["silver_column"] == "displayName"
    assert props["displayName"]["in_silver"] is True

    lines_gold = {
        "source": "dbc",
        "kind": "ms_learn_entity_properties",
        "tables": [
            {
                "silver_entity": "sales_invoice_lines",
                "properties": [{"name": "documentId", "type": "string"}],
            }
        ],
    }
    lines_reconciled = reconcile_entity_properties(lines_gold, _profile())
    line_props = {p["name"]: p for p in lines_reconciled["tables"][0]["properties"]}
    assert line_props["header_id"]["origin"] == "unpack"


def test_reconcile_entity_relationships_uses_silver_columns() -> None:
    properties = reconcile_entity_properties(
        {
            "source": "dbc",
            "kind": "ms_learn_entity_properties",
            "tables": [
                {
                    "silver_entity": "sales_orders",
                    "properties": [{"name": "customerId", "type": "string"}],
                },
                {
                    "silver_entity": "customers",
                    "properties": [{"name": "id", "type": "string"}],
                },
            ],
        },
        _profile(),
    )
    relationships = {
        "source": "dbc",
        "kind": "ms_learn_entity_relationships",
        "tables": {
            "sales_orders": {
                "PK": "id",
                "relationships": [
                    {"target": "customers", "FK": "customerId", "PK": "id"},
                ],
            }
        },
    }
    from meshflow.dna.source_docs.reconcile import build_properties_silver_index

    reconciled = reconcile_entity_relationships(
        relationships,
        _profile(),
        properties_index=build_properties_silver_index(properties),
    )
    table = reconciled["tables"]["sales_orders"]
    rel = table["relationships"][0]
    assert rel["silver_FK"] == "customerId"
    assert rel["silver_PK"] == "id"
    assert rel["fk_in_silver"] is True
    assert rel["pk_in_silver"] is True


def test_reconcile_gold_artifacts_all_three() -> None:
    artifacts = {
        "entity_properties": {
            "source": "dbc",
            "kind": "ms_learn_entity_properties",
            "tables": [
                {
                    "silver_entity": "customers",
                    "properties": [{"name": "displayName", "type": "string"}],
                }
            ],
        },
        "entity_relationships": {
            "source": "dbc",
            "kind": "ms_learn_entity_relationships",
            "tables": {
                "sales_orders": {
                    "PK": "id",
                    "relationships": [
                        {"target": "customers", "FK": "customerId", "PK": "id"},
                    ],
                }
            },
        },
        "entity_property_tags": {
            "source": "dbc",
            "kind": "ms_learn_entity_property_tags",
            "tables": [
                {
                    "silver_entity": "customers",
                    "properties": [{"name": "displayName", "tags": ["name"]}],
                }
            ],
        },
    }
    reconciled = reconcile_gold_artifacts(artifacts, _profile())
    assert reconciled["entity_properties"]["tables"][0]["properties"][0]["in_silver"] is True
    assert reconciled["entity_relationships"]["tables"]["sales_orders"]["relationships"][0]["silver_FK"]
    tag_prop = reconciled["entity_property_tags"]["tables"][0]["properties"][0]
    assert tag_prop["silver_column"] == "displayName"
