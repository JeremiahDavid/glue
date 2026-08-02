from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from werkzeug.test import Client

from meshflow.dna.settings import DnaSettings
from meshflow.dna.web.app import REVENUE_TABLE_LIMIT, create_app
from meshflow.project_config import get_environment_config, load_project_config


@pytest.fixture
def portal_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HIVEFLOW_PORTAL_USERNAME", "poc")
    monkeypatch.setenv("HIVEFLOW_PORTAL_PASSWORD", "changeme")
    monkeypatch.setenv("HIVEFLOW_PORTAL_CLIENT_ID", "poc")


def _client(tmp_path: Path) -> Client:
    settings = DnaSettings(source="dbc", data_dir=tmp_path, pack_id="bc_intra_v1")
    config = load_project_config()
    env_config = config["companies"]["POC"]["environments"]["dev"]
    return Client(create_app(settings, company="POC", environment="dev", env_config=env_config))


def test_public_landing_and_pricing(tmp_path: Path) -> None:
    client = _client(tmp_path)

    home = client.get("/")
    assert home.status_code == 200
    assert b"Hive Flow" in home.data
    assert b"Reveal what matters" in home.data

    pricing = client.get("/pricing")
    assert pricing.status_code == 200
    assert b"$100" in pricing.data
    assert b"$5,000" in pricing.data


def test_portal_requires_login(tmp_path: Path, portal_env: None) -> None:
    client = _client(tmp_path)
    response = client.get("/portal")
    assert response.status_code == 302
    assert "/portal/login" in response.headers["Location"]


def test_portal_login_and_overview(tmp_path: Path, portal_env: None) -> None:
    client = _client(tmp_path)
    login = client.post(
        "/portal/login",
        data={"username": "poc", "password": "changeme", "next": "/portal"},
    )
    assert login.status_code == 302
    assert login.headers["Location"].endswith("/portal")

    overview = client.get("/portal")
    assert overview.status_code == 200
    assert b"POC Distribution Co." in overview.data
    assert b"Executive snapshot" in overview.data


def test_portal_semantics_after_login(tmp_path: Path, portal_env: None) -> None:
    client = _client(tmp_path)
    client.post("/portal/login", data={"username": "poc", "password": "changeme"})

    semantics = client.get("/portal/semantics")
    assert semantics.status_code == 200
    assert b"bc_intra_v1" in semantics.data


def test_api_gateway_stage_prefix(tmp_path: Path, portal_env: None) -> None:
    client = _client(tmp_path)

    response = client.get("/", environ_overrides={"SCRIPT_NAME": "/prod"})
    assert response.status_code == 200
    assert b'href="/prod/pricing"' in response.data
    assert b'src="/prod/static/hiveflowai-symbol.png"' in response.data

    client.post(
        "/portal/login",
        data={"username": "poc", "password": "changeme"},
        environ_overrides={"SCRIPT_NAME": "/prod"},
    )
    executive = client.get("/portal/executive", environ_overrides={"SCRIPT_NAME": "/prod"})
    assert executive.status_code == 200
    assert b'href="/prod/portal/revenue"' in executive.data


def test_web_app_api_endpoints_require_auth(tmp_path: Path) -> None:
    client = _client(tmp_path)
    pack = client.get("/api/pack")
    assert pack.status_code == 401


def test_web_app_api_endpoints(tmp_path: Path, portal_env: None) -> None:
    client = _client(tmp_path)
    client.post("/portal/login", data={"username": "poc", "password": "changeme"})

    pack = client.get("/api/pack")
    assert pack.status_code == 200
    assert pack.json["pack_id"] == "bc_intra_v1"

    revenue = client.get("/api/revenue")
    assert revenue.status_code == 200
    assert revenue.json["output_id"] == "out_fact_revenue_lines"
    assert revenue.json["row_count"] == 0
    assert len(revenue.json["rows"]) <= REVENUE_TABLE_LIMIT


def test_client_portal_config_from_yaml() -> None:
    env_config = get_environment_config("POC", "dev")
    from meshflow.dna.web.portal.config import load_client_portal_config

    client = load_client_portal_config("poc", env_config, default_pack_id="bc_intra_v1")
    assert client.display_name == "POC Distribution Co."
    assert client.pack_id == "bc_intra_v1"
