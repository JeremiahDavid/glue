"""Tests for connector onboarding validators."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from meshflow.connectors.onboarding.dbc import list_dbc_companies, validate_dbc_credentials
from meshflow.connectors.onboarding.qbo import qbo_oauth_status
from meshflow.connectors.onboarding.qbd import generate_qwc_xml, qbd_secret_status


def test_list_dbc_companies_requires_lookup_fields() -> None:
    result = list_dbc_companies({"BC_CLIENT_ID": "id"})
    assert result["ok"] is False
    assert "BC_CLIENT_SECRET" in result["error"]


@patch("meshflow.bc.auth.acquire_client_credentials_token")
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


def test_validate_dbc_credentials_requires_company_id() -> None:
    result = validate_dbc_credentials(
        {
            "BC_CLIENT_ID": "client",
            "BC_CLIENT_SECRET": "secret",
            "BC_TENANT_ID": "tenant",
            "BC_ENVIRONMENT_NAME": "Production",
        }
    )
    assert result["ok"] is False
    assert "BC_COMPANY_ID" in result["error"]


@patch("meshflow.bc.auth.acquire_client_credentials_token")
@patch("meshflow.bc.client.BCClient")
def test_validate_dbc_credentials_probes_entity_access(mock_client_cls, mock_token) -> None:
    mock_token.return_value = MagicMock()
    mock_client = mock_client_cls.return_value
    mock_client.company.return_value = {"id": "company-guid", "displayName": "CRONUS USA, Inc."}
    mock_client.probe_entity_rows.return_value = 1

    result = validate_dbc_credentials(
        {
            "BC_CLIENT_ID": "client",
            "BC_CLIENT_SECRET": "secret",
            "BC_TENANT_ID": "tenant",
            "BC_ENVIRONMENT_NAME": "Production",
            "BC_COMPANY_ID": "company-guid",
        }
    )

    assert result["ok"] is True
    assert result["company_name"] == "CRONUS USA, Inc."
    assert result["probe_entity"] == "company_information"
    assert result["probe_row_count"] == 1
    mock_client.probe_entity_rows.assert_called_once()


@patch("meshflow.bc.auth.acquire_client_credentials_token")
@patch("meshflow.bc.client.BCClient")
def test_validate_dbc_credentials_rejects_entity_forbidden(mock_client_cls, mock_token) -> None:
    import httpx

    mock_token.return_value = MagicMock()
    mock_client = mock_client_cls.return_value
    mock_client.company.return_value = {"id": "company-guid", "displayName": "CRONUS USA, Inc."}
    response = httpx.Response(403, request=httpx.Request("GET", "https://example.test/companyInformation"))
    mock_client.probe_entity_rows.side_effect = httpx.HTTPStatusError(
        "Forbidden",
        request=response.request,
        response=response,
    )

    result = validate_dbc_credentials(
        {
            "BC_CLIENT_ID": "client",
            "BC_CLIENT_SECRET": "secret",
            "BC_TENANT_ID": "tenant",
            "BC_ENVIRONMENT_NAME": "Production",
            "BC_COMPANY_ID": "company-guid",
        }
    )

    assert result["ok"] is False
    assert "HTTP 403" in result["error"]
    assert "ADD RELATED FIELDS" in result["error"]
    assert "D365 BUS FULL ACCESS" in result["error"]


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
