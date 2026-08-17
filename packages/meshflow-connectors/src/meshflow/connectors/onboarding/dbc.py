"""Business Central credential validation for onboarding."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from meshflow.config import BCSettings

_DBC_LOOKUP_FIELDS = ("BC_CLIENT_ID", "BC_CLIENT_SECRET", "BC_TENANT_ID", "BC_ENVIRONMENT_NAME")
_DBC_VALIDATE_FIELDS = _DBC_LOOKUP_FIELDS + ("BC_COMPANY_ID",)


def _dbc_settings(credentials: dict[str, str], *, company_id: str) -> BCSettings:
    return BCSettings(
        client_id=str(credentials["BC_CLIENT_ID"]).strip(),
        client_secret=str(credentials["BC_CLIENT_SECRET"]).strip(),
        tenant_id=str(credentials["BC_TENANT_ID"]).strip(),
        environment_name=str(credentials["BC_ENVIRONMENT_NAME"]).strip(),
        company_id=company_id,
        data_dir=Path("."),
        environment=str(credentials.get("BC_ENVIRONMENT", "production")).strip() or "production",
    )


def _missing_fields(credentials: dict[str, str], required: tuple[str, ...]) -> list[str]:
    return [key for key in required if not str(credentials.get(key, "")).strip()]


def list_dbc_companies(credentials: dict[str, str]) -> dict[str, Any]:
    """List BC companies after Entra app credentials and environment name are provided."""
    missing = _missing_fields(credentials, _DBC_LOOKUP_FIELDS)
    if missing:
        return {"ok": False, "error": f"Missing required fields: {', '.join(missing)}"}

    from meshflow.bc.auth import acquire_client_credentials_token
    from meshflow.bc.client import BCClient

    settings = _dbc_settings(credentials, company_id="00000000-0000-0000-0000-000000000001")

    try:
        # Onboarding credentials are not stored yet; do not persist tokens to Secrets Manager.
        tokens = acquire_client_credentials_token(settings)
        client = BCClient(settings, tokens)
        companies = client.list_companies()
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

    if not companies:
        return {"ok": False, "error": "No companies returned for this tenant and environment."}

    return {"ok": True, "companies": companies}


def validate_dbc_credentials(credentials: dict[str, str]) -> dict[str, Any]:
    """Smoke-test BC OData access with the provided secret fields."""
    from meshflow.bc.auth import acquire_client_credentials_token
    from meshflow.bc.client import BCClient

    missing = _missing_fields(credentials, _DBC_VALIDATE_FIELDS)
    if missing:
        return {"ok": False, "error": f"Missing required fields: {', '.join(missing)}"}

    settings = _dbc_settings(credentials, company_id=str(credentials["BC_COMPANY_ID"]).strip())

    try:
        tokens = acquire_client_credentials_token(settings)
        client = BCClient(settings, tokens)
        company = client.company()
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

    return {
        "ok": True,
        "company_name": str(company.get("displayName") or company.get("name") or ""),
        "company_id": str(company.get("id") or settings.company_id),
    }
