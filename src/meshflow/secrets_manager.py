from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

if TYPE_CHECKING:
    from meshflow.qbo.token_store import QBOTokens


QBO_SECRET_KEYS = frozenset(
    {
        "QBO_CLIENT_ID",
        "QBO_CLIENT_SECRET",
        "QBO_ENVIRONMENT",
        "QBO_REDIRECT_URI",
        "access_token",
        "refresh_token",
        "realm_id",
        "token_type",
        "expires_in",
        "updated_at",
    }
)
def resolve_secret_id() -> str:
    explicit = os.getenv("MESHFLOW_SECRET_ID", "").strip()
    if explicit:
        return explicit

    from meshflow.project_config import resolve_qbo_secret_name

    company = os.getenv("MESHFLOW_COMPANY", "").strip() or None
    environment = os.getenv("MESHFLOW_ENVIRONMENT", "").strip() or None
    source = os.getenv("MESHFLOW_SOURCE", "").strip() or None
    return resolve_qbo_secret_name(company, environment, source)


def resolve_aws_region() -> str | None:
    for name in ("MESHFLOW_AWS_REGION", "AWS_REGION", "AWS_DEFAULT_REGION"):
        value = os.getenv(name, "").strip()
        if value:
            return value

    from meshflow.project_config import get_config_value

    configured = get_config_value("aws.region", default="")
    configured = str(configured).strip()
    return configured or None


def _secrets_client(*, region: str | None = None):
    try:
        import boto3
    except ImportError as exc:
        raise ImportError(
            "boto3 is required for AWS Secrets Manager access. "
            'Install meshflow with dependencies: pip install -e ".[dev]"'
        ) from exc

    return boto3.client(
        "secretsmanager",
        region_name=region or resolve_aws_region(),
    )


def qbo_secret_placeholder_payload(*, qbo_environment: str = "sandbox") -> dict[str, str]:
    environment = qbo_environment.strip().lower()
    if environment not in {"sandbox", "production"}:
        raise ValueError("qbo_environment must be 'sandbox' or 'production'")

    return {
        "QBO_CLIENT_ID": "REPLACE_ME",
        "QBO_CLIENT_SECRET": "REPLACE_ME",
        "QBO_ENVIRONMENT": environment,
        "QBO_REDIRECT_URI": "http://localhost:8080/callback",
        "access_token": "",
        "refresh_token": "",
        "realm_id": "",
    }


def ensure_secret_json(
    secret_id: str,
    payload: dict[str, Any],
    *,
    region: str | None = None,
    description: str | None = None,
) -> str:
    """Create a JSON secret if missing. Returns 'created' or 'exists'."""
    from botocore.exceptions import ClientError

    client = _secrets_client(region=region)
    try:
        client.create_secret(
            Name=secret_id,
            Description=description or f"Meshflow QBO credentials ({secret_id})",
            SecretString=json.dumps(payload, indent=2),
        )
        return "created"
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code", "")
        if error_code == "ResourceExistsException":
            return "exists"
        raise


@dataclass(frozen=True)
class QBOSecretSpec:
    secret_id: str
    region: str
    payload: dict[str, Any]
    description: str


def _extract_qbo_payload(entry: dict[str, Any]) -> dict[str, Any]:
    if "values" in entry:
        values = entry["values"]
        if not isinstance(values, dict):
            raise ValueError("'values' must be a mapping of secret keys")
        payload = {str(key): value for key, value in values.items()}
    else:
        payload = {
            str(key): value
            for key, value in entry.items()
            if str(key) in QBO_SECRET_KEYS
        }

    if not payload:
        raise ValueError("Secret spec must include QBO secret fields or a 'values' mapping")

    qbo_environment = str(payload.get("QBO_ENVIRONMENT", "sandbox")).strip().lower()
    defaults = qbo_secret_placeholder_payload(qbo_environment=qbo_environment)
    merged = defaults.copy()
    merged.update(payload)
    return merged


def _resolve_secret_spec(entry: dict[str, Any], *, config_path: Path | None) -> QBOSecretSpec:
    from meshflow.project_config import (
        DEFAULT_CONFIG_PATH,
        get_config_value,
        resolve_qbo_secret_name,
    )

    entry_config = entry.get("config")
    if entry_config is not None:
        resolved_config_path = Path(str(entry_config).strip())
        if not resolved_config_path.is_absolute():
            resolved_config_path = DEFAULT_CONFIG_PATH.parent / resolved_config_path
    else:
        resolved_config_path = config_path

    secret_name = str(entry.get("secret_name", "")).strip()
    company = str(entry.get("company", "")).strip() or None
    source = str(entry.get("source", "")).strip() or None
    environment = str(entry.get("environment", "")).strip() or None

    if secret_name:
        secret_id = secret_name
    elif company and source and environment:
        secret_id = resolve_qbo_secret_name(
            company,
            environment,
            source,
            path=resolved_config_path,
        )
    else:
        raise ValueError(
            "Each secret spec must include company, source, and environment, "
            "or secret_name with region"
        )

    region = str(entry.get("region", "")).strip()
    if not region:
        if company and environment:
            region = str(
                get_config_value(
                    "aws.region",
                    company=company,
                    environment=environment,
                    path=resolved_config_path,
                )
            ).strip()
        else:
            raise ValueError("region is required when secret_name is used without company/environment")
    if not region:
        raise ValueError(
            f"Missing aws.region for {company}/{environment}. "
            "Set it in config.yaml or region in the secrets YAML."
        )

    description = str(entry.get("description", "")).strip()
    if not description and company and source and environment:
        description = f"QuickBooks Online credentials for {company}/{source}/{environment}"
    elif not description:
        description = f"Meshflow QBO credentials ({secret_id})"

    return QBOSecretSpec(
        secret_id=secret_id,
        region=region,
        payload=_extract_qbo_payload(entry),
        description=description,
    )


