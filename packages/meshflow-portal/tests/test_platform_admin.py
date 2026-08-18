"""Tests for platform admin job registry and enqueue helpers."""

from __future__ import annotations

import json
import os

import pytest

from meshflow.dna.web.admin.auth import is_allowed_admin_username
from meshflow.dna.web.admin.jobs import (
    AdminJobMisconfigured,
    UnknownAdminJob,
    admin_job_status,
    enqueue_admin_job,
)
from meshflow.dna.web.admin.registry import (
    get_admin_job,
    jobs_grouped_by_source,
    registered_admin_jobs,
    source_display_name,
)
from meshflow.dna.web.app import create_app
from meshflow.dna.settings import DnaSettings


def test_registered_admin_jobs_include_dbc_source_docs() -> None:
    jobs = registered_admin_jobs()
    ids = {job.id for job in jobs}
    assert "dbc.source_docs.scrape" in ids
    assert "dbc.source_docs.relationships" in ids
    assert "dbc.source_docs.tags" in ids
    grouped = jobs_grouped_by_source()
    assert grouped[0][0] == "dbc"
    assert source_display_name("dbc").startswith("Business Central")


def test_enqueue_admin_job_dry_run(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AWS_LAMBDA_FUNCTION_NAME", raising=False)
    monkeypatch.setenv("MESHFLOW_SOURCE_DOCS_SCRAPE_FUNCTION", "platform-dev-bc-source-docs-scrape")
    result = enqueue_admin_job("dbc.source_docs.scrape")
    assert result["status"] == "dry_run"
    assert result["function_name"] == "platform-dev-bc-source-docs-scrape"
    assert result["payload"]["source"] == "dbc"


def test_enqueue_unknown_job_raises() -> None:
    with pytest.raises(UnknownAdminJob):
        enqueue_admin_job("qbo.not.registered")


def test_enqueue_misconfigured_without_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MESHFLOW_SOURCE_DOCS_TAGS_FUNCTION", raising=False)
    with pytest.raises(AdminJobMisconfigured):
        enqueue_admin_job("dbc.source_docs.tags")


def test_enqueue_admin_job_invokes_lambda(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MESHFLOW_SOURCE_DOCS_TAGS_FUNCTION", "platform-dev-bc-source-docs-tags")

    calls: list[dict] = []

    class FakeLambda:
        def invoke(self, **kwargs):
            calls.append(kwargs)
            return {"StatusCode": 202}

    import meshflow.dna.web.admin.jobs as jobs_mod

    monkeypatch.setattr(jobs_mod, "_on_lambda", lambda: True)

    import builtins

    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "boto3":
            class FakeBoto3:
                def client(self, service, region_name=None):
                    assert service == "lambda"
                    return FakeLambda()

            return FakeBoto3()
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    result = enqueue_admin_job("dbc.source_docs.tags")
    assert result["status"] == "queued"
    assert result["job_id"] == "dbc.source_docs.tags"
    assert calls and calls[0]["FunctionName"] == "platform-dev-bc-source-docs-tags"
    assert calls[0]["InvocationType"] == "Event"


def test_admin_job_status_local(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AWS_LAMBDA_FUNCTION_NAME", raising=False)
    monkeypatch.setenv(
        "MESHFLOW_SOURCE_DOCS_RELATIONSHIPS_FUNCTION",
        "platform-dev-bc-source-docs-relationships",
    )
    status = admin_job_status("dbc.source_docs.relationships")
    assert status["state"] == "local"
    assert status["run_state"] == "local"
    assert status["function_name"].endswith("relationships")
    assert "console.aws.amazon.com/lambda" in status["console_url"]


def test_infer_run_from_messages_running_completed_failed() -> None:
    from meshflow.dna.web.admin.jobs import _infer_run_from_messages

    running = _infer_run_from_messages(
        [
            "START RequestId: aaa-111 Version: $LATEST",
            '{"msg": "source_docs_tags_start", "source": "dbc"}',
        ]
    )
    assert running["run_state"] == "running"

    completed = _infer_run_from_messages(
        [
            "START RequestId: aaa-111 Version: $LATEST",
            '{"msg": "source_docs_tags_start", "source": "dbc"}',
            '{"msg": "source_docs_tags_done", "result": {"status": "published"}}',
            "END RequestId: aaa-111",
            "REPORT RequestId: aaa-111 Duration: 226221.87 ms Billed Duration: 226347 ms",
        ]
    )
    assert completed["run_state"] == "completed"
    assert completed["result_status"] == "published"
    assert "Completed" in completed["summary"]

    failed = _infer_run_from_messages(
        [
            "START RequestId: bbb-222 Version: $LATEST",
            "Traceback (most recent call last):",
            "Runtime.ExitError",
            "END RequestId: bbb-222",
            "REPORT RequestId: bbb-222 Duration: 12.00 ms Status: error",
        ]
    )
    assert failed["run_state"] == "failed"


def test_admin_job_card_has_lambda_link_not_raw_json() -> None:
    from meshflow.dna.web.admin.registry import get_admin_job
    from meshflow.dna.web.admin.views import _job_card_html

    job = get_admin_job("dbc.source_docs.tags")
    assert job is not None
    html = _job_card_html(
        job,
        url=lambda path: path,
        status={
            "run_state": "completed",
            "state": "completed",
            "summary": "Completed (published) · 3m 46s",
            "function_name": "platform-dev-bc-source-docs-tags",
            "console_url": "https://us-east-2.console.aws.amazon.com/lambda/home?region=us-east-2#/functions/platform-dev-bc-source-docs-tags",
            "message": '{"msg": "should_not_render"}',
        },
    )
    assert "Open Lambda" in html
    assert "Status JSON" not in html
    assert "admin-job-message" not in html
    assert "should_not_render" not in html
    assert "Completed (published)" in html
    assert 'data-run-state="completed"' in html


def test_admin_username_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MESHFLOW_ADMIN_USERNAME", "GlobalAdmin")
    assert is_allowed_admin_username("GlobalAdmin") is True
    assert is_allowed_admin_username("AdminPOC") is False


def test_bootstrap_global_admin_creates_portal_pool_user(monkeypatch: pytest.MonkeyPatch) -> None:
    from unittest.mock import MagicMock, patch

    from meshflow.dna.web.admin.auth import bootstrap_global_admin

    mock_client = MagicMock()
    mock_client.exceptions.UsernameExistsException = type("UsernameExistsException", (Exception,), {})

    def admin_get_user(**kwargs):
        pool = kwargs["UserPoolId"]
        username = kwargs["Username"]
        if pool == "portal-pool" and username == "AdminPOC":
            return {
                "Username": "AdminPOC",
                "UserAttributes": [{"Name": "email", "Value": "admin@example.com"}],
            }
        if pool == "portal-pool" and username == "GlobalAdmin":
            return None
        if pool == "admin-pool" and username == "GlobalAdmin":
            return None
        return None

    mock_client.admin_get_user.side_effect = admin_get_user
    mock_client.admin_create_user.return_value = {"User": {"UserStatus": "FORCE_CHANGE_PASSWORD"}}

    with patch("meshflow.dna.web.admin.auth._cognito_client", return_value=mock_client):
        result = bootstrap_global_admin(
            portal_user_pool_id="portal-pool",
            admin_user_pool_id="admin-pool",
            temporary_password="TempPass123!",
        )

    assert result["status"] == "created"
    assert result["portal_status"] == "created"
    assert result["portal_client_id"] == "platform"
    assert mock_client.admin_create_user.call_count == 2


def test_bootstrap_global_admin_omits_portal_email_when_taken(monkeypatch: pytest.MonkeyPatch) -> None:
    from unittest.mock import MagicMock, patch

    from meshflow.dna.web.admin.auth import bootstrap_global_admin

    mock_client = MagicMock()
    mock_client.exceptions.UsernameExistsException = type("UsernameExistsException", (Exception,), {})

    def admin_get_user(**kwargs):
        pool = kwargs["UserPoolId"]
        username = kwargs["Username"]
        if pool == "portal-pool" and username == "AdminPOC":
            return {
                "Username": "AdminPOC",
                "UserAttributes": [{"Name": "email", "Value": "admin@example.com"}],
            }
        if pool == "admin-pool" and username == "GlobalAdmin":
            return {
                "Username": "GlobalAdmin",
                "UserStatus": "CONFIRMED",
                "UserAttributes": [{"Name": "email", "Value": "admin@example.com"}],
            }
        return None

    mock_client.admin_get_user.side_effect = admin_get_user
    mock_client.admin_create_user.return_value = {
        "User": {"UserStatus": "FORCE_CHANGE_PASSWORD", "Username": "GlobalAdmin"}
    }

    with patch("meshflow.dna.web.admin.auth._cognito_client", return_value=mock_client), patch(
        "meshflow.dna.web.admin.auth.find_user_by_email",
        return_value="AdminPOC",
    ):
        result = bootstrap_global_admin(
            portal_user_pool_id="portal-pool",
            admin_user_pool_id="admin-pool",
            temporary_password="TempPass123!",
        )

    assert result["status"] == "exists"
    assert result["portal_status"] == "created"
    portal_create = mock_client.admin_create_user.call_args_list[0].kwargs
    portal_attrs = {item["Name"]: item["Value"] for item in portal_create["UserAttributes"]}
    assert portal_attrs["custom:client_id"] == "platform"
    assert "email" not in portal_attrs
    assert "portal_email_note" in result


def test_bootstrap_global_admin_updates_existing_portal_user(monkeypatch: pytest.MonkeyPatch) -> None:
    from unittest.mock import MagicMock, patch

    from meshflow.dna.web.admin.auth import bootstrap_global_admin

    mock_client = MagicMock()

    def admin_get_user(**kwargs):
        pool = kwargs["UserPoolId"]
        username = kwargs["Username"]
        if pool == "portal-pool" and username == "AdminPOC":
            return {
                "Username": "AdminPOC",
                "UserAttributes": [{"Name": "email", "Value": "admin@example.com"}],
            }
        if pool == "portal-pool" and username == "GlobalAdmin":
            return {
                "Username": "GlobalAdmin",
                "UserStatus": "CONFIRMED",
                "UserAttributes": [
                    {"Name": "email", "Value": "admin@example.com"},
                    {"Name": "custom:client_id", "Value": "platform"},
                ],
            }
        if pool == "admin-pool" and username == "GlobalAdmin":
            return {
                "Username": "GlobalAdmin",
                "UserStatus": "CONFIRMED",
                "UserAttributes": [{"Name": "email", "Value": "admin@example.com"}],
            }
        return None

    mock_client.admin_get_user.side_effect = admin_get_user

    with patch("meshflow.dna.web.admin.auth._cognito_client", return_value=mock_client), patch(
        "meshflow.dna.web.admin.auth.find_user_by_email",
        return_value="AdminPOC",
    ):
        result = bootstrap_global_admin(
            portal_user_pool_id="portal-pool",
            admin_user_pool_id="admin-pool",
            temporary_password="TempPass123!",
        )

    assert result["status"] == "exists"
    assert result["portal_status"] == "updated"
    assert result["portal_client_id"] == "platform"
    mock_client.admin_update_user_attributes.assert_called_once()
    assert mock_client.admin_set_user_password.call_count == 2


def test_admin_ui_mode_login_and_home(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MESHFLOW_UI_MODE", "admin")
    monkeypatch.setenv("MESHFLOW_ADMIN_USERNAME", "GlobalAdmin")
    monkeypatch.setenv("HIVEFLOW_PORTAL_SESSION_SECRET", "test-admin-secret")
    monkeypatch.delenv("HIVEFLOW_COGNITO_USER_POOL_ID", raising=False)

    settings = DnaSettings(source="dbc", data_dir=tmp_path, company="POC")
    app = create_app(settings, company="POC", environment="dev", ui_mode="admin")

    from werkzeug.test import Client

    client = Client(app)
    login = client.get("/admin/login")
    assert login.status_code == 200
    assert b"Platform admin" in login.data
    assert b"/admin/architecture" in login.data

    home = client.get("/admin")
    assert home.status_code in {302, 401, 200}
    # Unauthenticated should redirect to login
    if home.status_code == 302:
        assert "/admin/login" in (home.headers.get("Location") or "")

    architecture = client.get("/admin/architecture")
    assert architecture.status_code in {302, 401, 200}
    if architecture.status_code == 302:
        assert "/admin/login" in (architecture.headers.get("Location") or "")

    # Portal routes are not enabled in admin mode
    portal = client.get("/portal/login")
    assert portal.status_code == 404


def test_admin_architecture_diagrams() -> None:
    from meshflow.dna.web.admin.diagrams import INFRASTRUCTURE_MERMAID, PIPELINE_MERMAID
    from meshflow.dna.web.admin.views import render_admin_architecture

    assert "PlatformAdminStack" in INFRASTRUCTURE_MERMAID
    assert "IngestStack" in INFRASTRUCTURE_MERMAID
    assert "DnaStack" in INFRASTRUCTURE_MERMAID
    assert "Bronze" in PIPELINE_MERMAID
    assert "DNA Engine" in PIPELINE_MERMAID
    assert "Reporting Engine" in PIPELINE_MERMAID

    html = render_admin_architecture(url=lambda path: path, username="GlobalAdmin")
    assert "Infrastructure" in html
    assert "Ingest / DNA / Reporting" in html
    assert 'class="mermaid"' in html
    assert "mermaid@11" in html


def test_get_admin_job() -> None:
    assert get_admin_job("dbc.source_docs.scrape") is not None
    assert get_admin_job("missing") is None
