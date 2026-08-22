"""Generic Cognito plumbing shared by admin/ and portal/ — neither imports the other.

Extracted from portal/cognito.py during the Phase 2 auth-coupling cleanup:
these functions are generic Cognito SDK helpers (build a client, look up a
user tolerant of case, flatten/build UserAttributes), not portal-specific
business logic, so both admin and portal depend on them from here instead of
admin reaching into portal's private internals.
"""

from __future__ import annotations

from typing import Any

ADMIN_GROUP_NAME = "PlatformAdmins"


def cognito_client(region: str):
    import boto3

    return boto3.client("cognito-idp", region_name=region)


def attribute_map(attributes: list[dict[str, str]] | None) -> dict[str, str]:
    mapped: dict[str, str] = {}
    for entry in attributes or []:
        name = str(entry.get("Name", "")).strip()
        value = str(entry.get("Value", "")).strip()
        if name:
            mapped[name] = value
    return mapped


def admin_get_user(
    client: Any,
    *,
    user_pool_id: str,
    username: str,
) -> dict[str, Any] | None:
    """Fetch a Cognito user, tolerating case-sensitive username mismatches."""
    normalized = username.strip()
    if not normalized:
        return None
    try:
        return client.admin_get_user(UserPoolId=user_pool_id, Username=normalized)
    except client.exceptions.UserNotFoundException:
        pass

    needle = normalized.casefold()
    paginator = client.get_paginator("list_users")
    for page in paginator.paginate(UserPoolId=user_pool_id):
        for entry in page.get("Users", []):
            candidate = str(entry.get("Username", "")).strip()
            attributes = attribute_map(entry.get("Attributes"))
            email = attributes.get("email", "").strip()
            if candidate.casefold() == needle or email.casefold() == needle:
                try:
                    return client.admin_get_user(UserPoolId=user_pool_id, Username=candidate)
                except client.exceptions.UserNotFoundException:
                    return None
    return None


def build_user_attributes(
    *,
    client_id: str,
    email: str = "",
    role: str = "member",
) -> list[dict[str, str]]:
    attributes = [
        {"Name": "custom:client_id", "Value": client_id.strip().lower()},
        {"Name": "custom:portal_role", "Value": role},
    ]
    if email.strip():
        attributes.extend(
            [
                {"Name": "email", "Value": email.strip()},
                {"Name": "email_verified", "Value": "true"},
            ]
        )
    return attributes


def admin_username_allowlist() -> str:
    import os

    return os.getenv("MESHFLOW_ADMIN_USERNAME", "GlobalAdmin").strip() or "GlobalAdmin"


def is_allowed_admin_username(username: str) -> bool:
    allowed = admin_username_allowlist()
    return bool(username) and username.strip() == allowed


def is_admin_group_member(username: str, *, user_pool_id: str, region: str) -> bool:
    """Check membership in ADMIN_GROUP_NAME within the given Cognito pool."""
    normalized = username.strip()
    if not normalized or not user_pool_id.strip():
        return False
    try:
        client = cognito_client(region)
        response = client.admin_list_groups_for_user(
            Username=normalized,
            UserPoolId=user_pool_id.strip(),
        )
    except Exception:  # noqa: BLE001 — treat Cognito lookup failures as non-admin
        return False
    groups = response.get("Groups") or []
    return any(str(group.get("GroupName", "")).strip() == ADMIN_GROUP_NAME for group in groups)
