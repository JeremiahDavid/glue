from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from intuitlib.exceptions import AuthClientError

from hiveflow.config import QBOSettings
from hiveflow.qbo.oauth import (
    access_token_is_valid,
    ensure_access_token,
    refresh_access_token,
)
from hiveflow.qbo.token_store import QBOTokens


def _auth_client_error(message: str) -> AuthClientError:
    response = MagicMock()
    response.status_code = 400
    response.content = f'{{"error":"{message}"}}'.encode()
    response.text = message
    response.headers.get.return_value = "tid"
    return AuthClientError(response)


def _settings() -> QBOSettings:
    return QBOSettings(
        client_id="client-id",
        client_secret="client-secret",
        environment="sandbox",
        redirect_uri="http://localhost:8080/callback",
        data_dir=Path("data"),
        token_path=Path(".hiveflow/qbo_tokens.json"),
        secret_id="hiveflow-poc-qbo-dev",
    )


def _fresh_tokens(*, access_token: str = "access", refresh_token: str = "refresh-1") -> QBOTokens:
    return QBOTokens(
        access_token=access_token,
        refresh_token=refresh_token,
        realm_id="realm-1",
        expires_in=3600,
        updated_at=datetime.now(UTC).isoformat(),
    )


def test_access_token_is_valid_when_recent() -> None:
    assert access_token_is_valid(_fresh_tokens()) is True


def test_access_token_is_invalid_when_expired() -> None:
    tokens = _fresh_tokens()
    tokens.updated_at = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
    assert access_token_is_valid(tokens) is False


def test_ensure_access_token_returns_cached_token_without_refresh() -> None:
    settings = _settings()
    tokens = _fresh_tokens()

    with patch("hiveflow.qbo.oauth.refresh_access_token") as refresh:
        result = ensure_access_token(settings, tokens)

    assert result is tokens
    refresh.assert_not_called()


def test_ensure_access_token_refreshes_when_expired() -> None:
    settings = _settings()
    tokens = _fresh_tokens()
    tokens.updated_at = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
    refreshed = _fresh_tokens(access_token="access-new", refresh_token="refresh-2")

    with patch("hiveflow.qbo.oauth.refresh_access_token", return_value=refreshed) as refresh:
        result = ensure_access_token(settings, tokens)

    assert result.access_token == "access-new"
    refresh.assert_called_once_with(settings, tokens)


def test_refresh_access_token_reuses_rotated_secret_after_invalid_grant() -> None:
    settings = _settings()
    stale = _fresh_tokens(refresh_token="refresh-old")
    rotated = _fresh_tokens(access_token="access-from-peer", refresh_token="refresh-new")

    with (
        patch("hiveflow.qbo.token_store.load_tokens", return_value=stale),
        patch(
            "hiveflow.qbo.oauth._refresh_with_auth_client",
            side_effect=_auth_client_error("invalid_grant"),
        ) as refresh,
        patch("hiveflow.qbo.oauth._load_latest_tokens", side_effect=[stale, rotated]),
    ):
        result = refresh_access_token(settings, stale)

    assert result.access_token == "access-from-peer"
    refresh.assert_called_once()


def test_refresh_access_token_raises_when_refresh_token_revoked() -> None:
    settings = _settings()
    tokens = _fresh_tokens()

    with (
        patch("hiveflow.qbo.oauth._load_latest_tokens", return_value=tokens),
        patch(
            "hiveflow.qbo.oauth._refresh_with_auth_client",
            side_effect=_auth_client_error("invalid_grant"),
        ),
    ):
        with pytest.raises(RuntimeError, match="Re-run scripts/qbo_auth.py"):
            refresh_access_token(settings, tokens)
