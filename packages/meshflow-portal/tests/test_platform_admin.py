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
    assert status["function_name"].endswith("relationships")


def test_admin_username_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MESHFLOW_ADMIN_USERNAME", "GlobalAdmin")
    assert is_allowed_admin_username("GlobalAdmin") is True
    assert is_allowed_admin_username("AdminPOC") is False


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

    home = client.get("/admin")
    assert home.status_code in {302, 401, 200}
    # Unauthenticated should redirect to login
    if home.status_code == 302:
        assert "/admin/login" in (home.headers.get("Location") or "")

    # Portal routes are not enabled in admin mode
    portal = client.get("/portal/login")
    assert portal.status_code == 404


def test_get_admin_job() -> None:
    assert get_admin_job("dbc.source_docs.scrape") is not None
    assert get_admin_job("missing") is None
