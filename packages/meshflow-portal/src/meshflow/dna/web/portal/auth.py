from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from typing import Any

from werkzeug.wrappers import Request, Response

SESSION_COOKIE = "hiveflow_portal_session"
SESSION_MAX_AGE_SECONDS = 60 * 60 * 12

_SESSION_SECRET_CACHE: str | None = None


def session_cookie_name() -> str:
    """Cookie name — admin mode uses a separate name to avoid clashing with portal."""
    override = os.getenv("HIVEFLOW_SESSION_COOKIE", "").strip()
    return override or SESSION_COOKIE


def _load_secret_from_arn(secret_arn: str) -> str:
    import boto3

    client = boto3.client("secretsmanager")
    response = client.get_secret_value(SecretId=secret_arn)
    return str(response.get("SecretString", "")).strip()


def _session_secret(company: str, environment: str) -> str:
    global _SESSION_SECRET_CACHE  # noqa: PLW0603 — Lambda container reuse
    if _SESSION_SECRET_CACHE:
        return _SESSION_SECRET_CACHE

    configured = os.getenv("HIVEFLOW_PORTAL_SESSION_SECRET", "").strip()
    if configured:
        _SESSION_SECRET_CACHE = configured
        return configured

    secret_arn = os.getenv("HIVEFLOW_PORTAL_SESSION_SECRET_ARN", "").strip()
    if secret_arn:
        _SESSION_SECRET_CACHE = _load_secret_from_arn(secret_arn)
        if _SESSION_SECRET_CACHE:
            return _SESSION_SECRET_CACHE

    seed = f"{company}:{environment}:hiveflow-portal"
    _SESSION_SECRET_CACHE = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return _SESSION_SECRET_CACHE


@dataclass(frozen=True)
class PortalUser:
    username: str
    client_id: str
    password: str = ""


@dataclass(frozen=True)
class PortalSession:
    username: str
    client_id: str
    issued_at: int


