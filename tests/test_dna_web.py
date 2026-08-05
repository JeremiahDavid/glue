from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from werkzeug.test import Client

from meshflow.dna.settings import DnaSettings
from meshflow.dna.web.app import REVENUE_TABLE_LIMIT, _sanitize_portal_next, create_app
from meshflow.dna.web.portal.views import aggregate_revenue_by_month
from meshflow.project_config import get_environment_config, load_project_config


@pytest.fixture
def portal_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HIVEFLOW_PORTAL_USERNAME", "poc")
    monkeypatch.setenv("HIVEFLOW_PORTAL_PASSWORD", "changeme")
    monkeypatch.setenv("HIVEFLOW_PORTAL_CLIENT_ID", "poc")


@pytest.fixture
def cognito_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HIVEFLOW_COGNITO_USER_POOL_ID", "us-east-2_TestPool")
    monkeypatch.setenv("HIVEFLOW_COGNITO_CLIENT_ID", "testclient")
    monkeypatch.setenv("HIVEFLOW_COGNITO_REGION", "us-east-2")
    monkeypatch.setenv("HIVEFLOW_PORTAL_DEFAULT_CLIENT_ID", "poc")
    monkeypatch.delenv("HIVEFLOW_PORTAL_USERNAME", raising=False)
    monkeypatch.delenv("HIVEFLOW_PORTAL_PASSWORD", raising=False)


def _client(tmp_path: Path) -> Client:
    settings = DnaSettings(source="dbc", data_dir=tmp_path, pack_id="bc_intra_v1")
    config = load_project_config()
    try:
        from meshflow.project_config import get_platform_environment_config

        env_config = get_platform_environment_config("dev")
    except KeyError:
        env_config = config["companies"]["POC"]["environments"]["dev"]
    return Client(create_app(settings, company="POC", environment="dev", env_config=env_config))


def test_public_landing_and_pricing(tmp_path: Path) -> None:
    client = _client(tmp_path)

    home = client.get("/")
    assert home.status_code == 200
    assert b"Hive Flow" in home.data
    assert b"Reveal what matters" in home.data

    pricing = client.get("/pricing")
    assert pricing.status_code == 200
    assert b"$100" in pricing.data
    assert b"$5,000" in pricing.data


def test_portal_requires_login(tmp_path: Path, portal_env: None) -> None:
    client = _client(tmp_path)
    response = client.get("/portal")
    assert response.status_code == 302
    assert "/portal/login" in response.headers["Location"]


def test_portal_login_and_overview(tmp_path: Path, portal_env: None) -> None:
    client = _client(tmp_path)
    login = client.post(
        "/portal/login",
        data={"username": "poc", "password": "changeme", "next": "/portal"},
    )
    assert login.status_code == 302
    assert login.headers["Location"].endswith("/portal")

    overview = client.get("/portal")
    assert overview.status_code == 200
    assert b"POC Distribution Co." in overview.data
    assert b"Executive snapshot" in overview.data


def test_portal_governance_after_login(tmp_path: Path, portal_env: None) -> None:
    client = _client(tmp_path)
    client.post("/portal/login", data={"username": "poc", "password": "changeme"})

    governance = client.get("/portal/governance")
    assert governance.status_code == 200
    assert b"Pack Registry" in governance.data
    assert b"poc_dna_config" in governance.data or b"poc_reporting_config" in governance.data
    assert b"Reporting layout pack" in governance.data
    assert b"Config Portal" in governance.data or b"Users" in governance.data

    legacy = client.get("/portal/semantics")
    assert legacy.status_code == 302
    assert legacy.headers["Location"].endswith("/portal/governance")


def test_portal_nav_data_dropdown_and_governance(tmp_path: Path, portal_env: None) -> None:
    client = _client(tmp_path)
    client.post("/portal/login", data={"username": "poc", "password": "changeme"})

    overview = client.get("/portal")
    assert overview.status_code == 200
    assert b"nav-dropdown-panel" in overview.data
    assert b">Data</a>" in overview.data
    assert b"nav-dropdown-panel" in overview.data
    assert b"Executive KPIs" in overview.data
    assert b"Revenue trend" in overview.data
    assert b">Governance</a>" in overview.data
    assert b">Executive</a>" not in overview.data
    assert b">Trend</a>" not in overview.data


