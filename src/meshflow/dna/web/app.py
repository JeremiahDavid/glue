"""HiveFlowAI web application — public site + authenticated client portal."""

from __future__ import annotations

import json
import mimetypes
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlparse

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
    require_portal_admin,
    require_portal_session,
    session_from_request,
)
from meshflow.dna.web.portal.config import load_client_portal_config
from meshflow.dna.web.portal.views import (
    REVENUE_OUTPUT_ID,
    REVENUE_TABLE_LIMIT,
    _legacy_portal_users,
    aggregate_revenue_by_month,
    render_admin_users,
    render_executive,
    render_governance,
    render_overview,
    render_revenue,
    render_revenue_trend,
    render_chart_demo,
)
from meshflow.dna.web.branding import load_branding_asset
from meshflow.dna.web.public.pages import render_landing, render_platform, render_pricing
from meshflow.dna.web.theme import BRAND_NAME, MIME_TYPES, STATIC_DIR, render_login_page

LEGACY_REDIRECTS = {
    "/executive": "/portal/executive",
    "/revenue": "/portal/revenue",
    "/definitions": "/portal/governance",
    "/semantics": "/portal/governance",
    "/portal/semantics": "/portal/governance",
    "/kpis": "/portal/executive",
}

GLOBAL_UI_ENDPOINTS = frozenset(
    {
        "landing",
        "platform",
        "pricing",
        "portal_login",
        "portal_logout",
        "portal_home",
        "portal_admin_users",
        "static",
    }
)

REPORTING_UI_ENDPOINTS = frozenset(
    {
        "portal_login",
        "portal_logout",
        "portal_home",
        "portal_executive",
        "portal_revenue",
        "portal_revenue_trend",
        "portal_chart_demo",
        "portal_governance",
        "portal_semantics",
        "static",
        "api_pack",
        "api_kpis",
        "api_revenue",
        "api_revenue_trend",
        "api_manifest",
    }
)


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


def _portal_settings(
    base_settings: DnaSettings,
    client_config: Any,
    *,
    environment: str,
) -> DnaSettings:
    from meshflow.project_config import (
        get_environment_config,
        resolve_aws_deploy_env,
        resolve_data_bucket_name,
        resolve_dna_source,
    )

    pack_id = client_config.pack_id or base_settings.pack_id
    reporting_company = str(getattr(client_config, "reporting_company", "")).strip()

    if reporting_company:
        client_env = get_environment_config(reporting_company, environment)
        bucket = base_settings.s3_bucket
        if not bucket:
            try:
                account, region = resolve_aws_deploy_env(client_env, environment)
                bucket = resolve_data_bucket_name(
                    reporting_company,
                    environment,
                    account=account,
                    region=region,
                )
            except ValueError:
                bucket = None
        source = resolve_dna_source(client_env)
        return DnaSettings(
            source=source,
            data_dir=base_settings.data_dir,
            s3_bucket=bucket,
            pack_id=pack_id,
            pack_version=base_settings.pack_version,
        )

    if pack_id != base_settings.pack_id:
        return DnaSettings(
            source=base_settings.source,
            data_dir=base_settings.data_dir,
            s3_bucket=base_settings.s3_bucket,
            pack_id=pack_id,
            pack_version=base_settings.pack_version,
        )
    return base_settings


def _resolve_ui_mode(ui_mode: str | None = None) -> str:
    resolved = (ui_mode or os.getenv("MESHFLOW_UI_MODE", "full")).strip().lower()
    if resolved not in {"full", "global", "reporting"}:
        return "full"
    return resolved


def _client_reporting_site_url(client_id: str) -> str | None:
    cookie_domain = os.getenv("HIVEFLOW_PORTAL_COOKIE_DOMAIN", "").strip().lstrip(".")
    if not cookie_domain:
        return None
    normalized = client_id.strip().lower()
    if not normalized:
        return None
    return f"https://{normalized}.{cookie_domain}/portal"


def _sanitize_portal_next(next_path: str, *, client_id: str = "") -> str:
    """Normalize post-login targets — never bounce through reporting /portal/login."""
    value = (next_path or "/portal").strip()
    if not value:
        return "/portal"
    if value.rstrip("/") == "/portal/login":
        return "/portal"
    if value.startswith("http://") or value.startswith("https://"):
        parsed = urlparse(value)
        path = parsed.path or "/"
        if path.rstrip("/") == "/portal/login":
            return "/portal"
        reporting_base = _client_reporting_site_url(client_id) if client_id else None
        if reporting_base:
            base = urlparse(reporting_base)
            if parsed.netloc == base.netloc and path.startswith("/portal"):
                suffix = path.removeprefix("/portal")
                return f"/portal{suffix}" if suffix else "/portal"
    return value