def load_qbo_secret_specs(
    path: Path,
    *,
    config_path: Path | None = None,
) -> list[QBOSecretSpec]:
    with path.open(encoding="utf-8") as handle:
        document = yaml.safe_load(handle)

    if document is None:
        raise ValueError(f"{path} is empty")

    if not isinstance(document, dict):
        raise ValueError(f"{path} must contain a YAML mapping at the top level")

    entries: list[dict[str, Any]]
    if "secrets" in document:
        raw_entries = document["secrets"]
        if not isinstance(raw_entries, list) or not raw_entries:
            raise ValueError(f"{path} secrets must be a non-empty list")
        entries = []
        for index, item in enumerate(raw_entries):
            if not isinstance(item, dict):
                raise ValueError(f"{path} secrets[{index}] must be a mapping")
            entries.append(item)
    else:
        entries = [document]

    return [_resolve_secret_spec(entry, config_path=config_path) for entry in entries]


def create_qbo_secrets_from_yaml(
    path: Path,
    *,
    config_path: Path | None = None,
    update_existing: bool = False,
) -> tuple[int, int, int]:
    """Create secrets defined in YAML. Returns created, existing, updated counts."""
    created = 0
    existing = 0
    updated = 0

    for spec in load_qbo_secret_specs(path, config_path=config_path):
        result = ensure_secret_json(
            spec.secret_id,
            spec.payload,
            region=spec.region,
            description=spec.description,
        )
        if result == "created":
            created += 1
            print(f"Created {spec.secret_id} in {spec.region}")
            continue

        existing += 1
        if update_existing:
            put_secret_json(spec.secret_id, spec.payload, region=spec.region)
            updated += 1
            print(f"Updated {spec.secret_id} in {spec.region}")
        else:
            print(f"Already exists: {spec.secret_id} in {spec.region}")

    return created, existing, updated


def get_secret_json(secret_id: str, *, region: str | None = None) -> dict[str, Any]:
    from botocore.exceptions import ClientError

    resolved_region = region or resolve_aws_region() or "default"
    try:
        response = _secrets_client(region=region).get_secret_value(SecretId=secret_id)
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code", "")
        if error_code == "ResourceNotFoundException":
            raise ValueError(
                f"Secrets Manager secret {secret_id!r} was not found in region {resolved_region!r}. "
                "Run `python scripts/create_secrets.py --file secrets.example.yaml` "
                "(with your values filled in)."
            ) from exc
        raise

    raw = response.get("SecretString")
    if not raw:
        raise ValueError(f"Secret {secret_id!r} has no SecretString payload")

    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError(f"Secret {secret_id!r} must contain a JSON object")
    return payload


def put_secret_json(secret_id: str, payload: dict[str, Any], *, region: str | None = None) -> None:
    _secrets_client(region=region).put_secret_value(
        SecretId=secret_id,
        SecretString=json.dumps(payload, indent=2),
    )


def merge_secret_json(secret_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    payload = get_secret_json(secret_id)
    payload.update(updates)
    put_secret_json(secret_id, payload)
    return payload


def load_tokens_from_secret(secret_id: str) -> QBOTokens | None:
    from meshflow.qbo.token_store import QBOTokens

    payload = get_secret_json(secret_id)
    refresh_token = str(payload.get("refresh_token", "")).strip()
    realm_id = str(payload.get("realm_id", "")).strip()
    if not refresh_token or not realm_id:
        return None

    return QBOTokens(
        access_token=str(payload.get("access_token", "")).strip(),
        refresh_token=refresh_token,
        realm_id=realm_id,
        token_type=str(payload.get("token_type", "bearer")).strip() or "bearer",
        expires_in=payload.get("expires_in"),
        updated_at=payload.get("updated_at"),
    )


def save_tokens_to_secret(secret_id: str, tokens: QBOTokens) -> None:
    tokens.touch()
    merge_secret_json(
        secret_id,
        {
            "access_token": tokens.access_token,
            "refresh_token": tokens.refresh_token,
            "realm_id": tokens.realm_id,
            "token_type": tokens.token_type,
            "expires_in": tokens.expires_in,
            "updated_at": tokens.updated_at,
        },
    )
