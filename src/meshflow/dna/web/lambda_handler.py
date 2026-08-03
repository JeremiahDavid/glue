from __future__ import annotations

import os
from typing import Any

from meshflow.dna.runtime import resolve_dna_settings
from meshflow.dna.web.app import create_app
from meshflow.dna.web.theme import BINARY_STATIC_CONTENT_TYPES

_wsgi_app = None


def _get_wsgi_app():
    global _wsgi_app  # noqa: PLW0603 — Lambda container reuse
    if _wsgi_app is None:
        from meshflow.project_config import (
            get_environment_config,
            get_platform_environment_config,
            resolve_selection,
        )

        company, environment = resolve_selection()
        try:
            env_config = get_platform_environment_config(environment)
        except KeyError:
            env_config = get_environment_config(company, environment)

        _wsgi_app = create_app(
            resolve_dna_settings(),
            company=company,
            environment=environment,
            env_config=env_config,
            ui_mode=os.getenv("MESHFLOW_UI_MODE"),
        )
    return _wsgi_app


def ui_handler(event: dict[str, Any] | None, context: Any) -> dict[str, Any]:
    """Lambda entry point for the DNA reporting web UI (API Gateway proxy)."""
    try:
        import awsgi
    except ImportError as exc:
        raise RuntimeError(
            "aws-wsgi is required for the DNA UI Lambda. Install meshflow with dependencies."
        ) from exc

    return awsgi.response(
        _get_wsgi_app(),
        event,
        context,
        base64_content_types=BINARY_STATIC_CONTENT_TYPES,
    )