def test_api_gateway_stage_prefix(tmp_path: Path, portal_env: None) -> None:
    client = _client(tmp_path)

    response = client.get("/", environ_overrides={"SCRIPT_NAME": "/prod"})
    assert response.status_code == 200
    assert b'href="/prod/pricing"' in response.data
    assert b'src="/prod/static/hiveflowai-symbol.png"' in response.data

    client.post(
        "/portal/login",
        data={"username": "poc", "password": "changeme"},
        environ_overrides={"SCRIPT_NAME": "/prod"},
    )
    executive = client.get("/portal/executive", environ_overrides={"SCRIPT_NAME": "/prod"})
    assert executive.status_code == 200
    assert b"nav-dropdown-panel" in executive.data
    assert b"Executive KPIs" in executive.data


def test_execute_api_host_infers_stage_prefix(tmp_path: Path) -> None:
    client = _client(tmp_path)
    overrides = {
        "PATH_INFO": "/",
        "SCRIPT_NAME": "",
        "HTTP_HOST": "ao4eqbwn1l.execute-api.us-east-2.amazonaws.com",
        "awsgi.event": {"requestContext": {"stage": "prod"}},
    }
    response = client.get("/", environ_overrides=overrides)
    assert response.status_code == 200
    assert b'href="/prod/pricing"' in response.data

    pricing = client.get("/pricing", environ_overrides=overrides)
    assert pricing.status_code == 200


def test_custom_domain_does_not_add_stage_prefix(tmp_path: Path) -> None:
    client = _client(tmp_path)
    response = client.get(
        "/",
        environ_overrides={
            "PATH_INFO": "/",
            "SCRIPT_NAME": "",
            "HTTP_HOST": "hive-flow-ai.com",
            "awsgi.event": {"requestContext": {"stage": "prod"}},
        },
    )
    assert response.status_code == 200
    assert b'href="/pricing"' in response.data
    assert b'href="/prod/pricing"' not in response.data


def test_strips_stage_prefix_from_path_info(tmp_path: Path) -> None:
    client = _client(tmp_path)
    response = client.get(
        "/",
        environ_overrides={
            "PATH_INFO": "/prod/pricing",
            "SCRIPT_NAME": "",
            "HTTP_HOST": "ao4eqbwn1l.execute-api.us-east-2.amazonaws.com",
            "awsgi.event": {"requestContext": {"stage": "prod"}},
        },
    )
    assert response.status_code == 200
    assert b"HiveFlowAI" in response.data or b"Hive Flow" in response.data


def test_static_serves_symbol(tmp_path: Path) -> None:
    client = _client(tmp_path)
    static = client.get("/static/hiveflowai-symbol.png")
    assert static.status_code == 200
    assert static.mimetype == "image/png"
    assert len(static.data) > 1000


def test_awsgi_encodes_png_for_api_gateway(tmp_path: Path) -> None:
    import base64

    import awsgi

    from meshflow.dna.web.theme import BINARY_STATIC_CONTENT_TYPES

    settings = DnaSettings(source="dbc", data_dir=tmp_path, pack_id="bc_intra_v1")
    config = load_project_config()
    env_config = config["companies"]["POC"]["environments"]["dev"]
    app = create_app(settings, company="POC", environment="dev", env_config=env_config)

    event = {
        "httpMethod": "GET",
        "path": "/static/hiveflowai-symbol.png",
        "headers": {"Accept": "image/png"},
        "queryStringParameters": None,
        "body": "",
        "isBase64Encoded": False,
        "requestContext": {"stage": "prod"},
    }
    result = awsgi.response(app, event, None, base64_content_types=BINARY_STATIC_CONTENT_TYPES)

    assert result["statusCode"] in (200, "200")
    assert result["isBase64Encoded"] is True
    assert result["headers"]["Content-Type"] == "image/png"
    decoded = base64.b64decode(result["body"])
    assert decoded[:8] == b"\x89PNG\r\n\x1a\n"


