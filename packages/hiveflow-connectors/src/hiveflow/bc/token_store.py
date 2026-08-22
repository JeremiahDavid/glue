from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime

from hiveflow.compat import UTC
from typing import Any

from hiveflow.config import BCSettings

logger = logging.getLogger(__name__)

WATERMARKS_METADATA_KEYS = frozenset({"updated_at"})


@dataclass
class BCTokens:
    access_token: str
    tenant_id: str
    environment_name: str
    company_id: str
    token_type: str = "Bearer"
    expires_in: int | None = None
    expires_at: str | None = None
    updated_at: str | None = None

    def touch(self) -> None:
        self.updated_at = datetime.now(UTC).isoformat()


def _bc_secret_source(settings: BCSettings) -> str:
    prefix = settings.s3_prefix.strip("/")
    if prefix.startswith("raw/"):
        slug = prefix.removeprefix("raw/").split("/", 1)[0]
        return slug or "dbc"
    return prefix or "dbc"


def _resolve_bc_secret_id(settings: BCSettings) -> str | None:
    if settings.secret_id:
        return settings.secret_id

    from hiveflow.project_config import resolve_qbo_secret_name, resolve_selection

    company, environment = resolve_selection()
    try:
        return resolve_qbo_secret_name(
            company,
            environment,
            source=_bc_secret_source(settings),
        )
    except ValueError:
        return None


def watermarks_state_key(settings: BCSettings) -> str:
    prefix = settings.s3_prefix.strip("/")
    return f"{prefix}/_state/watermarks.json"


def watermarks_state_path(settings: BCSettings):
    from hiveflow.storage.paths import prefix_path

    return prefix_path(settings.data_dir, settings.s3_prefix, "_state", "watermarks.json")


def load_tokens(settings: BCSettings) -> BCTokens | None:
    from hiveflow.secrets_manager import load_bc_tokens_from_secret

    secret_id = _resolve_bc_secret_id(settings)
    if not secret_id:
        return None
    return load_bc_tokens_from_secret(secret_id)


def save_tokens(settings: BCSettings, tokens: BCTokens) -> None:
    from hiveflow.secrets_manager import save_bc_tokens_to_secret

    secret_id = _resolve_bc_secret_id(settings)
    if not secret_id:
        return
    save_bc_tokens_to_secret(secret_id, tokens)


def save_watermarks(settings: BCSettings, watermarks: dict[str, str]) -> str:
    """Persist incremental ingest watermarks under raw/{source}/_state/watermarks.json."""
    payload: dict[str, Any] = {
        **{key: value for key, value in watermarks.items() if value not in (None, "")},
        "updated_at": datetime.now(UTC).isoformat(),
    }
    if settings.s3_bucket:
        from hiveflow.ingest.storage import write_json_s3

        return write_json_s3(settings, watermarks_state_key(settings), payload)

    path = watermarks_state_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return str(path)


def load_watermarks(settings: BCSettings) -> dict[str, str]:
    """Load incremental ingest watermarks from S3/local state, with one-time secret migration."""
    watermarks = _load_watermarks_from_store(settings)
    if watermarks:
        return watermarks

    migrated = _migrate_watermarks_from_secret(settings)
    if migrated:
        save_watermarks(settings, migrated)
        logger.info("Migrated BC watermarks from Secrets Manager to %s", watermarks_state_key(settings))
    return migrated


def _normalize_watermarks(payload: dict[str, Any] | None) -> dict[str, str]:
    if not payload:
        return {}
    return {
        str(key): str(value)
        for key, value in payload.items()
        if key not in WATERMARKS_METADATA_KEYS and value not in (None, "")
    }


def _load_watermarks_from_store(settings: BCSettings) -> dict[str, str]:
    if settings.s3_bucket:
        from hiveflow.ingest.storage import read_json_s3

        payload = read_json_s3(settings.s3_bucket, watermarks_state_key(settings))
        return _normalize_watermarks(payload)

    from hiveflow.ingest.storage import read_json_local

    payload = read_json_local(watermarks_state_path(settings))
    return _normalize_watermarks(payload)


def _migrate_watermarks_from_secret(settings: BCSettings) -> dict[str, str]:
    from hiveflow.secrets_manager import get_secret_json, resolve_secret_id

    payload = get_secret_json(resolve_secret_id())
    raw = payload.get("watermarks", {})
    if not isinstance(raw, dict):
        return {}
    migrated = {
        str(key): str(value)
        for key, value in raw.items()
        if value not in (None, "")
    }
    return migrated
