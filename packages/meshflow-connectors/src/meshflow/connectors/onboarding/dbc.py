"""Business Central credential validation for onboarding."""

from __future__ import annotations

from typing import Any


def validate_dbc_credentials(credentials: dict[str, str]) -> dict[str, Any]:
    """Smoke-test BC OData access with the provided secret fields."""
    from meshflow.bc.auth import ensure_access_token
    from meshflow.bc.client import BCClient
    from meshflow.config import BCSettings

    required = ("BC_CLIENT_ID", "BC_CLIENT_SECRET", "BC_TENANT_ID", "BC_ENVIRONMENT_NAME", "BC_COMPANY_ID")
    missing = [key for key in required if not str(credentials.get(key, "")).strip()]
    if missing:
        return {"ok": False, "error": f"Missing required fields: {', '.join(missing)}"}

    from pathlib import Path

    settings = BCSettings(
        client_id=str(credentials["BC_CLIENT_ID"]).strip(),
        client_secret=str(credentials["BC_CLIENT_SECRET"]).strip(),
        tenant_id=str(credentials["BC_TENANT_ID"]).strip(),
        environment_name=str(credentials["BC_ENVIRONMENT_NAME"]).strip(),
        company_id=str(credentials["BC_COMPANY_ID"]).strip(),
        data_dir=Path("."),
        environment=str(credentials.get("BC_ENVIRONMENT", "production")).strip() or "production",
    )

    try:
        tokens = ensure_access_token(settings, None)
        client = BCClient(settings, tokens)
        company = client.company()
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

    return {
        "ok": True,
        "company_name": str(company.get("displayName") or company.get("name") or ""),
        "company_id": str(company.get("id") or settings.company_id),
    }