def test_static_serves_echarts_bundle(tmp_path: Path) -> None:
    client = _client(tmp_path)
    static = client.get("/static/echarts.min.js")
    assert static.status_code == 200
    assert static.mimetype == "application/javascript"
    assert b"echarts" in static.data.lower()


def test_branding_asset_from_s3(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HIVEFLOW_BRANDING_BUCKET", "hive-flow-ai-branding")
    monkeypatch.setenv("HIVEFLOW_BRANDING_SYMBOL_KEY", "HiveFlowAI Symbol.png")

    from meshflow.dna.web import branding

    branding._fetch_s3_object.cache_clear()

    def fake_fetch(bucket: str, key: str) -> bytes:
        assert bucket == "hive-flow-ai-branding"
        assert key == "HiveFlowAI Symbol.png"
        return b"fake-png-bytes"

    monkeypatch.setattr(branding, "_fetch_s3_object", fake_fetch)

    client = _client(tmp_path)
    static = client.get("/static/hiveflowai-symbol.png")
    assert static.status_code == 200
    assert static.data == b"fake-png-bytes"
    client = _client(tmp_path)
    pack = client.get("/api/pack")
    assert pack.status_code == 401


def test_web_app_api_endpoints(tmp_path: Path, portal_env: None) -> None:
    client = _client(tmp_path)
    client.post("/portal/login", data={"username": "poc", "password": "changeme"})

    pack = client.get("/api/pack")
    assert pack.status_code == 200
    assert pack.json["pack_id"] == "poc_dna_config"

    revenue = client.get("/api/revenue")
    assert revenue.status_code == 200
    assert revenue.json["output_id"] == "out_fact_revenue_lines"
    assert revenue.json["row_count"] == 0
    assert len(revenue.json["rows"]) <= REVENUE_TABLE_LIMIT

    trend = client.get("/api/revenue-trend")
    assert trend.status_code == 200
    assert trend.json["output_id"] == "out_fact_revenue_lines"
    assert trend.json["months"] == []


def test_aggregate_revenue_by_month() -> None:
    rows = [
        {"postingDate": "2026-01-15", "netAmount": 100.0},
        {"postingDate": "2026-01-20", "netAmount": 50.0},
        {"postingDate": "2026-02-01", "netAmount": 200.0},
        {"postingDate": "2025-11-01", "netAmount": 10.0},
    ]
    assert aggregate_revenue_by_month(rows, limit=0) == [
        ("2025-11", 10.0),
        ("2026-01", 150.0),
        ("2026-02", 200.0),
    ]
    assert aggregate_revenue_by_month(rows, limit=2) == [
        ("2026-01", 150.0),
        ("2026-02", 200.0),
    ]


def test_portal_revenue_trend_after_login(tmp_path: Path, portal_env: None) -> None:
    client = _client(tmp_path)
    client.post("/portal/login", data={"username": "poc", "password": "changeme"})

    trend = client.get("/portal/revenue-trend")
    assert trend.status_code == 200
    assert b"Revenue trend" in trend.data
    assert b"No revenue trend yet" in trend.data
    assert b"data-hive-chart" not in trend.data
    assert b"portal-charts.js" not in trend.data


def test_portal_revenue_trend_with_data_includes_echarts(tmp_path: Path, portal_env: None) -> None:
    from meshflow.ingest.storage import write_parquet_local

    client = _client(tmp_path)
    client.post("/portal/login", data={"username": "poc", "password": "changeme"})

    write_parquet_local(
        tmp_path / "gold" / "dna" / "out_fact_revenue_lines",
        "data.parquet",
        [
            {"postingDate": "2026-01-15", "netAmount": 100.0},
            {"postingDate": "2026-02-01", "netAmount": 200.0},
        ],
    )

    trend = client.get("/portal/revenue-trend")
    assert trend.status_code == 200
    assert b'data-hive-chart="' in trend.data
    assert b"portal-charts.js" in trend.data
    assert b"echarts.min.js" in trend.data
    assert b"Monthly posted revenue" in trend.data


def test_portal_chart_demo_after_login(tmp_path: Path, portal_env: None) -> None:
    client = _client(tmp_path)
    client.post("/portal/login", data={"username": "poc", "password": "changeme"})

    demo = client.get("/portal/chart-demo")
    assert demo.status_code == 200
    assert b"Chart catalog" in demo.data
    assert b"8 chart types" in demo.data
    assert b"Gold-backed demo" in demo.data
    assert demo.data.count(b"No gold data yet") == 8
    assert b"data-hive-chart=" not in demo.data
    assert b"portal-charts.js" not in demo.data


def test_portal_chart_demo_with_gold_data(tmp_path: Path, portal_env: None) -> None:
    from meshflow.ingest.storage import write_parquet_local

    client = _client(tmp_path)
    client.post("/portal/login", data={"username": "poc", "password": "changeme"})

    write_parquet_local(
        tmp_path / "gold" / "dna" / "out_fact_revenue_lines",
        "data.parquet",
        [
            {
                "postingDate": "2026-01-15",
                "netAmount": 100.0,
                "quantity": 2.0,
                "customerId": "c1",
                "customerName": "Acme",
                "itemId": "i1",
            },
            {
                "postingDate": "2026-02-01",
                "netAmount": 200.0,
                "quantity": 4.0,
                "customerId": "c1",
                "customerName": "Acme",
                "itemId": "i1",
            },
        ],
    )
    write_parquet_local(
        tmp_path / "gold" / "dna" / "out_dim_items",
        "data.parquet",
        [{"id": "i1", "displayName": "Widget A", "number": "W-A"}],
    )

    demo = client.get("/portal/chart-demo")
    assert demo.status_code == 200
    assert demo.data.count(b"data-hive-chart=") == 7
    assert b"No gold data yet" in demo.data
    assert b"portal-charts.js" in demo.data
    assert b"out_fact_revenue_lines" in demo.data
    assert b"Monthly posted revenue" in demo.data


def test_client_portal_config_from_yaml() -> None:
    from meshflow.dna.web.portal.config import load_client_portal_config
    from meshflow.project_config import get_platform_environment_config

    env_config = get_platform_environment_config("dev")
    client = load_client_portal_config("poc", env_config, default_pack_id="bc_intra_v1")
    assert client.display_name == "POC Distribution Co."
    assert client.pack_id == "bc_intra_v1"
    assert client.max_users == 10
    assert client.reporting_company == "POC"


def test_sanitize_portal_next_rewrites_reporting_login_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HIVEFLOW_PORTAL_COOKIE_DOMAIN", ".hive-flow-ai.com")
    assert (
        _sanitize_portal_next("https://poc.hive-flow-ai.com/portal/login", client_id="poc")
        == "/portal"
    )
    assert _sanitize_portal_next("/portal/login") == "/portal"


def test_brand_home_href_uses_primary_site_on_reporting(monkeypatch: pytest.MonkeyPatch) -> None:
    from meshflow.dna.web.theme import brand_home_href

    monkeypatch.setenv("HIVEFLOW_PRIMARY_SITE_URL", "https://hive-flow-ai.com")
    assert brand_home_href(lambda path: f"https://poc.hive-flow-ai.com{path}") == "https://hive-flow-ai.com/"


def test_portal_brand_links_to_summary() -> None:
    from types import SimpleNamespace

    from meshflow.dna.web.theme import render_portal_page

    html = render_portal_page(
        title="Summary",
        active_path="/portal",
        body="<p>ok</p>",
        nav_links=(),
        client=SimpleNamespace(display_name="POC Distribution Co.", accent_color=None),
        url=lambda path: path,
    )
    assert 'class="brand" href="/portal"' in html


def test_reporting_portal_login_redirects_to_global_with_relative_next(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HIVEFLOW_GLOBAL_LOGIN_URL", "https://hive-flow-ai.com/portal/login")
    monkeypatch.setenv("HIVEFLOW_PORTAL_COOKIE_DOMAIN", ".hive-flow-ai.com")
    settings = DnaSettings(source="dbc", data_dir=tmp_path, pack_id="bc_intra_v1")
    config = load_project_config()
    try:
        from meshflow.project_config import get_platform_environment_config

        env_config = get_platform_environment_config("dev")
    except KeyError:
        env_config = config["companies"]["POC"]["environments"]["dev"]
    client = Client(
        create_app(
            settings,
            company="POC",
            environment="dev",
            env_config=env_config,
            ui_mode="reporting",
        )
    )
    response = client.get("/portal/login")
    assert response.status_code == 302
    assert response.headers["Location"] == "https://hive-flow-ai.com/portal/login?next=%2Fportal"


def test_portal_admin_users_requires_login(tmp_path: Path, portal_env: None) -> None:
    client = _client(tmp_path)
    response = client.get("/portal/governance/users")
    assert response.status_code == 302
    assert "/portal/login" in response.headers["Location"]


def test_portal_admin_users_lists_legacy_users(tmp_path: Path, portal_env: None) -> None:
    client = _client(tmp_path)
    client.post("/portal/login", data={"username": "poc", "password": "changeme"})

    response = client.get("/portal/governance/users")
    assert response.status_code == 200
    assert b"Users" in response.data
    assert b"poc" in response.data
    assert b"1 of 10 seats used" in response.data
    assert b"Pack Registry" in response.data
    assert b"Config Portal" in response.data


def test_portal_admin_users_invite_post(tmp_path: Path, cognito_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    from unittest.mock import patch

    from meshflow.dna.web.portal.auth import PortalUser
    from meshflow.dna.web.portal.cognito import PortalLoginResult, PortalUserRecord

    monkeypatch.setenv("HIVEFLOW_PORTAL_USERNAME", "")
    monkeypatch.setenv("HIVEFLOW_PORTAL_PASSWORD", "")

    settings = DnaSettings(source="dbc", data_dir=tmp_path, pack_id="bc_intra_v1")
    config = load_project_config()
    try:
        from meshflow.project_config import get_platform_environment_config

        env_config = get_platform_environment_config("dev")
    except KeyError:
        env_config = config["companies"]["POC"]["environments"]["dev"]
    client = Client(create_app(settings, company="POC", environment="dev", env_config=env_config))

    with patch(
        "meshflow.dna.web.portal.cognito.authenticate_with_cognito",
        return_value=PortalLoginResult(
            kind="authenticated",
            user=PortalUser(username="poc", client_id="poc"),
        ),
    ), patch(
        "meshflow.dna.web.portal.cognito.portal_user_is_admin",
        return_value=True,
    ), patch(
        "meshflow.dna.web.portal.cognito.list_portal_users_for_client",
        return_value=[
            PortalUserRecord(
                username="poc",
                email="poc@example.com",
                client_id="poc",
                role="admin",
                status="CONFIRMED",
                enabled=True,
            )
        ],
    ), patch(
        "meshflow.dna.web.portal.cognito.invite_portal_user",
        return_value={
            "username": "jane",
            "client_id": "poc",
            "email": "jane@example.com",
            "role": "member",
            "status": "FORCE_CHANGE_PASSWORD",
            "delivery": "invite_email",
        },
    ) as mock_invite:
        client.post("/portal/login", data={"action": "sign_in", "username": "poc", "password": "SecretPass123!"})
        response = client.post(
            "/portal/governance/users",
            data={
                "action": "invite",
                "username": "jane",
                "email": "jane@example.com",
                "role": "member",
            },
        )

    assert response.status_code == 200
    assert b"Invite sent to jane@example.com" in response.data
    mock_invite.assert_called_once()
    assert mock_invite.call_args.kwargs["client_id"] == "poc"
    assert mock_invite.call_args.kwargs["max_users"] == 10
    assert mock_invite.call_args.kwargs["role"] == "member"
