from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from hiveflow.compat import UTC
from pathlib import Path


@dataclass
class QBOTokens:
    access_token: str
    refresh_token: str
    realm_id: str
    token_type: str = "bearer"
    expires_in: int | None = None
    updated_at: str | None = None

    def touch(self) -> None:
        self.updated_at = datetime.now(UTC).isoformat()


def load_tokens(path: Path) -> QBOTokens | None:
    from hiveflow.secrets_manager import load_tokens_from_secret, resolve_secret_id

    return load_tokens_from_secret(resolve_secret_id())


def save_tokens(path: Path, tokens: QBOTokens) -> None:
    from hiveflow.secrets_manager import resolve_secret_id, save_tokens_to_secret

    save_tokens_to_secret(resolve_secret_id(), tokens)
