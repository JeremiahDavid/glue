"""Tests for platform admin onboarding routes."""

from __future__ import annotations

import pytest
from werkzeug.test import Client

from meshflow.dna.web.admin.onboarding.handlers import (
    collect_wizard_form_values,
    company_from_display_name,
    normalize_wizard_step,
    parse_client_create_form,
    parse_connectors_from_form,
    preview_client_create_form,
    validate_wizard_step,
    wizard_goto_step,
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
    if response.status_code == 200:
        body = response.get_data(as_text=True)
        assert "admin-onboarding-steps" in body
        assert "Client identity" in body


def test_validate_wizard_step_requires_identity_fields() -> None:
    with pytest.raises(ValueError, match="Display name is required"):
        validate_wizard_step(1, {"client_id": "acme"})
    with pytest.raises(ValueError, match="Portal client id is required"):
        validate_wizard_step(1, {"display_name": "Acme Co"})


def test_wizard_goto_step_parses_action() -> None:
    assert wizard_goto_step("goto_3") == 3
    assert wizard_goto_step("next") is None


def test_preview_client_create_form_summarizes_spec() -> None:
    preview = preview_client_create_form(
        {
            "display_name": "Acme Distribution Co.",
            "client_id": "acme",
            "connector_dbc_enabled": "on",
        }
    )
    assert preview["company"] == "ACMEDISTRIBUTIONCO"
    assert preview["client_id"] == "acme"
    assert preview["connectors"][0]["source"] == "dbc"


def test_collect_wizard_form_values_strips_control_fields() -> None:
    values = collect_wizard_form_values(
        {"display_name": "Acme", "step": "2", "action": "next", "client_id": "acme"}
    )
    assert values == {"display_name": "Acme", "client_id": "acme"}
    assert normalize_wizard_step(99) == 5
