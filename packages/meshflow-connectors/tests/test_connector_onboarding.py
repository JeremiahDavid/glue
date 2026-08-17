"""Tests for connector onboarding validators."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from meshflow.connectors.onboarding.dbc import list_dbc_companies
from meshflow.connectors.onboarding.qbo import qbo_oauth_status
from meshflow.connectors.onboarding.qbd import generate_qwc_xml, qbd_secret_status


def test_list_dbc_companies_requires_lookup_fields() -> None:
    result = list_dbc_companies({"BC_CLIENT_ID": "id"})
    assert result["ok"] is False
    assert "BC_CLIENT_SECRET" in result["error"]


@patch("meshflow.bc.auth.ensure_access_token")
@patch("meshflow.bc.client.BCClient")
def test_list_dbc_companies_returns_sorted_companies(mock_client_cls, mock_token) -> None:
    mock_token.return_value = MagicMock()
    mock_client_cls.return_value.list_companies.return_value = [
        {"id": "b", "display_name": "Beta"},
        {"id": "a", "display_name": "Alpha"},
    ]
    result = list_dbc_companies(
        {
            "BC_CLIENT_ID": "client",
            "BC_CLIENT_SECRET": "secret",
            "BC_TENANT_ID": "tenant",
            "BC_ENVIRONMENT_NAME": "Production",
        }
    )
    assert result["ok"] is True
    assert len(result["companies"]) == 2


def test_qbo_oauth_status_pending() -> None:
    result = qbo_oauth_status({"QBO_CLIENT_ID": "id", "QBO_CLIENT_SECRET": "secret"})
    assert result["ok"] is False
    assert result["oauth_complete"] is False


def test_qbo_oauth_status_complete() -> None:
    result = qbo_oauth_status(
        {
            "QBO_CLIENT_ID": "id",
            "QBO_CLIENT_SECRET": "secret",
            "refresh_token": "rt",
            "realm_id": "123",
        }
    )
    assert result["ok"] is True
    assert result["oauth_complete"] is True


def test_qbd_secret_status_missing_fields() -> None:
    result = qbd_secret_status({})
    assert result["ok"] is False
    assert "QBD_QBWC_USERNAME" in result["missing"]


def test_generate_qwc_xml_contains_username() -> None:
    xml = generate_qwc_xml(
        app_name="Meshflow",
        soap_url="https://example.com/soap",
        username="operator",
    )
    assert "operator" in xml
    assert "https://example.com/soap" in xml
