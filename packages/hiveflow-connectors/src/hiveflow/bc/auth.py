from __future__ import annotations

from datetime import datetime, timedelta

from hiveflow.compat import UTC
from typing import Any

import httpx

from hiveflow.bc.token_store import BCTokens
from hiveflow.config import BCSettings

BC_SCOPE = "https://api.businesscentral.dynamics.com/.default"
TOKEN_SKEW_SECONDS = 300


def _authority(tenant_id: str) -> str:
    return f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"


def _parse_expires_at(expires_in: int | None) -> str | None:
    if expires_in is None:
        return None
    return (datetime.now(UTC) + timedelta(seconds=int(expires_in))).isoformat()


def _token_is_valid(tokens: BCTokens) -> bool:
    if not tokens.access_token:
        return False
    if not tokens.expires_at:
        return True
    try:
        expires_at = datetime.fromisoformat(tokens.expires_at)
    except ValueError:
        return False
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return expires_at > datetime.now(UTC) + timedelta(seconds=TOKEN_SKEW_SECONDS)


def acquire_client_credentials_token(settings: BCSettings) -> BCTokens:
    """Acquire an application access token for the Business Central API."""
    response = httpx.post(
        _authority(settings.tenant_id),
        data={
            "grant_type": "client_credentials",
            "client_id": settings.client_id,
            "client_secret": settings.client_secret,
            "scope": BC_SCOPE,
        },
        timeout=60.0,
    )
    response.raise_for_status()
    payload: dict[str, Any] = response.json()
    access_token = str(payload.get("access_token", "")).strip()
    if not access_token:
        raise RuntimeError("Business Central token response did not include access_token")

    return BCTokens(
        access_token=access_token,
        tenant_id=settings.tenant_id,
        environment_name=settings.environment_name,
        company_id=settings.company_id,
        token_type=str(payload.get("token_type", "Bearer")).strip() or "Bearer",
        expires_in=payload.get("expires_in"),
        expires_at=_parse_expires_at(payload.get("expires_in")),
    )


def ensure_access_token(settings: BCSettings, tokens: BCTokens | None) -> BCTokens:
    if tokens is not None and _token_is_valid(tokens):
        return tokens
    refreshed = acquire_client_credentials_token(settings)
    from hiveflow.bc.token_store import save_tokens

    save_tokens(settings, refreshed)
    return refreshed
