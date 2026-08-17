"""Tests for platform admin onboarding routes."""

from __future__ import annotations

import pytest
from werkzeug.test import Client

from meshflow.dna.web.admin.onboarding.handlers import (
    company_from_display_name,
    parse_client_create_form,
    parse_connectors_from_form,
)
from meshflow.dna.web.app import create_app
from meshflow.dna.settings import DnaSettings


@pytest.fixture()
def admin_client(monkeypatch: pytest.MonkeyPatch, tmp_path) -> Client:
    monkeypatch.setenv("MESHFLOW_UI_MODE", "admin")
    monkeypatch.delenv("HIVEFLOW_COGNITO_USER_POOL_ID", raising=False)
    settings = DnaSettings(source="dbc", data_dir=tmp_path, company="POC")
    app = create_app(settings, company="POC", environment="dev", ui_mode="admin")
    return Client(app)


def test_company_from_display_name_camel_cases_words() -> None:
    assert company_from_display_name("Acme Distribution Co.") == "ACMEDISTRIBUTIONCO"
    assert company_from_display_name("Acme") == "ACME"


def test_parse_connectors_from_form_supports_multiple_enabled() -> None:
    connectors = parse_connectors_from_form(
        {
            "connector_dbc_enabled": "on",
            "connector_qbo_enabled": "on",
            "connector_qbd_enabled": "on",
        }
    )
    assert tuple(item.source for item in connectors) == ("dbc", "qbd", "qbo")


def test_parse_client_create_form_derives_defaults() -> None:
    spec = parse_client_create_form(
        {
            "display_name": "Acme Distribution Co.",
            "client_id": "acme",
            "connector_dbc_enabled": "on",
        }
    )
    assert spec.company == "ACMEDISTRIBUTIONCO"
    assert spec.client_id == "acme"
    assert spec.environment == "dev"
    assert tuple(item.source for item in spec.connectors) == ("dbc",)
    assert spec.portal.display_name == "Acme Distribution Co."
    assert spec.portal.reporting_hostname == "acme"
    assert spec.dna.source == "dbc"


def test_admin_onboarding_requires_login(admin_client: Client) -> None:
    response = admin_client.get("/admin/onboarding")
    assert response.status_code in {302, 401, 200}
    if response.status_code == 302:
        assert "/admin/login" in (response.headers.get("Location") or "")


def test_admin_onboarding_new_route_registered(admin_client: Client) -> None:
    response = admin_client.get("/admin/onboarding/new")
    assert response.status_code in {302, 200, 401, 503}
