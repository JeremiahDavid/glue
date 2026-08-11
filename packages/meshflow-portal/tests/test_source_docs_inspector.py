"""Tests for Source Semantic Reference (gold source-docs) portal inspector."""

from __future__ import annotations

from pathlib import Path

import pytest
from werkzeug.test import Client

from meshflow.dna.init_client import init_client_governance
from meshflow.dna.settings import DnaSettings
from meshflow.dna.source_docs_reference import load_source_docs_gold
from meshflow.dna.store import write_yaml_artifact
from meshflow.dna.web.app import create_app
from meshflow.project_config import load_project_config
from meshflow.storage.paths import governance_source_docs_gold_key


@pytest.fixture
def portal_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HIVEFLOW_PORTAL_USERNAME", "poc")
    monkeypatch.setenv("HIVEFLOW_PORTAL_PASSWORD", "changeme")
    monkeypatch.setenv("HIVEFLOW_PORTAL_CLIENT_ID", "poc")


def _settings(tmp_path: Path) -> DnaSettings:
    settings = DnaSettings(source="dbc", data_dir=tmp_path, company="POC")
    init_client_governance(settings, company="POC")
    return settings


def _client(tmp_path: Path) -> Client:
    settings = _settings(tmp_path)
    config = load_project_config()
    try:
        from meshflow.project_config import get_platform_environment_config

        env_config = get_platform_environment_config("dev")
    except KeyError:
        env_config = config["companies"]["POC"]["environments"]["dev"]
    return Client(
        create_app(
            settings,
            company="POC",
            environment="dev",
            env_config=env_config,
            ui_mode="reporting",
        )
    )


def _seed_gold(settings: DnaSettings) -> None:
    write_yaml_artifact(
        settings,
        governance_source_docs_gold_key("dbc", "entity_properties.yaml"),
        {
            "source": "dbc",
            "kind": "ms_learn_entity_properties",
            "entity_count": 1,
            "property_count": 2,
            "generated_at": "2026-08-11T00:00:00Z",
            "entities": [
                {
                    "silver_entity": "sales_orders",
                    "bc_resource_slug": "salesorder",
                    "description": "A sales order.",
                    "properties": [
                        {"name": "id", "type": "GUID", "description": "Unique ID"},
                        {"name": "status", "type": "string", "description": "Order status"},
                    ],
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
            "entity_count": 1,
            "property_count": 2,
            "tagged_property_count": 1,
            "entities": [
                {
                    "silver_entity": "sales_orders",
                    "properties": [
                        {"name": "id", "tags": []},
                        {"name": "status", "tags": ["order status"]},
                    ],
                }
            ],
        },
    )


def test_load_source_docs_gold_empty(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    payload = load_source_docs_gold(settings)
    assert payload["available"] is False
    assert payload["complete"] is False


def test_load_source_docs_gold_populated(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    _seed_gold(settings)
    payload = load_source_docs_gold(settings)
    assert payload["available"] is True
    assert payload["complete"] is True
    assert payload["summary"]["entity_count"] == 1
    assert payload["summary"]["relationship_count"] == 1
    assert payload["summary"]["tagged_property_count"] == 1


def test_source_docs_inspector_empty_shows_build(tmp_path: Path, portal_env: None) -> None:
    client = _client(tmp_path)
    client.post("/portal/login", data={"username": "poc", "password": "changeme"})
    response = client.get("/portal/semantics/source-docs")
    assert response.status_code == 200
    assert b"Source Semantic Reference" in response.data
    assert b"Build Gold Reference" in response.data
    assert b"source-docs-build" in response.data
    assert b"No gold source documentation" in response.data
    assert b"semantic-builder-step-nav" not in response.data


def test_source_docs_inspector_populated(tmp_path: Path, portal_env: None) -> None:
    settings = _settings(tmp_path)
    _seed_gold(settings)
    config = load_project_config()
    try:
        from meshflow.project_config import get_platform_environment_config

        env_config = get_platform_environment_config("dev")
    except KeyError:
        env_config = config["companies"]["POC"]["environments"]["dev"]
    client = Client(
        create_app(
            settings,
            company="POC",
            environment="dev",
            env_config=env_config,
            ui_mode="reporting",
        )
    )
    client.post("/portal/login", data={"username": "poc", "password": "changeme"})
    response = client.get("/portal/semantics/source-docs")
    assert response.status_code == 200
    assert b"Rebuild Gold Reference" in response.data
    assert b"sales_orders" in response.data
    assert b"order status" in response.data
    assert b"customerId" in response.data
    assert b"data-source-docs-tab" in response.data


def test_source_docs_gold_api(tmp_path: Path, portal_env: None) -> None:
    settings = _settings(tmp_path)
    _seed_gold(settings)
    config = load_project_config()
    try:
        from meshflow.project_config import get_platform_environment_config

        env_config = get_platform_environment_config("dev")
    except KeyError:
        env_config = config["companies"]["POC"]["environments"]["dev"]
    client = Client(
        create_app(
            settings,
            company="POC",
            environment="dev",
            env_config=env_config,
            ui_mode="reporting",
        )
    )
    client.post("/portal/login", data={"username": "poc", "password": "changeme"})
    response = client.get("/api/source-docs-gold")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["available"] is True
    assert payload["summary"]["entity_count"] == 1
