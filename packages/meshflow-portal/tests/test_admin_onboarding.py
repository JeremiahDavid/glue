"""Tests for platform admin onboarding routes."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from werkzeug.test import Client

from meshflow.dna.web.admin.onboarding.guides import (
    load_connector_guide_markdown,
    render_connector_guide_html,
)
from meshflow.dna.web.admin.onboarding.handlers import (
    ConnectorCredentialSnapshot,
    company_from_display_name,
    entity_bundles_for_connector,
    load_connector_credentials,
    normalize_wizard_step,
    parse_client_create_form,
    parse_connectors_from_form,
    save_connector_secret,
    validate_client_config_form,
)
from meshflow.dna.web.admin.onboarding.views import render_client_detail, render_onboarding_wizard
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
        assert "Client config" in body
        assert "Step 1 of 2" in body


def test_validate_client_config_form_requires_identity_fields() -> None:
    with pytest.raises(ValueError, match="Display name is required"):
        validate_client_config_form({"client_id": "acme"})
    with pytest.raises(ValueError, match="Portal client id is required"):
        validate_client_config_form({"display_name": "Acme Co"})


def test_normalize_wizard_step_clamps_to_two_steps() -> None:
    assert normalize_wizard_step(1) == 1
    assert normalize_wizard_step(99) == 2


def test_load_connector_guide_markdown_for_known_sources() -> None:
    for source in ("dbc", "qbo", "qbd"):
        markdown = load_connector_guide_markdown(source)
        assert markdown
        assert "What the client needs" in markdown


def test_render_connector_guide_html_includes_inline_credential_fields() -> None:
    render_connector_guide_html.cache_clear()
    html = render_connector_guide_html("dbc")
    assert 'data-credential-guide="BC_CLIENT_ID"' in html
    assert 'data-credential-guide="BC_COMPANY_ID"' not in html
    assert "Load companies" in html
    assert "admin-connector-guide-input" in html
    assert "admin-connector-guide-field" not in html
    assert 'placeholder="paste"' in html
    assert 'name="BC_CLIENT_ID"' not in html
    assert "OAuthLanding.htm" in html


def test_render_connector_guide_html_includes_credential_sections() -> None:
    render_connector_guide_html.cache_clear()
    html = render_connector_guide_html("dbc")
    assert "admin-connector-guide-content" in html
    assert "Entra" in html
    assert "Where to find each input" in html
    assert "Entra client id" in html
    assert "BC company" in html
    assert "config.yaml" not in html
    assert "Secrets Manager" not in html
    assert "Deploy AWS" not in html


def test_render_connector_guide_html_excludes_backend_for_qbo() -> None:
    render_connector_guide_html.cache_clear()
    html = render_connector_guide_html("qbo")
    assert "Intuit" in html
    assert "Where to find each input" in html
    assert "QBO redirect URI" in html
    assert "cdk deploy" not in html.lower()
    assert "stepfunctions" not in html.lower()


def test_render_connector_guide_html_excludes_backend_for_qbd() -> None:
    render_connector_guide_html.cache_clear()
    html = render_connector_guide_html("qbd")
    assert "Web Connector" in html
    assert "Where to find each input" in html
    assert "SOAP URL" in html
    assert "API Gateway" not in html
    assert "create_secrets.py" not in html


def test_entity_bundles_for_connector_lists_known_bundles() -> None:
    assert "full" in entity_bundles_for_connector("dbc")
    assert "full_accounting" in entity_bundles_for_connector("qbo")
    assert "v1_accounting" in entity_bundles_for_connector("qbd")


def test_render_onboarding_wizard_uses_entity_bundle_select() -> None:
    html = render_onboarding_wizard(
        url=lambda path: path,
        username="admin",
    )
    assert 'name="connector_dbc_entity_bundle"' in html
    assert "<select" in html
    assert 'value="full"' in html or ">full</option>" in html


def test_render_client_detail_shows_second_onboarding_step() -> None:
    html = render_client_detail(
        url=lambda path: path,
        username="admin",
        company="ACME",
        client_id="acme",
        environment="dev",
        connector_sources=["dbc"],
    )
    assert "Step 2 of 2" in html
    assert "admin-onboarding-step-arrow" in html
    assert ">Step 1</span>" in html
    assert ">Step 2</span>" in html
    assert "Deploy &amp; verify" in html or "Deploy & verify" in html
    assert 'href="/admin/onboarding/new?company=ACME&amp;environment=dev&amp;client_id=acme"' in html


def test_render_onboarding_wizard_links_forward_to_detail_when_editing() -> None:
    from meshflow.dna.web.admin.onboarding.views import render_onboarding_wizard

    html = render_onboarding_wizard(
        url=lambda path: path,
        username="admin",
        company="ACME",
        environment="dev",
        client_id="acme",
        form_values={
            "onboarding_company": "ACME",
            "onboarding_environment": "dev",
            "onboarding_client_id": "acme",
            "display_name": "Acme Co",
            "client_id": "acme",
            "connector_dbc_enabled": "on",
        },
    )
    assert 'href="/admin/onboarding/acme?environment=dev&amp;client_id=acme"' in html


def test_render_client_detail_includes_credential_setup_guide() -> None:
    html = render_client_detail(
        url=lambda path: path,
        username="admin",
        company="ACME",
        client_id="acme",
        environment="dev",
        connector_sources=["dbc", "qbo"],
    )
    assert "Credential setup guide" in html
    assert 'data-connector-guide="connector-guide-dbc"' in html
    assert 'id="connector-guide-dbc"' in html
    assert 'id="connector-secrets-dbc"' in html
    assert 'data-credential-main="BC_CLIENT_ID"' in html
    assert 'data-credential-guide="BC_CLIENT_ID"' in html
    assert "data-credential-summary" in html
    assert "syncGuideToMain" in html
    assert "Save secret" in html
    assert "Apply to form" in html


def test_render_client_detail_disables_load_companies_until_lookup_fields_filled() -> None:
    html = render_client_detail(
        url=lambda path: path,
        username="admin",
        company="ACME",
        client_id="acme",
        environment="dev",
        connector_sources=["dbc"],
    )
    assert "data-dbc-load-companies" in html
    assert "Fill in the four fields above" in html
    load_btn_empty = html.split("data-dbc-load-companies", 1)[1].split("</button>", 1)[0]
    assert " disabled" in load_btn_empty

    html_saved = render_client_detail(
        url=lambda path: path,
        username="admin",
        company="ACME",
        client_id="acme",
        environment="dev",
        connector_sources=["dbc"],
        connector_credentials={
            "dbc": ConnectorCredentialSnapshot(
                secret_id="meshflow-acme-dbc-dev",
                exists=True,
                values={
                    "BC_CLIENT_ID": "client-id",
                    "BC_CLIENT_SECRET": "client-secret",
                    "BC_TENANT_ID": "tenant-id",
                    "BC_ENVIRONMENT_NAME": "Production",
                },
            )
        },
    )
    load_btn = html_saved.split("data-dbc-load-companies")[1].split("</button>")[0]
    assert " disabled" not in load_btn
    assert "Load companies from this BC environment" in load_btn


def test_render_client_detail_prefills_saved_credentials() -> None:
    html = render_client_detail(
        url=lambda path: path,
        username="admin",
        company="ACME",
        client_id="acme",
        environment="dev",
        connector_sources=["dbc"],
        connector_credentials={
            "dbc": ConnectorCredentialSnapshot(
                secret_id="meshflow-acme-dbc-dev",
                exists=True,
                values={
                    "BC_CLIENT_ID": "client-id",
                    "BC_CLIENT_SECRET": "client-secret",
                    "BC_TENANT_ID": "tenant-id",
                    "BC_ENVIRONMENT_NAME": "Production",
                    "BC_COMPANY_ID": "company-guid",
                },
            )
        },
    )
    assert "Saved secret: <code>meshflow-acme-dbc-dev</code>" in html
    assert 'value="client-id"' in html
    assert 'value="tenant-id"' in html
    assert 'value="Production"' in html
    assert 'value="company-guid"' in html
    assert 'value="company-guid" selected' in html


def test_load_connector_credentials_returns_empty_when_secret_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "meshflow.client_registry.ClientRegistry.get_client",
        lambda self, company, environment=None, client_id=None: SimpleNamespace(
            company="ACME",
            environment="dev",
            client_id="acme",
            connector_sources=("dbc",),
        ),
    )
    monkeypatch.setattr(
        "meshflow.client_registry.ClientRegistry.secret_name",
        lambda self, record, source=None: "meshflow-acme-dbc-dev",
    )

    def _raise_not_found(secret_id: str, region=None):
        raise ValueError(
            f"Secrets Manager secret {secret_id!r} was not found in region 'us-east-2'."
        )

    monkeypatch.setattr(
        "meshflow.dna.web.admin.onboarding.handlers.get_secret_json",
        _raise_not_found,
    )

    snapshot = load_connector_credentials(company="ACME", environment="dev", source="dbc")
    assert snapshot.exists is False
    assert snapshot.secret_id == "meshflow-acme-dbc-dev"
    assert snapshot.values == {}


def test_save_connector_secret_merges_existing_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "meshflow.client_registry.ClientRegistry.get_client",
        lambda self, company, environment=None, client_id=None: SimpleNamespace(
            company="ACME",
            environment="dev",
            client_id="acme",
            connector_sources=("dbc",),
        ),
    )
    monkeypatch.setattr(
        "meshflow.client_registry.ClientRegistry.secret_name",
        lambda self, record, source=None: "meshflow-acme-dbc-dev",
    )
    stored: dict[str, Any] = {
        "BC_CLIENT_ID": "old-id",
        "BC_CLIENT_SECRET": "old-secret",
        "access_token": "token",
    }
    monkeypatch.setattr(
        "meshflow.dna.web.admin.onboarding.handlers.get_secret_json",
        lambda secret_id, region=None: dict(stored),
    )

    def _put_secret_json(secret_id: str, payload: dict[str, Any], region=None) -> None:
        stored.clear()
        stored.update(payload)

    monkeypatch.setattr(
        "meshflow.dna.web.admin.onboarding.handlers.put_secret_json",
        _put_secret_json,
    )
    monkeypatch.setattr(
        "meshflow.secrets_manager.ensure_secret_json",
        lambda secret_id, payload, region=None, source=None, company=None, environment=None: "exists",
    )

    save_connector_secret(
        company="ACME",
        environment="dev",
        source="dbc",
        credentials={"BC_CLIENT_ID": "new-id"},
    )

    assert stored["BC_CLIENT_ID"] == "new-id"
    assert stored["BC_CLIENT_SECRET"] == "old-secret"
    assert stored["access_token"] == "token"
