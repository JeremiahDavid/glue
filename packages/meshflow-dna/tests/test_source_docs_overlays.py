"""Tests for source-docs overlay mutate, pending diff, and version snapshots."""

from __future__ import annotations

from pathlib import Path

from meshflow.dna.init_client import init_client_governance
from meshflow.dna.settings import DnaSettings
from meshflow.dna.source_docs_overlays import (
    apply_exclude,
    commit_version,
    list_pending_excludes,
    list_versions,
    load_overlay,
    restore_version,
    undo_exclude,
)
from meshflow.dna.store import write_yaml_artifact
from meshflow.storage.paths import governance_source_docs_gold_key


def _settings(tmp_path: Path) -> DnaSettings:
    settings = DnaSettings(source="dbc", data_dir=tmp_path, company="POC")
    init_client_governance(settings, company="POC")
    return settings


def _seed_gold(settings: DnaSettings, *, generated_at: str = "2026-08-11T00:00:00Z") -> None:
    write_yaml_artifact(
        settings,
        governance_source_docs_gold_key("dbc", "entity_properties.yaml"),
        {
            "source": "dbc",
            "kind": "ms_learn_entity_properties",
            "generated_at": generated_at,
            "table_count": 1,
            "property_count": 1,
            "tables": [
                {
                    "silver_entity": "sales_orders",
                    "properties": [{"name": "status", "type": "string", "description": "Status"}],
                }
            ],
        },
    )
    write_yaml_artifact(
        settings,
        governance_source_docs_gold_key("dbc", "entity_relationships.yaml"),
        {
            "source": "dbc",
            "kind": "ms_learn_entity_relationships",
            "generated_at": generated_at,
            "table_count": 1,
            "relationship_count": 1,
            "tables": {
                "sales_orders": {
                    "PK": "id",
                    "relationships": [
                        {"target": "customers", "PK": "id", "FK": "customerId"},
                    ],
                }
            },
        },
    )
    write_yaml_artifact(
        settings,
        governance_source_docs_gold_key("dbc", "entity_property_tags.yaml"),
        {
            "source": "dbc",
            "kind": "ms_learn_entity_property_tags",
            "generated_at": generated_at,
            "table_count": 1,
            "property_count": 1,
            "tagged_property_count": 1,
            "tables": [
                {
                    "silver_entity": "sales_orders",
                    "properties": [{"name": "status", "tags": ["order status", "document status"]}],
                }
            ],
        },
    )


def test_apply_and_undo_table_exclude(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    result = apply_exclude(settings, kind="table", table="sales_orders")
    assert result["changed"] is True
    assert result["pending_count"] == 1
    assert result["pending"][0]["kind"] == "table"

    for artifact in (
        "entity_properties",
        "entity_relationships",
        "entity_property_tags",
    ):
        overlay = load_overlay(settings, artifact)
        assert overlay is not None
        assert "sales_orders" in overlay["exclude"]["tables"]

    undo = undo_exclude(settings, kind="table", table="sales_orders")
    assert undo["changed"] is True
    assert undo["pending_count"] == 0


def test_apply_relationship_and_tag_excludes(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    apply_exclude(
        settings,
        kind="relationship",
        table="sales_orders",
        fk="customerId",
        target="customers",
    )
    apply_exclude(
        settings,
        kind="tag",
        silver_entity="sales_orders",
        name="status",
        tags=["order status"],
    )
    pending = list_pending_excludes(settings)
    kinds = {p["kind"] for p in pending}
    assert kinds == {"relationship", "tag"}
    assert len(pending) == 2


def test_pending_clears_after_commit(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    _seed_gold(settings)
    apply_exclude(settings, kind="table", table="sales_orders")
    assert list_pending_excludes(settings)
    committed = commit_version(settings, note="first submit")
    assert committed["version"] == 1
    assert list_pending_excludes(settings) == []
    versions = list_versions(settings)
    assert versions["active_version"] == 1
    assert versions["pending_count"] == 0


def test_restore_rewrites_overlays_and_gold(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    _seed_gold(settings, generated_at="2026-08-11T00:00:00Z")
    apply_exclude(settings, kind="table", table="sales_orders")
    commit_version(settings, note="v1")

    # Second edit + gold bump, then commit v2.
    undo_exclude(settings, kind="table", table="sales_orders")
    apply_exclude(
        settings,
        kind="tag",
        silver_entity="sales_orders",
        name="status",
        tags=["order status"],
    )
    _seed_gold(settings, generated_at="2026-08-12T00:00:00Z")
    commit_version(settings, note="v2")

    restored = restore_version(settings, version=1)
    assert restored["version"] == 3
    assert restored["entry"]["restored_from"] == 1

    props = load_overlay(settings, "entity_properties")
    assert props is not None
    assert "sales_orders" in (props.get("exclude") or {}).get("tables", [])

    from meshflow.dna.source_docs_reference import load_source_docs_gold_artifact

    gold_props = load_source_docs_gold_artifact(settings, "entity_properties")
    assert gold_props is not None
    assert gold_props["generated_at"] == "2026-08-11T00:00:00Z"

    # After restore commit, pending should be empty (live matches active snapshot).
    assert list_pending_excludes(settings) == []
