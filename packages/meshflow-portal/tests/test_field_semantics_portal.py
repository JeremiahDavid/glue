"""Tests for field semantics portal API and Config Assistant integration."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from werkzeug.test import Client

from meshflow.dna.field_semantics import publish_field_semantics, save_field_semantics_draft
from meshflow.dna.init_client import init_client_governance
from meshflow.dna.settings import DnaSettings
from meshflow.dna.web.app import create_app
from meshflow.dna.web.portal.config_assistant.bedrock_chat import run_tool, system_prompt
from meshflow.dna.web.portal.semantics.api import concepts_payload, draft_payload, entities_payload
from meshflow.project_config import load_project_config


@pytest.fixture
def portal_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HIVEFLOW_PORTAL_USERNAME", "poc")
    monkeypatch.setenv("HIVEFLOW_PORTAL_PASSWORD", "changeme")
    monkeypatch.setenv("HIVEFLOW_PORTAL_CLIENT_ID", "poc")


@pytest.fixture
def seeded_settings(tmp_path: Path) -> DnaSettings:
    settings = DnaSettings(source="dbc", data_dir=tmp_path, company="POC")
    init_client_governance(settings, company="POC")
    return settings


def _client(tmp_path: Path) -> Client:
    settings = DnaSettings(source="dbc", data_dir=tmp_path, company="POC")
    init_client_governance(settings, company="POC")
    config = load_project_config()
    try:
        from meshflow.project_config import get_platform_environment_config

        env_config = get_platform_environment_config("dev")
    except KeyError:
        env_config = config["companies"]["POC"]["environments"]["dev"]
    return Client(create_app(settings, company="POC", environment="dev", env_config=env_config))


def test_concepts_payload(seeded_settings: DnaSettings) -> None:
    payload = concepts_payload(seeded_settings)
    assert payload["categories"]
    assert payload["concepts"]
    assert payload["custom_concepts"] == []


def test_entities_payload(seeded_settings: DnaSettings) -> None:
    payload = entities_payload(seeded_settings)
    assert payload["source"] == "dbc"
    assert payload["entities"]


def test_draft_payload(seeded_settings: DnaSettings) -> None:
    payload = draft_payload(seeded_settings)
    assert payload["draft"]["status"] == "draft"
    assert "assistant_context" in payload


def test_system_prompt_includes_field_semantics(seeded_settings: DnaSettings) -> None:
    prompt = system_prompt(
        seeded_settings,
        base_version="1.0.0",
        next_version="1.0.1",
    )
    assert "Published field semantics" in prompt


def test_run_tool_get_field_semantics(seeded_settings: DnaSettings) -> None:
    draft = draft_payload(seeded_settings)["draft"]
    draft["mappings"] = [
        {
            "silver_entity": "customers",
            "column": "id",
            "concepts": ["primary_key"],
        }
    ]
    save_field_semantics_draft(seeded_settings, draft, username="admin@test.com")
    publish_field_semantics(seeded_settings, username="admin@test.com")

    payload = json.loads(run_tool(seeded_settings, "get_field_semantics"))
    assert payload["published"] is True
    assert payload["mappings"][0]["column"] == "id"


def test_semantics_page_renders(tmp_path: Path, portal_env: None) -> None:
    client = _client(tmp_path)
    client.post("/portal/login", data={"username": "poc", "password": "changeme"})

    response = client.get("/portal/semantics", follow_redirects=False)
    assert response.status_code in {200, 302}
    if response.status_code == 302:
        follow = client.get(response.headers["Location"])
        assert follow.status_code == 200
        assert b"Field Semantics" in follow.data
    else:
        assert b"Field Semantics" in response.data
