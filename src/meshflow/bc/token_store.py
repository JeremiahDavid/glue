from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from meshflow.config import BCSettings


@dataclass
class BCTokens:
    access_token: str
    tenant_id: str
    environment_name: str
    company_id: str
    token_type: str = "Bearer"
    expires_in: int | None = None
    expires_at: str | None = None
    watermarks: dict[str, str] | None = None
    updated_at: str | None = None

    def touch(self) -> None:
        self.updated_at = datetime.now(UTC).isoformat()


def load_tokens(settings: BCSettings) -> BCTokens | None:
    from meshflow.secrets_manager import load_bc_tokens_from_secret, resolve_secret_id

    return load_bc_tokens_from_secret(resolve_secret_id())


def save_tokens(settings: BCSettings, tokens: BCTokens) -> None:
    from meshflow.secrets_manager import resolve_secret_id, save_bc_tokens_to_secret

    save_bc_tokens_to_secret(resolve_secret_id(), tokens)


def save_watermarks(settings: BCSettings, watermarks: dict[str, str]) -> None:
    from meshflow.secrets_manager import merge_secret_json, resolve_secret_id

    merge_secret_json(resolve_secret_id(), {"watermarks": watermarks})


def load_watermarks(settings: BCSettings) -> dict[str, str]:
    from meshflow.secrets_manager import get_secret_json, resolve_secret_id

    payload = get_secret_json(resolve_secret_id())
    raw = payload.get("watermarks", {})
    if not isinstance(raw, dict):
        return {}
    return {str(key): str(value) for key, value in raw.items() if value not in (None, "")}
