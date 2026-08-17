"""QuickBooks Online onboarding helpers."""

from __future__ import annotations

from typing import Any


def qbo_oauth_status(secret_payload: dict[str, Any]) -> dict[str, Any]:
    """Return whether QBO OAuth tokens are present in a secret payload."""
    client_id = str(secret_payload.get("QBO_CLIENT_ID", "")).strip()
    client_secret = str(secret_payload.get("QBO_CLIENT_SECRET", "")).strip()
    refresh_token = str(secret_payload.get("refresh_token", "")).strip()
    realm_id = str(secret_payload.get("realm_id", "")).strip()

    missing = []
    if not client_id:
        missing.append("QBO_CLIENT_ID")
    if not client_secret:
        missing.append("QBO_CLIENT_SECRET")

    if not refresh_token or not realm_id:
        return {
            "ok": False,
            "oauth_complete": False,
            "missing": missing,
            "message": "OAuth pending — run scripts/qbo_auth.py after saving client credentials.",
        }

    return {
        "ok": True,
        "oauth_complete": True,
        "realm_id": realm_id,
        "message": "OAuth tokens present.",
    }