def _sign_payload(payload: str, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def create_session_token(session: PortalSession, *, company: str, environment: str) -> str:
    body = json.dumps(
        {
            "username": session.username,
            "client_id": session.client_id,
            "issued_at": session.issued_at,
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    signature = _sign_payload(body, _session_secret(company, environment))
    return f"{body}.{signature}"


def read_session_token(token: str, *, company: str, environment: str) -> PortalSession | None:
    if not token or "." not in token:
        return None
    body, signature = token.rsplit(".", 1)
    expected = _sign_payload(body, _session_secret(company, environment))
    if not hmac.compare_digest(signature, expected):
        return None
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None

    issued_at = int(payload.get("issued_at", 0))
    if issued_at <= 0 or time.time() - issued_at > SESSION_MAX_AGE_SECONDS:
        return None

    username = str(payload.get("username", "")).strip()
    client_id = str(payload.get("client_id", "")).strip()
    if not username or not client_id:
        return None
    return PortalSession(username=username, client_id=client_id, issued_at=issued_at)


def session_from_request(request: Request, *, company: str, environment: str) -> PortalSession | None:
    token = request.cookies.get(session_cookie_name(), "")
    return read_session_token(token, company=company, environment=environment)


def set_session_cookie(response: Response, token: str) -> None:
    cookie_kwargs: dict[str, Any] = {
        "max_age": SESSION_MAX_AGE_SECONDS,
        "httponly": True,
        "samesite": "Lax",
        "secure": os.getenv("HIVEFLOW_PORTAL_COOKIE_SECURE", "").strip().lower() in {"1", "true", "yes"},
        "path": "/",
    }
    cookie_domain = os.getenv("HIVEFLOW_PORTAL_COOKIE_DOMAIN", "").strip()
    if cookie_domain:
        cookie_kwargs["domain"] = cookie_domain
    response.set_cookie(session_cookie_name(), token, **cookie_kwargs)


def clear_session_cookie(response: Response) -> None:
    name = session_cookie_name()
    cookie_domain = os.getenv("HIVEFLOW_PORTAL_COOKIE_DOMAIN", "").strip()
    if cookie_domain:
        response.delete_cookie(name, path="/", domain=cookie_domain)
    else:
        response.delete_cookie(name, path="/")
    # Also drop a colliding portal cookie on shared parent domains (admin host-only mode).
    if name != SESSION_COOKIE and not cookie_domain:
        response.delete_cookie(SESSION_COOKIE, path="/")
        response.delete_cookie(SESSION_COOKIE, path="/", domain=".hive-flow-ai.com")


def load_portal_users(*, company: str, environment: str) -> dict[str, PortalUser]:
    users: dict[str, PortalUser] = {}

    raw_users = os.getenv("HIVEFLOW_PORTAL_USERS", "").strip()
    if raw_users:
        payload = json.loads(raw_users)
        if isinstance(payload, list):
            for item in payload:
                if not isinstance(item, dict):
                    continue
                username = str(item.get("username", "")).strip().lower()
                password = str(item.get("password", ""))
                client_id = str(item.get("client_id", username)).strip().lower()
                if username and password:
                    users[username] = PortalUser(username=username, password=password, client_id=client_id)

    username = os.getenv("HIVEFLOW_PORTAL_USERNAME", "").strip().lower()
    password = os.getenv("HIVEFLOW_PORTAL_PASSWORD", "")
    client_id = os.getenv("HIVEFLOW_PORTAL_CLIENT_ID", company).strip().lower() or company.lower()
    if username and password:
        users[username] = PortalUser(username=username, password=password, client_id=client_id)

    secrets_path = os.getenv("HIVEFLOW_PORTAL_SECRETS_PATH", "").strip()
    if not secrets_path:
        from meshflow.project_config import PROJECT_ROOT

        candidate = PROJECT_ROOT / "secrets" / f"{company.lower()}-portal-{environment.lower()}.yaml"
        if candidate.is_file():
            secrets_path = str(candidate)

    if secrets_path:
        import yaml

        with open(secrets_path, encoding="utf-8") as handle:
            payload = yaml.safe_load(handle) or {}
        if isinstance(payload, dict):
            portal_users = payload.get("portal_users", payload.get("PORTAL_USERS", []))
            if isinstance(portal_users, list):
                for item in portal_users:
                    if not isinstance(item, dict):
                        continue
                    entry_username = str(item.get("username", "")).strip().lower()
                    entry_password = str(item.get("password", ""))
                    entry_client = str(item.get("client_id", entry_username)).strip().lower()
                    if entry_username and entry_password:
                        users[entry_username] = PortalUser(
                            username=entry_username,
                            password=entry_password,
                            client_id=entry_client,
                        )

    secret_name = os.getenv("HIVEFLOW_PORTAL_SECRET_NAME", "").strip()
    if secret_name:
        import json as json_module

        import boto3

        client = boto3.client("secretsmanager")
        response = client.get_secret_value(SecretId=secret_name)
        raw_secret = response.get("SecretString", "")
        payload = json_module.loads(raw_secret) if raw_secret else {}
        if isinstance(payload, dict):
            portal_users = payload.get("portal_users", payload.get("PORTAL_USERS", []))
            if isinstance(portal_users, list):
                for item in portal_users:
                    if not isinstance(item, dict):
                        continue
                    entry_username = str(item.get("username", "")).strip().lower()
                    entry_password = str(item.get("password", ""))
                    entry_client = str(item.get("client_id", entry_username)).strip().lower()
                    if entry_username and entry_password:
                        users[entry_username] = PortalUser(
                            username=entry_username,
                            password=entry_password,
                            client_id=entry_client,
                        )

    return users


def authenticate(
    username: str,
    password: str,
    *,
    company: str,
    environment: str,
) -> PortalUser | None:
    from meshflow.dna.web.portal.cognito import authenticate_with_cognito, cognito_configured

    if cognito_configured():
        result = authenticate_with_cognito(
            username,
            password,
            company=company,
            environment=environment,
        )
        if result is None or result.kind != "authenticated" or result.user is None:
            return None
        return result.user

    normalized = username.strip().lower()
    users = load_portal_users(company=company, environment=environment)
    user = users.get(normalized)
    if user is None:
        return None
    if not hmac.compare_digest(user.password, password):
        return None
    return PortalUser(username=user.username, client_id=user.client_id)


def login_response(
    user: PortalUser,
    *,
    company: str,
    environment: str,
    redirect_to: str,
) -> Response:
    token = create_session_token(
        PortalSession(username=user.username, client_id=user.client_id, issued_at=int(time.time())),
        company=company,
        environment=environment,
    )
    response = Response(status=302, headers={"Location": redirect_to})
    set_session_cookie(response, token)
    return response


def require_portal_session(
    request: Request,
    *,
    company: str,
    environment: str,
    login_url: str,
) -> tuple[PortalSession | None, Response | None]:
    session = session_from_request(request, company=company, environment=environment)
    if session is None:
        next_path = request.full_path if request.query_string else request.path
        location = f"{login_url}?next={next_path}" if next_path and next_path != "?" else login_url
        return None, Response(status=302, headers={"Location": location})
    return session, None


def require_portal_admin(
    username: str,
    *,
    company: str,
    environment: str,
) -> bool:
    from meshflow.dna.web.portal.cognito import portal_user_is_admin

    return portal_user_is_admin(username, company=company, environment=environment)
