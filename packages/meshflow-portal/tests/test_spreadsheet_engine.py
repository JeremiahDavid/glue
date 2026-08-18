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


def test_proposal_review_renders_table_preview() -> None:
    from meshflow.dna.web.portal.spreadsheet_engine.render import render_spreadsheet_engine_page

    job = {"job_id": "job1", "status": "ready", "filename": "sample.xlsx"}
    table = {
        "table_id": "t0",
        "entity_name": "customers",
        "purpose": "Customer master",
        "grain": "one row per customer",
        "confidence": 0.9,
        "status": "pending_review",
        "schema": [
            {"name": "customer_id", "type": "string", "description": "id", "is_key": True},
            {"name": "company", "type": "string", "description": "name"},
        ],
        "profiling": {
            "columns": [
                {
                    "name": "customer_id",
                    "inferred_type": "string",
                    "null_rate": 0,
                    "cardinality": 2,
                    "likely_key": True,
                    "patterns": [],
                },
                {
                    "name": "company",
                    "inferred_type": "string",
                    "null_rate": 0,
                    "cardinality": 2,
                    "likely_key": False,
                    "patterns": [],
                },
            ]
        },
        "source": {"sheet": "Customers", "row_count": 2},
    }
    preview = {
        "headers": ["customer_id", "company"],
        "rows": [["C1", "Acme"], ["C2", "Beta"]],
        "row_count": 2,
        "preview_row_count": 2,
        "truncated": False,
    }
    html = render_spreadsheet_engine_page(
        url=lambda path: path,
        sources=["sse"],
        active_source="sse",
        availability={"sse": True},
        is_admin=True,
        job=job,
        report={"tables": [table]},
        active_tab="review",
        table_preview=preview,
    )
    assert "Data preview" in html
    assert "Showing 2 of 2 data rows." in html
    assert "spreadsheet-schema-toggle" in html
    assert "Proposed schema" in html
    assert "Column profiling" in html
    assert "Acme" in html


def test_notes_section_renders_cleanly() -> None:
    from meshflow.dna.web.portal.spreadsheet_engine.render import _table_analysis_html

    html = _table_analysis_html(
        {
            "table_id": "t0",
            "entity_name": "customers",
            "purpose": "Customer master",
            "grain": "one row per customer",
            "confidence": 0.9,
            "status": "pending_review",
            "schema": [{"name": "customer_id", "type": "string", "description": "id"}],
            "profiling": {
                "columns": [
                    {
                        "name": "customer_id",
                        "inferred_type": "string",
                        "null_rate": 0,
                        "cardinality": 2,
                        "likely_key": True,
                        "patterns": [],
                    }
                ]
            },
            "notes": [
                "Heuristic fallback — Bedrock unavailable or returned invalid JSON.",
                "Rows alternate between item header and price detail.",
            ],
        },
        embedded=True,
    )
    assert "spreadsheet-notes" in html
    assert "Schema inferred locally" in html
    assert "Rows alternate between item header and price detail." in html
    assert "Heuristic fallback" not in html
    assert "spreadsheet-schema-toggle" in html


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
    assert 'role="tabpanel">' in html
    assert "spreadsheet-engine-panel-catalog" in html
    assert "Recent workbooks" not in html


def test_catalog_tab_lists_approved_proposals() -> None:
    from meshflow.dna.web.portal.spreadsheet_engine.render import render_spreadsheet_engine_page

    catalog_entry = {
        "catalog_id": "job1__t0",
        "job_id": "job1",
        "table_id": "t0",
        "filename": "sample.xlsx",
        "entity_name": "customers",
        "approved_at": "2026-01-01T00:00:00+00:00",
        "approved_by": "poc",
        "last_upload_at": "2026-02-01T00:00:00+00:00",
        "transformation": {"version": 1, "steps": [{"op": "rename_columns", "mapping": {"a": "b"}}]},
        "proposal": {
            "table_id": "t0",
            "entity_name": "customers",
            "purpose": "Customer master",
            "grain": "one row per customer",
            "confidence": 0.9,
            "status": "approved",
            "schema": [{"name": "customer_id", "type": "string", "description": "id", "is_key": True}],
            "profiling": {"columns": []},
            "source": {"sheet": "Customers", "row_count": 2},
        },
    }
    html = render_spreadsheet_engine_page(
        url=lambda path: path,
        sources=["sse"],
        active_source="sse",
        availability={"sse": True},
        is_admin=True,
        catalog_entries=[catalog_entry],
        active_catalog=catalog_entry,
        active_tab="catalog",
    )
    assert "Approved catalog" in html
    assert "customers" in html
    assert "Last upload" in html
    assert "spreadsheet-catalog-detail" in html
    assert "Customer master" in html
    assert "Re-upload workbook" in html
    assert "linked_catalog_id" in html


