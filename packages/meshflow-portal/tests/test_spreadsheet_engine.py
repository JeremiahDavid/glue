"""Portal tests for Spreadsheet Engine Source Browser UI."""

from __future__ import annotations

from pathlib import Path

import pytest
from werkzeug.test import Client

from meshflow.dna.init_client import init_client_governance
from meshflow.dna.settings import DnaSettings
from meshflow.dna.web.app import create_app
from meshflow.project_config import load_project_config


@pytest.fixture
def portal_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HIVEFLOW_PORTAL_USERNAME", "poc")
    monkeypatch.setenv("HIVEFLOW_PORTAL_PASSWORD", "changeme")
    monkeypatch.setenv("HIVEFLOW_PORTAL_CLIENT_ID", "poc")


def _client(tmp_path: Path) -> Client:
    settings = DnaSettings(source="dbc", data_dir=tmp_path, company="POC")
    init_client_governance(settings, company="POC")
    config = load_project_config()
    try:
        from meshflow.project_config import get_platform_environment_config

        env_config = get_platform_environment_config("dev")
    except KeyError:
        env_config = config["companies"]["poc"]["environments"]["dev"]
    return Client(
        create_app(
            settings,
            company="POC",
            environment="dev",
            env_config=env_config,
            ui_mode="reporting",
        )
    )


def test_source_browser_lists_spreadsheet_engine_first(tmp_path: Path, portal_env: None) -> None:
    client = _client(tmp_path)
    client.post("/portal/login", data={"username": "poc", "password": "changeme"})
    response = client.get("/portal/semantics/source-docs")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Spreadsheet Engine" in html
    assert html.index("Spreadsheet Engine") < html.index("Business Central")


def test_spreadsheet_engine_route_renders_upload(tmp_path: Path, portal_env: None) -> None:
    client = _client(tmp_path)
    client.post("/portal/login", data={"username": "poc", "password": "changeme"})
    response = client.get("/portal/semantics/source-docs/sse")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Upload workbook" in html
    assert "Refine proposals" in html
    assert "semantic-builder-keys-tabs" in html
    assert "assistant-compose" in html


def test_state_machine_arn_uses_sts_account(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MESHFLOW_SPREADSHEET_STATE_MACHINE_ARN", raising=False)
    monkeypatch.setenv("AWS_REGION", "us-east-2")

    class _Sts:
        def get_caller_identity(self):
            return {"Account": "123456789012"}

    class _Boto3:
        def client(self, name: str):
            assert name == "sts"
            return _Sts()

    monkeypatch.setitem(__import__("sys").modules, "boto3", _Boto3())

    from meshflow.dna.web.portal.spreadsheet_engine.service import _state_machine_arn

    arn = _state_machine_arn(company="POC", environment="dev")
    assert arn == "arn:aws:states:us-east-2:123456789012:stateMachine:poc-dev-spreadsheet"
