"""Tests for BC source-docs overlay merge and schema validation."""

from __future__ import annotations

import pytest
from jsonschema import ValidationError

from meshflow.bc.source_docs_merge import (
    merge_entity_list_catalog,
    merge_entity_relationships,
    merge_source_docs_artifact,
)
from meshflow.bc.source_docs_schema import list_schema_filenames, validate_source_docs_payload


def _properties_catalog() -> dict:
    return {
        "source": "dbc",
        "kind": "ms_learn_entity_properties",
        "entities": [
            {
                "silver_entity": "sales_orders",
                "properties": [
                    {"name": "id", "type": "GUID", "description": "Unique ID"},
                    {"name": "odataEtag", "type": "string", "description": "ETag"},
                    {"name": "status", "type": "string", "description": "Status"},
                ],
            },
            {
                "silver_entity": "items",
                "properties": [
                    {"name": "id", "type": "GUID", "description": "Unique ID"},
                ],
            },
        ],
    }


def _relationships_catalog() -> dict:
    return {
        "source": "dbc",
        "kind": "ms_learn_entity_relationships",
        "tables": {
            "sales_invoice_lines": {
                "PK": "id",
                "relationships": [
                    {"target": "sales_invoices", "PK": "id", "FK": "documentId"},
                    {"target": "items", "PK": "id", "FK": "itemId"},
                ],
            },
            "items": {"PK": "id", "relationships": []},
        },
    }


def test_schema_files_are_packaged() -> None:
    names = list_schema_filenames()
    assert "entity_properties.schema.json" in names
    assert "entity_properties.overlay.schema.json" in names
    assert len(names) == 6


def test_validate_global_and_overlay_properties() -> None:
    validate_source_docs_payload(_properties_catalog(), artifact="entity_properties")
    overlay = {
        "source": "dbc",
        "kind": "ms_learn_entity_properties_overlay",
        "exclude": {
            "silver_entities": ["items"],
            "properties": [{"silver_entity": "sales_orders", "names": ["odataEtag"]}],
        },
        "addition": {
            "properties": [
                {
                    "silver_entity": "sales_orders",
                    "properties": [
                        {
                            "name": "customField",
                            "type": "string",
                            "description": "Client custom field",
                        }
                    ],
                }
            ]
        },
    }
    validate_source_docs_payload(overlay, artifact="entity_properties", variant="overlay")


def test_invalid_overlay_rejected() -> None:
    with pytest.raises(ValidationError):
        validate_source_docs_payload(
            {
                "source": "dbc",
                "kind": "ms_learn_entity_properties",  # wrong kind for overlay
                "exclude": {},
            },
            artifact="entity_properties",
            variant="overlay",
        )


def test_merge_properties_exclude_and_addition() -> None:
    overlay = {
        "source": "dbc",
        "kind": "ms_learn_entity_properties_overlay",
        "exclude": {
            "silver_entities": ["items"],
            "properties": [{"silver_entity": "sales_orders", "names": ["odataEtag"]}],
        },
        "addition": {
            "properties": [
                {
                    "silver_entity": "sales_orders",
                    "properties": [
                        {"name": "customField", "type": "string", "description": "Custom"}
                    ],
                }
            ],
            "entities": [
                {
                    "silver_entity": "custom_entity",
                    "properties": [{"name": "id", "type": "GUID", "description": "ID"}],
                }
            ],
        },
    }
    gold = merge_source_docs_artifact(
        artifact="entity_properties",
        global_catalog=_properties_catalog(),
        overlay=overlay,
    )
    assert gold["kind"] == "ms_learn_entity_properties"
    names = {e["silver_entity"] for e in gold["entities"]}
    assert names == {"sales_orders", "custom_entity"}
    sales = next(e for e in gold["entities"] if e["silver_entity"] == "sales_orders")
    prop_names = {p["name"] for p in sales["properties"]}
    assert prop_names == {"id", "status", "customField"}
    assert "odataEtag" not in prop_names


def test_merge_relationships() -> None:
    overlay = {
        "source": "dbc",
        "kind": "ms_learn_entity_relationships_overlay",
        "exclude": {
            "tables": ["items"],
            "relationships": [{"table": "sales_invoice_lines", "FK": "itemId"}],
        },
        "addition": {
            "relationships": [
                {
                    "table": "sales_invoice_lines",
                    "target": "locations",
                    "PK": "id",
                    "FK": "locationId",
                }
            ]
        },
    }
    gold = merge_source_docs_artifact(
        artifact="entity_relationships",
        global_catalog=_relationships_catalog(),
        overlay=overlay,
    )
    assert "items" not in gold["tables"]
    rels = gold["tables"]["sales_invoice_lines"]["relationships"]
    fks = {r["FK"] for r in rels}
    assert fks == {"documentId", "locationId"}


def test_merge_without_overlay_is_passthrough_shape() -> None:
    gold = merge_entity_list_catalog(
        _properties_catalog(),
        None,
        kind="ms_learn_entity_properties",
    )
    assert gold["entity_count"] == 2
    assert gold["kind"] == "ms_learn_entity_properties"


def test_merge_relationships_clear_all_for_table() -> None:
    gold = merge_entity_relationships(
        _relationships_catalog(),
        {
            "source": "dbc",
            "kind": "ms_learn_entity_relationships_overlay",
            "exclude": {"relationships": [{"table": "sales_invoice_lines"}]},
        },
    )
    assert gold["tables"]["sales_invoice_lines"]["relationships"] == []