def test_upload_form_renders_catalog_link_dropdown() -> None:
    from meshflow.dna.web.portal.spreadsheet_engine.render import render_spreadsheet_engine_page

    catalog_entry = {
        "catalog_id": "sample__customers",
        "entity_name": "customers",
        "filename": "sample.xlsx",
    }
    html = render_spreadsheet_engine_page(
        url=lambda path: path,
        sources=["sse"],
        active_source="sse",
        availability={"sse": True},
        is_admin=True,
        catalog_entries=[catalog_entry],
        active_tab="analyze",
    )
    assert "linked_catalog_id" in html
    assert "sample__customers" in html


def test_transformation_panel_renders_in_proposal_review() -> None:
    from meshflow.dna.web.portal.spreadsheet_engine.render import render_spreadsheet_engine_page

    report = {
        "table_count": 1,
        "tables": [
            {
                "table_id": "t0",
                "entity_name": "customers",
                "purpose": "Customer master",
                "grain": "one row per customer",
                "confidence": 0.9,
                "status": "pending_review",
                "schema": [{"name": "customer_id", "type": "string"}],
                "profiling": {"columns": []},
                "transformation": {
                    "version": 1,
                    "steps": [{"op": "rename_columns", "mapping": {"Customer ID": "customer_id"}}],
                },
                "transformation_status": "pending_review",
            }
        ],
    }
    transform_preview = {
        "transformation_preview": {
            "before": {"headers": ["Customer ID"], "rows": [["C1"]], "row_count": 1, "preview_row_count": 1},
            "after": {"headers": ["customer_id"], "rows": [["C1"]], "row_count": 1, "preview_row_count": 1},
        }
    }
    html = render_spreadsheet_engine_page(
        url=lambda path: path,
        sources=["sse"],
        active_source="sse",
        availability={"sse": True},
        is_admin=True,
        job={"job_id": "job1", "status": "ready", "filename": "sample.xlsx"},
        report=report,
        request_job_id="job1",
        active_tab="review",
        transform_preview=transform_preview,
    )
    assert "spreadsheet-transform-panel" in html
    assert "Approve transformation" in html
    assert "Before (raw)" in html
    assert "After (transformed)" in html


def test_reload_validation_passed_renders_complete_button() -> None:
    from meshflow.dna.web.portal.spreadsheet_engine.render import render_spreadsheet_engine_page

    report = {
        "table_count": 1,
        "tables": [
            {
                "table_id": "t0",
                "entity_name": "customers",
                "purpose": "Customers",
                "reload_mode": True,
                "reload_validation_status": "passed",
                "linked_catalog_id": "sample__customers",
                "transformation": {"version": 1, "steps": []},
                "transformation_status": "approved",
                "schema": [{"name": "customer_id", "type": "string"}],
            }
        ],
    }
    html = render_spreadsheet_engine_page(
        url=lambda path: path,
        sources=["sse"],
        active_source="sse",
        availability={"sse": True},
        is_admin=True,
        job={"job_id": "job1", "status": "ready", "filename": "sample.xlsx", "reupload": True},
        report=report,
        request_job_id="job1",
        active_tab="review",
    )
    assert "Reload validation passed" in html
    assert "Complete reload" in html
    assert "No AI analysis was run" in html


def test_reload_validation_failed_renders_recovery_options() -> None:
    from meshflow.dna.web.portal.spreadsheet_engine.render import render_spreadsheet_engine_page

    report = {
        "table_count": 1,
        "tables": [
            {
                "table_id": "t0",
                "entity_name": "customers",
                "reload_mode": True,
                "reload_validation_status": "failed",
                "reload_validation_issues": ["Expected column 'company' missing from transformed output"],
                "linked_catalog_id": "sample__customers",
                "transformation": {"version": 1, "steps": []},
                "schema": [{"name": "customer_id", "type": "string"}],
            }
        ],
    }
    html = render_spreadsheet_engine_page(
        url=lambda path: path,
        sources=["sse"],
        active_source="sse",
        availability={"sse": True},
        is_admin=True,
        job={"job_id": "job1", "status": "ready", "filename": "sample.xlsx", "reupload": True},
        report=report,
        request_job_id="job1",
        active_tab="review",
    )
    assert "Reload validation failed" in html
    assert "Upload a different file" in html
    assert "Rewrite schema with AI" in html
    assert "Propose new transformation with AI" in html


def test_spreadsheet_pipeline_progress_includes_propose_stage() -> None:
    from meshflow.dna.web.portal.spreadsheet_engine.service import spreadsheet_pipeline_progress

    pipeline = spreadsheet_pipeline_progress("proposing")
    labels = [stage["label"] for stage in pipeline["stages"]]
    assert "Propose transformations" in labels
    assert pipeline["stages"][3]["state"] == "active"


