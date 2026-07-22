from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_TOKEN_PATH = PROJECT_ROOT / ".meshflow" / "qbo_tokens.json"


@dataclass(frozen=True)
class QBOSettings:
    client_id: str
    client_secret: str
    environment: str
    redirect_uri: str
    data_dir: Path
    token_path: Path
    secret_id: str | None = None
    s3_bucket: str | None = None
    s3_prefix: str = "qbo"

    @property
    def api_base_url(self) -> str:
        if self.environment == "production":
            return "https://quickbooks.api.intuit.com"
        return "https://sandbox-quickbooks.api.intuit.com"

    @property
    def is_sandbox(self) -> bool:
        return self.environment != "production"


def _read_setting(name: str, payload: dict[str, Any] | None, *, default: str = "") -> str:
    if payload and payload.get(name) not in (None, ""):
        return str(payload[name]).strip()
    return os.getenv(name, default).strip()


def load_qbo_settings() -> QBOSettings:
    from meshflow.secrets_manager import get_secret_json, resolve_secret_id

    secret_id = resolve_secret_id()
    payload = get_secret_json(secret_id)

    client_id = _read_setting("QBO_CLIENT_ID", payload)
    client_secret = _read_setting("QBO_CLIENT_SECRET", payload)
    if not client_id or not client_secret:
        raise ValueError(
            f"Missing QBO_CLIENT_ID or QBO_CLIENT_SECRET in secret {secret_id!r}. "
            "Update the secret in AWS Secrets Manager before running auth or ingest."
        )

    environment = _read_setting("QBO_ENVIRONMENT", payload, default="sandbox").lower()
    if environment not in {"sandbox", "production"}:
        raise ValueError("QBO_ENVIRONMENT must be 'sandbox' or 'production'")

    data_dir = Path(os.getenv("MESHFLOW_DATA_DIR", str(DEFAULT_DATA_DIR)))
    token_path = Path(os.getenv("QBO_TOKEN_PATH", str(DEFAULT_TOKEN_PATH)))
    s3_bucket = os.getenv("MESHFLOW_S3_BUCKET", "").strip() or None
    s3_prefix = os.getenv("MESHFLOW_S3_PREFIX", "qbo").strip().strip("/") or "qbo"

    return QBOSettings(
        client_id=client_id,
        client_secret=client_secret,
        environment=environment,
        redirect_uri=_read_setting(
            "QBO_REDIRECT_URI",
            payload,
            default="http://localhost:8080/callback",
        ),
        data_dir=data_dir,
        token_path=token_path,
        secret_id=secret_id,
        s3_bucket=s3_bucket,
        s3_prefix=s3_prefix,
    )
