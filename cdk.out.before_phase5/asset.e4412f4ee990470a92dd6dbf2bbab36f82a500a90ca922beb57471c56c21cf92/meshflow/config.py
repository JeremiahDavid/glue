from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from meshflow.repo_paths import find_project_root

load_dotenv()

PROJECT_ROOT = find_project_root()
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


@dataclass(frozen=True)
class QBDSettings:
    data_dir: Path
    secret_id: str | None = None
    s3_bucket: str | None = None
    s3_prefix: str = "qbd"
    company_name: str | None = None
    company_file: str | None = None
    environment: str = "production"
    qbwc_username: str = ""
    qbwc_password: str = ""
    qbwc_password_hash: str = ""
    qbwc_app_name: str = "Meshflow QBD Connector"
    owner_id: str = ""
    file_id: str = ""
    qbxml_version: str = "13.0"
    qbwc_soap_url: str = ""


@dataclass(frozen=True)
class BCSettings:
    client_id: str
    client_secret: str
    tenant_id: str
    environment_name: str
    company_id: str
    data_dir: Path
    secret_id: str | None = None
    s3_bucket: str | None = None
    s3_prefix: str = "dbc"
    environment: str = "sandbox"


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
    s3_prefix = _resolve_raw_s3_prefix(default_source="qbo")

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


def load_qbd_settings() -> QBDSettings:
    from meshflow.secrets_manager import get_secret_json, resolve_secret_id

    payload: dict[str, Any] | None = None
    secret_id: str | None = None
    try:
        secret_id = resolve_secret_id()
        payload = get_secret_json(secret_id)
    except ValueError:
        secret_id = os.getenv("MESHFLOW_SECRET_ID", "").strip() or None

    data_dir = Path(os.getenv("MESHFLOW_DATA_DIR", str(DEFAULT_DATA_DIR)))
    s3_bucket = os.getenv("MESHFLOW_S3_BUCKET", "").strip() or None
    s3_prefix = _resolve_raw_s3_prefix(default_source="qbd")
    environment = _read_setting("QBD_ENVIRONMENT", payload, default="production").lower()

    qbwc_username = _read_setting("QBD_QBWC_USERNAME", payload)
    password_hash = _read_setting("QBD_QBWC_PASSWORD_HASH", payload)
    plain_password = _read_setting("QBD_QBWC_PASSWORD", payload)
    owner_id = _read_setting("QBD_OWNER_ID", payload)
    file_id = _read_setting("QBD_FILE_ID", payload)

    qbxml_version = _read_setting("QBD_QBXML_VERSION", payload, default="17.0")
    env_qbxml = os.getenv("QBD_QBXML_VERSION", "").strip()
    if env_qbxml:
        qbxml_version = env_qbxml

    return QBDSettings(
        data_dir=data_dir,
        secret_id=secret_id,
        s3_bucket=s3_bucket,
        s3_prefix=s3_prefix,
        company_name=_read_setting("QBD_COMPANY_NAME", payload) or None,
        company_file=_read_setting("QBD_COMPANY_FILE", payload) or None,
        environment=environment,
        qbwc_username=qbwc_username,
        qbwc_password=plain_password,
        qbwc_password_hash=password_hash,
        qbwc_app_name=_read_setting("QBD_QBWC_APP_NAME", payload, default="Meshflow QBD Connector"),
        owner_id=owner_id,
        file_id=file_id,
        qbxml_version=qbxml_version,
        qbwc_soap_url=_read_setting("QBWC_SOAP_URL", payload),
    )


def _resolve_raw_s3_prefix(*, default_source: str) -> str:
    explicit = os.getenv("MESHFLOW_S3_PREFIX", "").strip().strip("/")
    if explicit:
        return explicit

    from meshflow.project_config import resolve_ingest_s3_prefix, resolve_selection

    company, meshflow_environment = resolve_selection()
    source = os.getenv("MESHFLOW_SOURCE", default_source).strip().lower() or default_source
    return resolve_ingest_s3_prefix(company, meshflow_environment, source=source)


def load_bc_settings() -> BCSettings:
    from meshflow.secrets_manager import get_secret_json, resolve_secret_id

    secret_id = resolve_secret_id()
    payload = get_secret_json(secret_id)

    client_id = _read_setting("BC_CLIENT_ID", payload)
    client_secret = _read_setting("BC_CLIENT_SECRET", payload)
    tenant_id = _read_setting("BC_TENANT_ID", payload)
    environment_name = _read_setting("BC_ENVIRONMENT_NAME", payload)
    company_id = _read_setting("BC_COMPANY_ID", payload)
    missing = [
        name
        for name, value in (
            ("BC_CLIENT_ID", client_id),
            ("BC_CLIENT_SECRET", client_secret),
            ("BC_TENANT_ID", tenant_id),
            ("BC_ENVIRONMENT_NAME", environment_name),
            ("BC_COMPANY_ID", company_id),
        )
        if not value
    ]
    if missing:
        raise ValueError(
            f"Missing {', '.join(missing)} in secret {secret_id!r}. "
            "Update the secret in AWS Secrets Manager before running BC ingest."
        )

    environment = _read_setting("BC_ENVIRONMENT", payload, default="sandbox").lower()
    if environment not in {"sandbox", "production"}:
        raise ValueError("BC_ENVIRONMENT must be 'sandbox' or 'production'")

    data_dir = Path(os.getenv("MESHFLOW_DATA_DIR", str(DEFAULT_DATA_DIR)))
    s3_bucket = os.getenv("MESHFLOW_S3_BUCKET", "").strip() or None
    s3_prefix = _resolve_raw_s3_prefix(default_source="dbc")

    return BCSettings(
        client_id=client_id,
        client_secret=client_secret,
        tenant_id=tenant_id,
        environment_name=environment_name,
        company_id=company_id,
        data_dir=data_dir,
        secret_id=secret_id,
        s3_bucket=s3_bucket,
        s3_prefix=s3_prefix,
        environment=environment,
    )
