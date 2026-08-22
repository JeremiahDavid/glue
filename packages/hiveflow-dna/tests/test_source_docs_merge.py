"""Tests for BC source-docs overlay merge and schema validation."""

from __future__ import annotations

import pytest
from jsonschema import ValidationError

from hiveflow.dna.source_docs.merge import (
    merge_entity_list_catalog,
    merge_entity_relationships,
    merge_source_docs_artifact,
    normalize_source_docs_tables_payload,
)
from hiveflow.dna.source_docs.schema import list_schema_filenames, validate_source_docs_payload


def _properties_catalog() -> dict:
    return {
        "source": "dbc",
        "kind": "ms_learn_entity_properties",
        "tables": [
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
            "tables": ["items"],
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
            "tables": ["items"],
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
            "tables": [
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
    names = {e["silver_entity"] for e in gold["tables"]}
    assert names == {"sales_orders", "custom_entity"}
    sales = next(e for e in gold["tables"] if e["silver_entity"] == "sales_orders")
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
    assert gold["table_count"] == 2
    assert gold["kind"] == "ms_learn_entity_properties"
    assert "tables" in gold


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


def _tags_catalog() -> dict:
    return {
        "source": "dbc",
        "kind": "ms_learn_entity_property_tags",
        "tables": [
            {
                "silver_entity": "sales_orders",
                "properties": [
                    {"name": "status", "tags": ["order status", "document status"]},
                    {"name": "number", "tags": ["document number"]},
                ],
            }
        ],
    }


def test_validate_tags_overlay_per_tag_exclude() -> None:
    overlay = {
        "source": "dbc",
        "kind": "ms_learn_entity_property_tags_overlay",
        "exclude": {
            "tags": [
                {
                    "silver_entity": "sales_orders",
                    "name": "status",
                    "tags": ["order status"],
                }
            ]
        },
    }
    validate_source_docs_payload(overlay, artifact="entity_property_tags", variant="overlay")


def test_merge_tags_per_tag_exclude() -> None:
    overlay = {
        "source": "dbc",
        "kind": "ms_learn_entity_property_tags_overlay",
        "exclude": {
            "tags": [
                {
                    "silver_entity": "sales_orders",
                    "name": "status",
                    "tags": ["order status"],
                }
            ]
        },
    }
    gold = merge_source_docs_artifact(
        artifact="entity_property_tags",
        global_catalog=_tags_catalog(),
        overlay=overlay,
    )
    sales = next(e for e in gold["tables"] if e["silver_entity"] == "sales_orders")
    by_name = {p["name"]: p for p in sales["properties"]}
    assert by_name["status"]["tags"] == ["document status"]
    assert by_name["number"]["tags"] == ["document number"]
    assert gold["tagged_property_count"] == 2


def test_merge_tags_per_tag_exclude_drops_empty_property() -> None:
    overlay = {
        "source": "dbc",
        "kind": "ms_learn_entity_property_tags_overlay",
        "exclude": {
            "tags": [
                {
                    "silver_entity": "sales_orders",
                    "name": "number",
                    "tags": ["document number"],
                }
            ]
        },
    }
    gold = merge_source_docs_artifact(
        artifact="entity_property_tags",
        global_catalog=_tags_catalog(),
        overlay=overlay,
    )
    sales = next(e for e in gold["tables"] if e["silver_entity"] == "sales_orders")
    names = {p["name"] for p in sales["properties"]}
    assert "number" not in names
    assert "status" in names
    assert gold["tagged_property_count"] == 1


def test_normalize_legacy_entities_to_tables() -> None:
    legacy = {
        "source": "dbc",
        "kind": "ms_learn_entity_property_tags",
        "entity_count": 1,
        "entities": [
            {
                "silver_entity": "sales_orders",
                "properties": [{"name": "status", "tags": ["order status"]}],
            }
        ],
    }
    normalized = normalize_source_docs_tables_payload(legacy)
    assert "entities" not in normalized
    assert "entity_count" not in normalized
    assert normalized["table_count"] == 1
    assert normalized["tables"][0]["silver_entity"] == "sales_orders"

    gold = merge_source_docs_artifact(
        artifact="entity_property_tags",
        global_catalog=legacy,
        overlay=None,
    )
    assert "entities" not in gold
    assert "entity_count" not in gold
    assert gold["table_count"] == 1
    assert gold["tables"][0]["properties"][0]["tags"] == ["order status"]
