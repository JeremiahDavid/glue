"""HiveFlowAI web application — public site + authenticated client portal."""

from __future__ import annotations

import json
import mimetypes
from pathlib import Path
from typing import Any

from werkzeug.routing import Map, Rule
from werkzeug.serving import run_simple
from werkzeug.wrappers import Request, Response

from meshflow.dna.settings import DnaSettings
from meshflow.dna.store import load_pack_from_settings, read_json_artifact, read_production_output
from meshflow.dna.web.portal.auth import (
    authenticate,
    clear_session_cookie,
    load_portal_users,
    login_response,
    require_portal_session,
    session_from_request,
)
from meshflow.dna.web.portal.config import load_client_portal_config
from meshflow.dna.web.portal.views import (
    REVENUE_OUTPUT_ID,
    REVENUE_TABLE_LIMIT,
    render_executive,
    render_overview,
    render_revenue,
    render_semantics,
)
from meshflow.dna.web.branding import load_branding_asset
from meshflow.dna.web.public.pages import render_landing, render_platform, render_pricing
from meshflow.dna.web.theme import BRAND_NAME, MIME_TYPES, STATIC_DIR, render_login_page

LEGACY_REDIRECTS = {
    "/executive": "/portal/executive",
    "/revenue": "/portal/revenue",
    "/definitions": "/portal/semantics",
    "/kpis": "/portal/executive",
}


def _json_response(payload: Any, status: int = 200) -> Response:
    return Response(
        json.dumps(payload, indent=2, default=str),
        status=status,
        mimetype="application/json",
    )


def _api_gateway_stage(environ: dict[str, Any]) -> str:
    """Resolve API Gateway stage from awsgi event or headers."""
    event = environ.get("awsgi.event")
    if isinstance(event, dict):
        request_context = event.get("requestContext")
        if isinstance(request_context, dict):
            stage = str(request_context.get("stage", "")).strip()
            if stage:
                return stage
    return str(environ.get("HTTP_X_AMZN_APIGATEWAY_STAGE", "")).strip()


def _is_execute_api_host(environ: dict[str, Any]) -> bool:
    host = str(environ.get("HTTP_HOST") or environ.get("SERVER_NAME") or "").lower()
    return "execute-api" in host and "amazonaws.com" in host


def _prepare_gateway_environ(environ: dict[str, Any]) -> None:
    """Normalize API Gateway stage prefix into SCRIPT_NAME for link generation."""
    if environ.get("SCRIPT_NAME"):
        return

    path_info = environ.get("PATH_INFO") or "/"
    stage = _api_gateway_stage(environ)

    if stage:
        prefix = f"/{stage}"
        if path_info == prefix or path_info.startswith(f"{prefix}/"):
            environ["SCRIPT_NAME"] = prefix
            remainder = path_info[len(prefix) :]
            environ["PATH_INFO"] = remainder or "/"
            return

        # execute-api URLs include the stage in the browser path but awsgi may
        # pass PATH_INFO without it — still prefix generated links.
        if _is_execute_api_host(environ):
            environ["SCRIPT_NAME"] = prefix
            return

    for stage_name in ("prod", "dev", "staging"):
        prefix = f"/{stage_name}"
        if path_info == prefix or path_info.startswith(f"{prefix}/"):
            environ["SCRIPT_NAME"] = prefix
            remainder = path_info[len(prefix) :]
            environ["PATH_INFO"] = remainder or "/"
            return


def _app_url(request: Request, path: str) -> str:
    if not path.startswith("/"):
        path = f"/{path}"
    return f"{request.script_root}{path}"


def _redirect(request: Request, path: str) -> Response:
    return Response(status=302, headers={"Location": _app_url(request, path)})


def _serve_static(filename: str) -> Response:
    safe_name = Path(filename).name
    body = load_branding_asset(safe_name)
    if body is None:
        asset_path = STATIC_DIR / safe_name
        if not asset_path.is_file():
            return Response("Not found", status=404)
        body = asset_path.read_bytes()

    suffix = Path(safe_name).suffix.lower()
    mime = MIME_TYPES.get(suffix) or mimetypes.guess_type(safe_name)[0] or "application/octet-stream"
    return Response(
        body,
        mimetype=mime,
        headers={"Cache-Control": "public, max-age=86400"},
    )


