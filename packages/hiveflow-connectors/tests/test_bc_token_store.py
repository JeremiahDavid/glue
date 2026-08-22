"""Tests for BC token persistence helpers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from hiveflow.bc.token_store import BCTokens, save_tokens
from hiveflow.config import BCSettings


def _settings(**overrides) -> BCSettings:
    defaults = {
        "client_id": "client",
        "client_secret": "secret",
        "tenant_id": "tenant",
        "environment_name": "Production",
        "company_id": "00000000-0000-0000-0000-000000000001",
        "data_dir": Path("."),
    }
    defaults.update(overrides)
    return BCSettings(**defaults)


def test_save_tokens_skips_when_secret_cannot_be_resolved() -> None:
    tokens = BCTokens(
        access_token="token",
        tenant_id="tenant",
        environment_name="Production",
        company_id="00000000-0000-0000-0000-000000000001",
    )

    with patch("hiveflow.bc.token_store._resolve_bc_secret_id", return_value=None):
        with patch("hiveflow.secrets_manager.save_bc_tokens_to_secret") as save_secret:
            save_tokens(_settings(), tokens)

    save_secret.assert_not_called()


def test_save_tokens_uses_resolved_secret_id() -> None:
    tokens = BCTokens(
        access_token="token",
        tenant_id="tenant",
        environment_name="Production",
        company_id="00000000-0000-0000-0000-000000000001",
    )

    with patch("hiveflow.bc.token_store._resolve_bc_secret_id", return_value="hiveflow-poc-dbc-dev"):
        with patch("hiveflow.secrets_manager.save_bc_tokens_to_secret") as save_secret:
            save_tokens(_settings(), tokens)

    save_secret.assert_called_once_with("hiveflow-poc-dbc-dev", tokens)
