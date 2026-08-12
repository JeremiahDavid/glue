"""Platform admin Cognito helpers (separate pool from client portal)."""

from __future__ import annotations

import os
from typing import Any

from meshflow.dna.web.portal.auth import PortalUser
from meshflow.dna.web.portal.cognito import (
    NEW_PASSWORD_CHALLENGE,
    CognitoConfig,
    NewPasswordChallenge,
    PortalLoginResult,
    PortalUserAlreadyExists,
    _admin_get_user,
    _attribute_map,
    _cognito_client,
    authenticate_with_cognito,
    complete_new_password_challenge,
    load_cognito_config,
)


def admin_username_allowlist() -> str:
    return os.getenv("MESHFLOW_ADMIN_USERNAME", "GlobalAdmin").strip() or "GlobalAdmin"


def is_allowed_admin_username(username: str) -> bool:
    allowed = admin_username_allowlist()
    return bool(username) and username.strip() == allowed


def authenticate_admin(
    username: str,
    password: str,
    *,
    company: str,
    environment: str,
) -> PortalLoginResult | None:
    """Authenticate against the admin Cognito pool; reject non-allowlisted usernames."""
    result = authenticate_with_cognito(
        username,
        password,
        company=company,
        environment=environment,
    )
    if result is None:
        return None
    if result.kind == "new_password" and result.challenge is not None:
        # Allow challenge to proceed; final username is checked after password set.
        # If the typed identifier was email, Cognito still returns the pool username later.
        return result
    if result.kind == "authenticated" and result.user is not None:
        if not is_allowed_admin_username(result.user.username):
            return None
        return PortalLoginResult(
            kind="authenticated",
            user=PortalUser(username=result.user.username, client_id="platform"),
        )
    return None


def complete_admin_new_password(
    *,
    username: str,
    session: str,
    new_password: str,
    company: str,
    environment: str,
) -> PortalUser | None:
    user = complete_new_password_challenge(
        username=username,
        session=session,
        new_password=new_password,
        company=company,
        environment=environment,
    )
    if user is None or not is_allowed_admin_username(user.username):
        return None
    return PortalUser(username=user.username, client_id="platform")


def _user_email(user_payload: dict[str, Any]) -> str:
    attrs = _attribute_map(user_payload.get("UserAttributes"))
    return str(attrs.get("email") or "").strip()


def bootstrap_global_admin(
    *,
    portal_user_pool_id: str,
    admin_user_pool_id: str,
    portal_username: str = "AdminPOC",
    admin_username: str | None = None,
    region: str | None = None,
    temporary_password: str | None = None,
) -> dict[str, Any]:
    """Copy AdminPOC email from the portal pool and create GlobalAdmin in the admin pool."""
    region_name = (
        (region or "").strip()
        or os.getenv("AWS_REGION", "").strip()
        or os.getenv("AWS_DEFAULT_REGION", "").strip()
        or "us-east-2"
    )
    target_username = (admin_username or admin_username_allowlist()).strip()
    client = _cognito_client(region_name)

    portal_user = _admin_get_user(
        client,
        user_pool_id=portal_user_pool_id.strip(),
        username=portal_username.strip(),
    )
    if portal_user is None:
        raise RuntimeError(f"Portal user {portal_username!r} not found in {portal_user_pool_id}")

    email = _user_email(portal_user)
    if not email:
        raise RuntimeError(f"Portal user {portal_username!r} has no email attribute")

    existing = _admin_get_user(
        client,
        user_pool_id=admin_user_pool_id.strip(),
        username=target_username,
    )
    if existing is not None:
        return {
            "status": "exists",
            "username": target_username,
            "email": email,
            "admin_user_pool_id": admin_user_pool_id,
            "source_portal_user": portal_username,
        }

    create_kwargs: dict[str, Any] = {
        "UserPoolId": admin_user_pool_id.strip(),
        "Username": target_username,
        "UserAttributes": [
            {"Name": "email", "Value": email},
            {"Name": "email_verified", "Value": "true"},
        ],
    }
    if temporary_password:
        create_kwargs["TemporaryPassword"] = temporary_password
        create_kwargs["MessageAction"] = "SUPPRESS"
    try:
        response = client.admin_create_user(**create_kwargs)
    except client.exceptions.UsernameExistsException as exc:
        raise PortalUserAlreadyExists(f"User {target_username!r} already exists.") from exc

    return {
        "status": "created",
        "username": target_username,
        "email": email,
        "admin_user_pool_id": admin_user_pool_id,
        "source_portal_user": portal_username,
        "user_status": response.get("User", {}).get("UserStatus", "UNKNOWN"),
        "delivery": "invite_email" if not temporary_password else "temporary_suppressed",
    }


# Re-export for typing convenience in views/tests
__all__ = [
    "CognitoConfig",
    "NewPasswordChallenge",
    "NEW_PASSWORD_CHALLENGE",
    "PortalLoginResult",
    "admin_username_allowlist",
    "authenticate_admin",
    "bootstrap_global_admin",
    "complete_admin_new_password",
    "is_allowed_admin_username",
    "load_cognito_config",
]