def _portal_settings(base_settings: DnaSettings, client_config: Any) -> DnaSettings:
    if client_config.pack_id and client_config.pack_id != base_settings.pack_id:
        return DnaSettings(
            source=base_settings.source,
            data_dir=base_settings.data_dir,
            s3_bucket=base_settings.s3_bucket,
            pack_id=client_config.pack_id,
            pack_version=base_settings.pack_version,
        )
    return base_settings


def create_app(
    settings: DnaSettings,
    *,
    company: str = "POC",
    environment: str = "dev",
    env_config: dict[str, Any] | None = None,
):
    env_config = env_config or {}

    url_map = Map(
        [
            Rule("/", endpoint="landing"),
            Rule("/platform", endpoint="platform"),
            Rule("/pricing", endpoint="pricing"),
            Rule("/portal/login", endpoint="portal_login", methods=["GET", "POST"]),
            Rule("/portal/logout", endpoint="portal_logout"),
            Rule("/portal", endpoint="portal_home"),
            Rule("/portal/", endpoint="portal_home"),
            Rule("/portal/executive", endpoint="portal_executive"),
            Rule("/portal/revenue", endpoint="portal_revenue"),
            Rule("/portal/semantics", endpoint="portal_semantics"),
            Rule("/static/<path:filename>", endpoint="static"),
            Rule("/api/pack", endpoint="api_pack"),
            Rule("/api/kpis", endpoint="api_kpis"),
            Rule("/api/revenue", endpoint="api_revenue"),
            Rule("/api/manifest", endpoint="api_manifest"),
        ],
        strict_slashes=False,
    )

    def _client_config(client_id: str):
        return load_client_portal_config(
            client_id,
            env_config,
            default_pack_id=settings.pack_id,
        )

    def on_landing(request: Request) -> Response:
        return render_landing(request)

    def on_platform(request: Request) -> Response:
        return render_platform(request)

    def on_pricing(request: Request) -> Response:
        return render_pricing(request)

    def on_portal_login(request: Request) -> Response:
        url = lambda path: _app_url(request, path)
        if request.method == "GET":
            existing = session_from_request(request, company=company, environment=environment)
            next_path = request.args.get("next", "/portal")
            if existing is not None:
                return _redirect(request, next_path)
            return Response(
                render_login_page(url=url, next_path=next_path),
                mimetype="text/html",
            )

        username = request.form.get("username", "")
        password = request.form.get("password", "")
        next_path = request.form.get("next", "/portal") or "/portal"
        user = authenticate(username, password, company=company, environment=environment)
        if user is None:
            return Response(
                render_login_page(url=url, error="Invalid username or password.", next_path=next_path),
                mimetype="text/html",
                status=401,
            )
        return login_response(
            user,
            company=company,
            environment=environment,
            redirect_to=_app_url(request, next_path),
        )

    def on_portal_logout(request: Request) -> Response:
        response = _redirect(request, "/portal/login")
        clear_session_cookie(response)
        return response

    def _authorized(request: Request):
        login_url = _app_url(request, "/portal/login")
        return require_portal_session(request, company=company, environment=environment, login_url=login_url)

    def on_portal_home(request: Request) -> Response:
        session, redirect = _authorized(request)
        if redirect is not None:
            return redirect
        client = _client_config(session.client_id)
        portal_settings = _portal_settings(settings, client)
        return render_overview(request, settings=portal_settings, client=client)

    def on_portal_executive(request: Request) -> Response:
        session, redirect = _authorized(request)
        if redirect is not None:
            return redirect
        client = _client_config(session.client_id)
        portal_settings = _portal_settings(settings, client)
        return render_executive(request, settings=portal_settings, client=client)

    def on_portal_revenue(request: Request) -> Response:
        session, redirect = _authorized(request)
        if redirect is not None:
            return redirect
        client = _client_config(session.client_id)
        portal_settings = _portal_settings(settings, client)
        return render_revenue(request, settings=portal_settings, client=client)

    def on_portal_semantics(request: Request) -> Response:
        session, redirect = _authorized(request)
        if redirect is not None:
            return redirect
        client = _client_config(session.client_id)
        portal_settings = _portal_settings(settings, client)
        return render_semantics(request, settings=portal_settings, client=client)

    def on_static(_request: Request, filename: str) -> Response:
        return _serve_static(filename)

    def _api_authorized(request: Request) -> Response | None:
        session, redirect = _authorized(request)
        if redirect is not None:
            return _json_response({"error": "authentication_required"}, status=401)
        return None

    def on_api_pack(request: Request) -> Response:
        if (failure := _api_authorized(request)) is not None:
            return failure
        session = session_from_request(request, company=company, environment=environment)
        assert session is not None
        client = _client_config(session.client_id)
        portal_settings = _portal_settings(settings, client)
        return _json_response(load_pack_from_settings(portal_settings).to_dict())

    def on_api_kpis(request: Request) -> Response:
        if (failure := _api_authorized(request)) is not None:
            return failure
        session = session_from_request(request, company=company, environment=environment)
        assert session is not None
        client = _client_config(session.client_id)
        portal_settings = _portal_settings(settings, client)
        return _json_response(read_production_output(portal_settings, "out_kpi_snapshot"))

    def on_api_revenue(request: Request) -> Response:
        if (failure := _api_authorized(request)) is not None:
            return failure
        session = session_from_request(request, company=company, environment=environment)
        assert session is not None
        client = _client_config(session.client_id)
        portal_settings = _portal_settings(settings, client)
        all_rows = read_production_output(portal_settings, REVENUE_OUTPUT_ID)
        rows = sorted(all_rows, key=lambda row: str(row.get("postingDate", "")), reverse=True)[
            :REVENUE_TABLE_LIMIT
        ]
        return _json_response(
            {
                "output_id": REVENUE_OUTPUT_ID,
                "row_count": len(all_rows),
                "truncated": len(all_rows) > len(rows),
                "rows": rows,
            }
        )

    def on_api_manifest(request: Request) -> Response:
        if (failure := _api_authorized(request)) is not None:
            return failure
        session = session_from_request(request, company=company, environment=environment)
        assert session is not None
        client = _client_config(session.client_id)
        portal_settings = _portal_settings(settings, client)
        manifest = read_json_artifact(portal_settings, f"{portal_settings.gold_dna_prefix}/manifest.json")
        return _json_response(manifest or {})

    endpoints = {
        "landing": on_landing,
        "platform": on_platform,
        "pricing": on_pricing,
        "portal_login": on_portal_login,
        "portal_logout": on_portal_logout,
        "portal_home": on_portal_home,
        "portal_executive": on_portal_executive,
        "portal_revenue": on_portal_revenue,
        "portal_semantics": on_portal_semantics,
        "static": on_static,
        "api_pack": on_api_pack,
        "api_kpis": on_api_kpis,
        "api_revenue": on_api_revenue,
        "api_manifest": on_api_manifest,
    }

    def application(environ, start_response):
        _prepare_gateway_environ(environ)
        request = Request(environ)
        path = request.path.rstrip("/") or "/"
        legacy_target = LEGACY_REDIRECTS.get(path)
        if legacy_target is not None:
            location = _app_url(request, legacy_target)
            response = Response(status=302, headers={"Location": location})
            return response(environ, start_response)

        adapter = url_map.bind_to_environ(environ)
        try:
            endpoint, values = adapter.match()
            response = endpoints[endpoint](request, **values)
        except Exception as exc:  # noqa: BLE001 — surface errors in dev UI
            response = _json_response({"error": str(exc)}, status=500)
        return response(environ, start_response)

    application.load_portal_users = lambda: load_portal_users(company=company, environment=environment)  # type: ignore[attr-defined]
    return application


def run_server(settings: DnaSettings, *, host: str = "127.0.0.1", port: int = 8080) -> None:
    from meshflow.project_config import get_environment_config, resolve_selection

    company, environment = resolve_selection()
    env_config = get_environment_config(company, environment)
    app = create_app(settings, company=company, environment=environment, env_config=env_config)
    print(f"{BRAND_NAME} at http://{host}:{port}/")
    print(f"Client portal login at http://{host}:{port}/portal/login")
    run_simple(host, port, app, use_reloader=False, use_debugger=False)
