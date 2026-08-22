"""Coverage for HIVEFLOW_UI_MODE=global (GlobalUiStack) — marketing + shared login hub.

Before this file, ui_mode="global" had zero test coverage anywhere in the suite,
despite being the mode with the trickiest branch: the external-redirect handoff
from the shared login hub to a client's per-client reporting subdomain.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from werkzeug.test import Client

from hiveflow.dna.settings import DnaSettings
from hiveflow.dna.web.app import create_app
from hiveflow.dna.web.portal.auth import PortalSession, create_session_token
from hiveflow.project_config import load_project_config


def _global_client(tmp_path: Path) -> Client:
    settings = DnaSettings(source="dbc", data_dir=tmp_path, pack_id="bc_intra_v1")
    config = load_project_config()
    try:
        from hiveflow.project_config import get_platform_environment_config

        env_config = get_platform_environment_config("dev")
    except KeyError:
        env_config = config["companies"]["poc"]["environments"]["dev"]
    return Client(
        create_app(
            settings,
            company="POC",
            environment="dev",
            env_config=env_config,
            ui_mode="global",
        )
    )


def _set_session_cookie(client: Client, *, username: str, client_id: str, secret: str) -> None:
    token = create_session_token(
        PortalSession(username=username, client_id=client_id, issued_at=int(time.time())),
        company="POC",
        environment="dev",
    )
    client.set_cookie("hiveflow_portal_session", token)


def test_global_landing_platform_pricing(tmp_path: Path) -> None:
    client = _global_client(tmp_path)

    home = client.get("/")
    assert home.status_code == 200
    assert b"HiveFlowAI" in home.data
    assert b"DMaaS" in home.data

    platform = client.get("/platform")
    assert platform.status_code == 200

    pricing = client.get("/pricing")
    assert pricing.status_code == 200
    assert b"$100" in pricing.data


def test_global_portal_home_requires_login(tmp_path: Path) -> None:
    client = _global_client(tmp_path)
    response = client.get("/portal")
    assert response.status_code == 302
    assert "/portal/login" in response.headers["Location"]


def test_global_portal_login_form_renders_with_client_id_hint(tmp_path: Path) -> None:
    client = _global_client(tmp_path)
    response = client.get("/portal/login?client_id=poc")
    assert response.status_code == 200
    assert b"Client portal" in response.data
    assert b'id="client_id"' in response.data
    assert b'value="poc"' in response.data


def test_global_authenticated_portal_home_redirects_to_client_reporting_site(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HIVEFLOW_PORTAL_COOKIE_DOMAIN", ".hive-flow-ai.com")
    monkeypatch.setenv("HIVEFLOW_PORTAL_SESSION_SECRET", "test-global-mode-secret")
    client = _global_client(tmp_path)
    _set_session_cookie(client, username="poc", client_id="poc", secret="test-global-mode-secret")

    response = client.get("/portal")
    assert response.status_code == 302
    assert response.headers["Location"] == "https://poc.hive-flow-ai.com/portal"


def test_global_authenticated_portal_login_redirects_externally_with_next_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HIVEFLOW_PORTAL_COOKIE_DOMAIN", ".hive-flow-ai.com")
    monkeypatch.setenv("HIVEFLOW_PORTAL_SESSION_SECRET", "test-global-mode-secret")
    client = _global_client(tmp_path)
    _set_session_cookie(client, username="poc", client_id="poc", secret="test-global-mode-secret")

    response = client.get("/portal/login?next=/portal/executive")
    assert response.status_code == 302
    assert response.headers["Location"] == "https://poc.hive-flow-ai.com/portal/executive"


def test_global_authenticated_portal_home_without_cookie_domain_returns_503(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("HIVEFLOW_PORTAL_COOKIE_DOMAIN", raising=False)
    monkeypatch.setenv("HIVEFLOW_PORTAL_SESSION_SECRET", "test-global-mode-secret")
    client = _global_client(tmp_path)
    _set_session_cookie(client, username="poc", client_id="poc", secret="test-global-mode-secret")

    response = client.get("/portal")
    assert response.status_code == 503