def test_in_progress_job_renders_on_review_tab() -> None:
    from meshflow.dna.web.portal.spreadsheet_engine.render import render_spreadsheet_engine_page

    job = {"job_id": "job-abc", "status": "running", "filename": "sample.xlsx"}
    html = render_spreadsheet_engine_page(
        url=lambda path: path,
        sources=["sse"],
        active_source="sse",
        availability={"sse": True},
        is_admin=True,
        job=job,
        request_job_id="job-abc",
        active_tab="review",
        status_url="/api/spreadsheet-engine/status",
    )
    assert 'data-spreadsheet-panel="review"' in html
    assert "spreadsheet-proposal-status" in html
    assert "spreadsheet-proposal-stages" in html
    assert "Parse workbook" in html
    assert "api/spreadsheet-engine/status" in html
    assert 'id="spreadsheet-engine-panel-review"' in html
    assert 'role="tabpanel">' in html


def test_spreadsheet_pipeline_progress_maps_job_status() -> None:
    from meshflow.dna.web.portal.spreadsheet_engine.service import spreadsheet_pipeline_progress

    pipeline = spreadsheet_pipeline_progress(
        "profiling",
        execution_status="running",
    )
    assert pipeline["status_label"] == "Profiling columns"
    assert pipeline["execution_status"] == "running"
    assert pipeline["stages"][0]["state"] == "complete"
    assert pipeline["stages"][1]["state"] == "active"


def test_job_status_includes_pipeline_payload(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MESHFLOW_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("MESHFLOW_S3_BUCKET", raising=False)

    from meshflow.dna.settings import DnaSettings
    from meshflow.dna.web.portal.spreadsheet_engine.service import job_status
    from meshflow.spreadsheet.jobs import create_job, save_job

    job = create_job(filename="sample.xlsx", username="poc")
    job = save_job(
        {
            **job,
            "status": "interpreting",
            "execution_arn": "arn:aws:states:us-east-2:123:execution:spreadsheet:abc",
        }
    )

    class _Sf:
        def describe_execution(self, *, executionArn: str):
            assert executionArn.endswith(":abc")
            return {"status": "RUNNING"}

    class _Boto3:
        def client(self, name: str, **kwargs):
            if name == "stepfunctions":
                return _Sf()
            raise AssertionError(f"unexpected boto3 client {name!r}")

    monkeypatch.setitem(__import__("sys").modules, "boto3", _Boto3())

    settings = DnaSettings(source="dbc", data_dir=tmp_path, company="poc")
    payload = job_status(settings, job_id=job["job_id"], company="poc", environment="dev")
    assert payload["execution_status"] == "running"
    assert payload["pipeline"]["status_label"] == "Generating proposals"
    assert payload["pipeline"]["stages"][2]["state"] == "active"


def test_upload_redirects_to_review_tab(tmp_path: Path, portal_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    from io import BytesIO

    from openpyxl import Workbook

    client = _client(tmp_path)
    client.post("/portal/login", data={"username": "poc", "password": "changeme"})

    wb = Workbook()
    ws = wb.active
    ws.title = "Customers"
    ws.append(["Customer ID", "Company"])
    ws.append(["C1", "Acme"])
    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "")

    response = client.post(
        "/portal/semantics/source-docs/sse",
        data={
            "action": "upload",
            "workbook": (
                buffer,
                "sample.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ),
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    if response.status_code != 302:
        html = response.get_data(as_text=True)
        assert response.status_code == 302, html[:2000]
    location = response.headers.get("Location") or ""
    assert "job_id=" in location
    assert "tab=review" in location

    follow = client.get(location)
    assert follow.status_code == 200
    html = follow.get_data(as_text=True)
    assert "spreadsheet-table-analysis" in html or "Proposed schema" in html
    assert 'id="spreadsheet-proposal-status"' not in html


def test_review_tab_portal_footer_stays_inside_main_column() -> None:
    """Regression: malformed review tabpanel HTML used to eject the portal footer."""
    from bs4 import BeautifulSoup

    from meshflow.dna.web.portal.spreadsheet_engine.render import render_spreadsheet_engine_page
    from meshflow.dna.web.theme import render_portal_page

    job = {
        "job_id": "job-1",
        "status": "ready",
        "filename": "sample.xlsx",
    }
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
    }
    body = render_spreadsheet_engine_page(
        url=lambda path: path,
        sources=["sse"],
        active_source="sse",
        availability={"sse": True},
        is_admin=True,
        job=job,
        report={"tables": [table]},
        active_tab="review",
    )

    class _Client:
        display_name = "POC"

    page = render_portal_page(
        title="Spreadsheet Engine",
        active_path="/portal/semantics/source-docs/sse",
        body=body,
        nav_links=(),
        client=_Client(),
        url=lambda p: p,
        side_nav_title="DNA",
        side_nav_items=(("Spreadsheet Engine", "/portal/semantics/source-docs/sse"),),
        side_nav_id="dna-nav",
    )
    soup = BeautifulSoup(page, "html.parser")
    footer = soup.select_one("footer.portal-footer")
    portal_main = soup.select_one(".portal-main")
    assert footer is not None
    assert portal_main is not None
    assert footer.parent == portal_main
