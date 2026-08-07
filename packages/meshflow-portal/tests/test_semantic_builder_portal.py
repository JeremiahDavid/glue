"""Tests for Semantic Builder portal routes and API."""

from __future__ import annotations

from pathlib import Path

import pytest
from werkzeug.test import Client

from meshflow.dna.init_client import init_client_governance
from meshflow.dna.semantic_model import ensure_semantic_model_seed
from meshflow.dna.settings import DnaSettings
from meshflow.dna.web.app import create_app
from meshflow.dna.web.portal.semantics.model_api import builder_payload
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
    ensure_semantic_model_seed(settings)
    return settings


def _client(tmp_path: Path) -> Client:
    settings = DnaSettings(source="dbc", data_dir=tmp_path, company="POC")
    init_client_governance(settings, company="POC")
    ensure_semantic_model_seed(settings)
    config = load_project_config()
    try:
        from meshflow.project_config import get_platform_environment_config

        env_config = get_platform_environment_config("dev")
    except KeyError:
        env_config = config["companies"]["POC"]["environments"]["dev"]
    return Client(create_app(settings, company="POC", environment="dev", env_config=env_config))


def test_builder_payload(seeded_settings: DnaSettings) -> None:
    payload = builder_payload(seeded_settings)
    assert payload["draft"]["status"] == "draft"
    assert "coverage" in payload
    assert "readiness" in payload
    assert payload["workflow"]["init_completed"] is False


def test_semantic_builder_page_renders(tmp_path: Path, portal_env: None) -> None:
    client = _client(tmp_path)
    client.post("/portal/login", data={"username": "poc", "password": "changeme"})
    response = client.get("/portal/semantics/builder")
    assert response.status_code == 200
    assert b"Semantic Builder" in response.data
    assert b"Initialize from source docs" in response.data


def test_semantic_model_api_requires_auth(tmp_path: Path) -> None:
    client = _client(tmp_path)
    response = client.get("/api/semantic-model")
    assert response.status_code == 401
