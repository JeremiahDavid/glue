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
    assert "Proposals" in html
    assert "semantic-builder-keys-tabs" in html
    assert 'id="spreadsheet-table-chat"' not in html


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


def test_proposal_review_renders_table_chat(tmp_path: Path, portal_env: None) -> None:
    from meshflow.spreadsheet.jobs import create_job, save_job

    job = create_job(filename="sample.xlsx", username="poc")
    job = save_job({**job, "status": "ready"})
    table = {
        "table_id": "t0",
        "entity_name": "customers",
        "purpose": "Customer master",
        "grain": "one row per customer",
        "confidence": 0.9,
        "status": "pending_review",
        "schema": [{"name": "customer_id", "type": "string", "description": "id", "is_key": True}],
        "profiling": {"columns": []},
        "source": {"sheet": "Customers", "row_count": 2},
        "chat_history": [{"role": "user", "text": "rename id column", "at": "now"}],
    }
    from meshflow.dna.web.portal.spreadsheet_engine.render import render_spreadsheet_engine_page

    html = render_spreadsheet_engine_page(
        url=lambda path: path,
        sources=["sse", "dbc"],
        active_source="sse",
        availability={"sse": True, "dbc": False},
        is_admin=True,
        job=job,
        report={"tables": [table]},
        active_tab="review",
    )
    assert "customers" in html
    assert 'id="spreadsheet-table-chat"' in html
    assert "rename id column" in html
    assert "Approve table" in html