def _external_redirect(url: str) -> Response:
    return Response(status=302, headers={"Location": url})


def create_app(
    settings: DnaSettings,
    *,
    company: str = "POC",
    environment: str = "dev",
    env_config: dict[str, Any] | None = None,
    ui_mode: str | None = None,
):
    env_config = env_config or {}
    resolved_ui_mode = _resolve_ui_mode(ui_mode)
    fixed_client_id = os.getenv("MESHFLOW_PORTAL_CLIENT_ID", "").strip().lower()
    global_login_url = os.getenv("HIVEFLOW_GLOBAL_LOGIN_URL", "").strip()

    rules: list[Rule] = []
    if resolved_ui_mode in {"full", "global"}:
        rules.extend(
            [
                Rule("/", endpoint="landing"),
                Rule("/platform", endpoint="platform"),
                Rule("/pricing", endpoint="pricing"),
            ]
        )
    if resolved_ui_mode in {"full", "global"}:
        rules.extend(
            [
                Rule("/portal/login", endpoint="portal_login", methods=["GET", "POST"]),
                Rule("/portal/logout", endpoint="portal_logout"),
                Rule("/portal/admin/users", endpoint="portal_admin_users", methods=["GET", "POST"]),
            ]
        )
        if resolved_ui_mode == "global":
            rules.extend(
                [
                    Rule("/portal", endpoint="portal_home"),
                    Rule("/portal/", endpoint="portal_home"),
                ]
            )
    if resolved_ui_mode in {"full", "reporting"}:
        rules.extend(
            [
                Rule("/portal/login", endpoint="portal_login", methods=["GET", "POST"]),
                Rule("/portal/logout", endpoint="portal_logout"),
                Rule("/portal", endpoint="portal_home"),
                Rule("/portal/", endpoint="portal_home"),
                Rule("/portal/executive", endpoint="portal_executive"),
                Rule("/portal/revenue", endpoint="portal_revenue"),
                Rule("/portal/revenue-trend", endpoint="portal_revenue_trend"),
                Rule("/portal/chart-demo", endpoint="portal_chart_demo"),
                Rule("/portal/governance", endpoint="portal_governance"),
                Rule("/portal/semantics", endpoint="portal_semantics"),
                Rule("/api/pack", endpoint="api_pack"),
                Rule("/api/kpis", endpoint="api_kpis"),
                Rule("/api/revenue", endpoint="api_revenue"),
                Rule("/api/revenue-trend", endpoint="api_revenue_trend"),
                Rule("/api/manifest", endpoint="api_manifest"),
            ]
        )
    rules.append(Rule("/static/<path:filename>", endpoint="static"))

    url_map = Map(rules, strict_slashes=False)

    def _client_config(client_id: str):
        if fixed_client_id:
            client_id = fixed_client_id
        ui_cfg = env_config.get("ui", {})
        default_pack_id = str(ui_cfg.get("pack_id", settings.pack_id))
        return load_client_portal_config(
            client_id,
            env_config,
            default_pack_id=default_pack_id,
        )

    def _login_url(request: Request) -> str:
        if global_login_url:
            return global_login_url
        return _app_url(request, "/portal/login")

    def _post_login_redirect(request: Request, user_client_id: str, next_path: str) -> str:
        next_path = _sanitize_portal_next(next_path, client_id=user_client_id)
        if next_path.startswith("http://") or next_path.startswith("https://"):
            return next_path
        if resolved_ui_mode == "global":
            reporting_base = _client_reporting_site_url(user_client_id)
            if reporting_base and next_path.startswith("/portal"):
                suffix = next_path.removeprefix("/portal")
                return f"{reporting_base.rstrip('/')}{suffix or ''}"
        return _app_url(request, next_path)

    def on_landing(request: Request) -> Response:
        return render_landing(request)

    def on_platform(request: Request) -> Response:
        return render_platform(request)

    def on_pricing(request: Request) -> Response:
        return render_pricing(request)

    def on_portal_login(request: Request) -> Response:
        if resolved_ui_mode == "reporting" and global_login_url:
            existing = session_from_request(request, company=company, environment=environment)
            if existing is not None:
                next_path = _sanitize_portal_next(
                    request.args.get("next", "/portal"),
                    client_id=existing.client_id,
                )
                destination = _post_login_redirect(request, existing.client_id, next_path)
                if destination.startswith("http://") or destination.startswith("https://"):
                    return _external_redirect(destination)
                return _redirect(request, next_path)
            next_path = _sanitize_portal_next(request.args.get("next", "/portal"))
            return _external_redirect(f"{global_login_url}?{urlencode({'next': next_path})}")

        from meshflow.dna.web.portal.cognito import (
            authenticate_with_cognito,
            cognito_configured,
            complete_new_password_challenge,
        )

        url = lambda path: _app_url(request, path)
        if request.method == "GET":
            existing = session_from_request(request, company=company, environment=environment)
            next_path = _sanitize_portal_next(
                request.args.get("next", "/portal"),
                client_id=existing.client_id if existing is not None else "",
            )
            if existing is not None:
                destination = _post_login_redirect(request, existing.client_id, next_path)
                if destination.startswith("http://") or destination.startswith("https://"):
                    return _external_redirect(destination)
                return Response(status=302, headers={"Location": destination})
            return Response(
                render_login_page(url=url, next_path=next_path),
                mimetype="text/html",
            )

        action = request.form.get("action", "sign_in")
        next_path = request.form.get("next", "/portal") or "/portal"

        if action == "set_password":
            username = request.form.get("username", "")
            session = request.form.get("session", "")
            new_password = request.form.get("new_password", "")
            confirm_password = request.form.get("confirm_password", "")
            if new_password != confirm_password:
                return Response(
                    render_login_page(
                        url=url,
                        error="Passwords do not match.",
                        next_path=next_path,
                        mode="set_password",
                        username=username,
                        session=session,
                    ),
                    mimetype="text/html",
                    status=400,
                )
            user = complete_new_password_challenge(
                username=username,
                session=session,
                new_password=new_password,
                company=company,
                environment=environment,
            )
            if user is None:
                return Response(
                    render_login_page(
                        url=url,
                        error="Could not update your password. Check the policy and try again.",
                        next_path=next_path,
                        mode="set_password",
                        username=username,
                        session=session,
                    ),
                    mimetype="text/html",
                    status=401,
                )
            return login_response(
                user,
                company=company,
                environment=environment,
                redirect_to=_post_login_redirect(request, user.client_id, next_path),
            )

        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if cognito_configured():
            login_result = authenticate_with_cognito(
                username,
                password,
                company=company,
                environment=environment,
            )
            if login_result is None:
                return Response(
                    render_login_page(url=url, error="Invalid username or password.", next_path=next_path),
                    mimetype="text/html",
                    status=401,
                )
            if login_result.kind == "new_password" and login_result.challenge is not None:
                challenge = login_result.challenge
                return Response(
                    render_login_page(
                        url=url,
                        next_path=next_path,
                        mode="set_password",
                        username=challenge.username,
                        session=challenge.session,
                    ),
                    mimetype="text/html",
                )
            if login_result.user is None:
                return Response(
                    render_login_page(url=url, error="Invalid username or password.", next_path=next_path),
                    mimetype="text/html",
                    status=401,
                )
            return login_response(
                login_result.user,
                company=company,
                environment=environment,
                redirect_to=_post_login_redirect(request, login_result.user.client_id, next_path),
            )

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
            redirect_to=_post_login_redirect(request, user.client_id, next_path),
        )

    def on_portal_logout(request: Request) -> Response:
        response = _redirect(request, "/portal/login")
        clear_session_cookie(response)
        return response

    def _authorized(request: Request):
        login_url = _login_url(request)
        session, redirect = require_portal_session(
            request,
            company=company,
            environment=environment,
            login_url=login_url,
        )
        if session is not None and fixed_client_id and session.client_id != fixed_client_id:
            return None, _redirect(request, "/portal/login")
        return session, redirect

    def _portal_is_admin(username: str) -> bool:
        return require_portal_admin(username, company=company, environment=environment)

    def on_portal_home(request: Request) -> Response:
        session, redirect = _authorized(request)
        if redirect is not None:
            return redirect
        if resolved_ui_mode == "global":
            reporting_url = _client_reporting_site_url(session.client_id)
            if reporting_url:
                return _external_redirect(reporting_url)
            return Response(
                "Reporting dashboard URL is not configured for this client.",
                status=503,
                mimetype="text/plain",
            )
        client = _client_config(session.client_id)
        portal_settings = _portal_settings(settings, client, environment=environment)
        is_admin = _portal_is_admin(session.username)
        return render_overview(request, settings=portal_settings, client=client, is_admin=is_admin)

    def on_portal_executive(request: Request) -> Response:
        session, redirect = _authorized(request)
        if redirect is not None:
            return redirect
        client = _client_config(session.client_id)
        portal_settings = _portal_settings(settings, client, environment=environment)
        is_admin = _portal_is_admin(session.username)
        return render_executive(request, settings=portal_settings, client=client, is_admin=is_admin)

    def on_portal_revenue(request: Request) -> Response:
        session, redirect = _authorized(request)
        if redirect is not None:
            return redirect
        client = _client_config(session.client_id)
        portal_settings = _portal_settings(settings, client, environment=environment)
        is_admin = _portal_is_admin(session.username)
        return render_revenue(request, settings=portal_settings, client=client, is_admin=is_admin)

    def on_portal_revenue_trend(request: Request) -> Response:
        session, redirect = _authorized(request)
        if redirect is not None:
            return redirect
        client = _client_config(session.client_id)
        portal_settings = _portal_settings(settings, client, environment=environment)
        is_admin = _portal_is_admin(session.username)
        return render_revenue_trend(request, settings=portal_settings, client=client, is_admin=is_admin)

    def on_portal_chart_demo(request: Request) -> Response:
        session, redirect = _authorized(request)
        if redirect is not None:
            return redirect
        client = _client_config(session.client_id)
        portal_settings = _portal_settings(settings, client, environment=environment)
        is_admin = _portal_is_admin(session.username)
        return render_chart_demo(request, settings=portal_settings, client=client, is_admin=is_admin)

    def on_portal_governance(request: Request) -> Response:
        session, redirect = _authorized(request)
        if redirect is not None:
            return redirect
        client = _client_config(session.client_id)
        portal_settings = _portal_settings(settings, client, environment=environment)
        is_admin = _portal_is_admin(session.username)
        return render_governance(request, settings=portal_settings, client=client, is_admin=is_admin)

    def on_portal_admin_users(request: Request) -> Response:
        from meshflow.dna.web.portal.cognito import (
            PortalUserAlreadyExists,
            PortalUserLimitExceeded,
            cognito_configured,
            invite_portal_user,
            list_portal_users_for_client,
        )

        session, redirect = _authorized(request)
        if redirect is not None:
            return redirect
        if not _portal_is_admin(session.username):
            return Response("Forbidden", status=403, mimetype="text/plain")

        client = _client_config(session.client_id)
        message = ""
        error = ""
        invites_enabled = cognito_configured()

        if request.method == "POST" and request.form.get("action") == "invite":
            if not invites_enabled:
                error = "Team invites require Cognito authentication."
            else:
                username = request.form.get("username", "").strip()
                email = request.form.get("email", "").strip()
                try:
                    invite_portal_user(
                        username=username,
                        client_id=session.client_id,
                        email=email,
                        company=company,
                        environment=environment,
                        max_users=client.max_users,
                    )
                    message = f"Invite sent to {email}."
                except PortalUserLimitExceeded:
                    error = f"Seat limit reached ({client.max_users} users)."
                except PortalUserAlreadyExists:
                    error = f"Username {username!r} is already taken."
                except ValueError as exc:
                    error = str(exc)
                except RuntimeError as exc:
                    error = str(exc)

        if invites_enabled:
            users = list_portal_users_for_client(
                client_id=session.client_id,
                company=company,
                environment=environment,
            )
        else:
            users = _legacy_portal_users(session.client_id, company=company, environment=environment)

        return render_admin_users(
            request,
            client=client,
            users=users,
            current_username=session.username,
            message=message,
            error=error,
            invites_enabled=invites_enabled,
        )

    def on_portal_semantics(request: Request) -> Response:
        return _redirect(request, "/portal/governance")

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
        portal_settings = _portal_settings(settings, client, environment=environment)
        return _json_response(load_pack_from_settings(portal_settings).to_dict())

    def on_api_kpis(request: Request) -> Response:
        if (failure := _api_authorized(request)) is not None:
            return failure
        session = session_from_request(request, company=company, environment=environment)
        assert session is not None
        client = _client_config(session.client_id)
        portal_settings = _portal_settings(settings, client, environment=environment)
        return _json_response(read_production_output(portal_settings, "out_kpi_snapshot"))

    def on_api_revenue(request: Request) -> Response:
        if (failure := _api_authorized(request)) is not None:
            return failure
        session = session_from_request(request, company=company, environment=environment)
        assert session is not None
        client = _client_config(session.client_id)
        portal_settings = _portal_settings(settings, client, environment=environment)
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

    def on_api_revenue_trend(request: Request) -> Response:
        if (failure := _api_authorized(request)) is not None:
            return failure
        session = session_from_request(request, company=company, environment=environment)
        assert session is not None
        client = _client_config(session.client_id)
        portal_settings = _portal_settings(settings, client, environment=environment)
        all_rows = read_production_output(portal_settings, REVENUE_OUTPUT_ID)
        monthly = aggregate_revenue_by_month(all_rows)
        return _json_response(
            {
                "output_id": REVENUE_OUTPUT_ID,
                "row_count": len(all_rows),
                "months": [{"month": month, "net_amount": amount} for month, amount in monthly],
            }
        )

    def on_api_manifest(request: Request) -> Response:
        if (failure := _api_authorized(request)) is not None:
            return failure
        session = session_from_request(request, company=company, environment=environment)
        assert session is not None
        client = _client_config(session.client_id)
        portal_settings = _portal_settings(settings, client, environment=environment)
        manifest = read_json_artifact(portal_settings, f"{portal_settings.gold_dna_prefix}/manifest.json")
        return _json_response(manifest or {})

    enabled_endpoints = set(GLOBAL_UI_ENDPOINTS) | set(REPORTING_UI_ENDPOINTS)
    if resolved_ui_mode == "global":
        enabled_endpoints = GLOBAL_UI_ENDPOINTS
    elif resolved_ui_mode == "reporting":
        enabled_endpoints = REPORTING_UI_ENDPOINTS

    endpoints = {
        "landing": on_landing,
        "platform": on_platform,
        "pricing": on_pricing,
        "portal_login": on_portal_login,
        "portal_logout": on_portal_logout,
        "portal_home": on_portal_home,
        "portal_executive": on_portal_executive,
        "portal_revenue": on_portal_revenue,
        "portal_revenue_trend": on_portal_revenue_trend,
        "portal_chart_demo": on_portal_chart_demo,
        "portal_governance": on_portal_governance,
        "portal_admin_users": on_portal_admin_users,
        "portal_semantics": on_portal_semantics,
        "static": on_static,
        "api_pack": on_api_pack,
        "api_kpis": on_api_kpis,
        "api_revenue": on_api_revenue,
        "api_revenue_trend": on_api_revenue_trend,
        "api_manifest": on_api_manifest,
    }

    def application(environ, start_response):
        _prepare_gateway_environ(environ)
        request = Request(environ)
        path = request.path.rstrip("/") or "/"
        legacy_target = LEGACY_REDIRECTS.get(path)
        if legacy_target is not None:
            if resolved_ui_mode == "global":
                session = session_from_request(request, company=company, environment=environment)
                if session is not None:
                    reporting_url = _client_reporting_site_url(session.client_id)
                    if reporting_url:
                        suffix = legacy_target.removeprefix("/portal")
                        location = f"{reporting_url.rstrip('/')}{suffix or ''}"
                        response = Response(status=302, headers={"Location": location})
                        return response(environ, start_response)
            location = _app_url(request, legacy_target)
            response = Response(status=302, headers={"Location": location})
            return response(environ, start_response)

        adapter = url_map.bind_to_environ(environ)
        try:
            endpoint, values = adapter.match()
            if endpoint not in enabled_endpoints:
                response = Response("Not found", status=404)
                return response(environ, start_response)
            response = endpoints[endpoint](request, **values)
        except Exception as exc:  # noqa: BLE001 — surface errors in dev UI
            response = _json_response({"error": str(exc)}, status=500)
        return response(environ, start_response)

    application.load_portal_users = lambda: load_portal_users(company=company, environment=environment)  # type: ignore[attr-defined]
    return application


def run_server(settings: DnaSettings, *, host: str = "127.0.0.1", port: int = 8080) -> None:
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
    app = create_app(settings, company=company, environment=environment, env_config=env_config)
    print(f"{BRAND_NAME} at http://{host}:{port}/")
    print(f"Client portal login at http://{host}:{port}/portal/login")
    run_simple(host, port, app, use_reloader=False, use_debugger=False)
