"""Tests for connector onboarding validators."""

from __future__ import annotations

from meshflow.connectors.onboarding.qbo import qbo_oauth_status
from meshflow.connectors.onboarding.qbd import generate_qwc_xml, qbd_secret_status


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
