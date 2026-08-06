"""Admin-only config proposal preview cookie helpers."""

from __future__ import annotations

import os
from typing import Any

from werkzeug.wrappers import Request, Response

PREVIEW_COOKIE = "meshflow_config_preview"


def preview_proposal_id(request: Request) -> str | None:
    value = (request.cookies.get(PREVIEW_COOKIE) or "").strip().lower()
    return value or None


def set_preview_cookie(response: Response, proposal_id: str) -> None:
    kwargs: dict[str, Any] = {
        "path": "/",
        "httponly": True,
        "samesite": "Lax",
        "max_age": 60 * 60 * 8,
        "secure": os.getenv("HIVEFLOW_PORTAL_COOKIE_SECURE", "").strip().lower()
        in {"1", "true", "yes"},
    }
    domain = os.getenv("HIVEFLOW_PORTAL_COOKIE_DOMAIN", "").strip()
    if domain:
        kwargs["domain"] = domain
    response.set_cookie(PREVIEW_COOKIE, proposal_id.strip().lower(), **kwargs)


def clear_preview_cookie(response: Response) -> None:
    domain = os.getenv("HIVEFLOW_PORTAL_COOKIE_DOMAIN", "").strip()
    if domain:
        response.delete_cookie(PREVIEW_COOKIE, path="/", domain=domain)
    else:
        response.delete_cookie(PREVIEW_COOKIE, path="/")
