"""HiveFlowAI web application — public site + authenticated client portal."""

from __future__ import annotations

import json
import mimetypes
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlparse

from werkzeug.routing import Map, Rule
from werkzeug.exceptions import NotFound
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
from meshflow.dna.web.portal.preview import (
    clear_preview_cookie,
    preview_proposal_id,
    set_preview_cookie,
)
from meshflow.dna.web.portal.reporting_layout import find_reporting_page
from meshflow.dna.web.portal.reporting_api import (
    fetch_output_rows,
    fetch_page_data,
    list_reporting_pages_json,
)
from meshflow.dna.web.portal.governance_helpers.gold_bindings import build_reporting_binding_catalog
from meshflow.dna.web.portal.views import (
    _legacy_portal_users,
    render_admin_users,
    render_configured_page,
    render_governance,
)
from meshflow.dna.web.branding import load_branding_asset
from meshflow.dna.web.public.pages import render_landing, render_platform, render_pricing
from meshflow.dna.web.theme import BRAND_NAME, MIME_TYPES, STATIC_DIR, render_login_page

LEGACY_REDIRECTS = {
    "/executive": "/portal/executive",
    "/revenue": "/portal/revenue",
    "/definitions": "/portal/governance",
    "/semantics": "/portal/semantics/source-docs",
    "/portal/semantics": "/portal/semantics/source-docs",
    "/kpis": "/portal/executive",
    "/portal/admin/users": "/portal/governance/users",
    "/portal/admin/config": "/portal/governance/config",
    "/portal/admin/config/preview/exit": "/portal/governance/config/preview/exit",
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
        "portal_configured_page",
        "portal_catalog",
        "portal_catalog_output",
        "portal_catalog_gold",
        "portal_catalog_silver",
        "portal_catalog_silver_entity",
        "portal_dna",
        "portal_dna_kpi_generator",
        "portal_dna_kpi_generator_status",
        "portal_governance",
        "portal_governance_users",
        "portal_governance_config",
        "portal_governance_config_preview_exit",
        "portal_source_docs_inspector",
        "portal_source_docs_inspector_source",
        "portal_admin_users",
        "portal_admin_config",
        "portal_admin_config_preview_exit",
        "static",
        "api_pack",
        "api_manifest",
        "api_output",
        "api_reporting_pages",
        "api_reporting_page",
        "api_reporting_catalog",
        "api_source_docs_gold",
        "api_source_docs_gold_build",
        "api_source_docs_gold_exclude",
        "api_source_docs_gold_undo_exclude",
        "api_source_docs_gold_submit",
        "api_source_docs_gold_versions",
        "api_source_docs_gold_versions_commit",
        "api_source_docs_gold_restore",
    }
)

ADMIN_UI_ENDPOINTS = frozenset(
    {
        "admin_home",
        "admin_login",
        "admin_logout",
        "admin_architecture",
        "admin_job_run",
        "admin_job_status",
        "admin_onboarding",
        "admin_onboarding_new",
        "admin_onboarding_detail",
        "admin_onboarding_deploy",
        "admin_onboarding_secrets",
        "admin_onboarding_validate",
        "admin_onboarding_qwc",
        "static",
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


def _kpi_generator_redirect(
    request: Request,
    *,
    proposal_id: str = "",
    message: str = "",
    error: str = "",
) -> Response:
    """Post/Redirect/Get for KPI Generator; keep viewport on validation results."""
    params: dict[str, str] = {"validated": "1"}
    if proposal_id:
        params["proposal_id"] = proposal_id
    if message:
        params["msg"] = message
    if error:
        params["err"] = error
    return _redirect(
        request,
        f"/portal/dna/kpi-generator?{urlencode(params)}#kpi-generator-validation",
    )


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
    dev_mode = os.getenv("HIVEFLOW_DEV", "").strip().lower() in {"1", "true", "yes"}
    cache_control = "no-cache" if dev_mode else "public, max-age=86400"
    return Response(
        body,
        mimetype=mime,
        headers={"Cache-Control": cache_control},
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

    from meshflow.storage.paths import company_dna_config_id

    reporting_company = str(getattr(client_config, "reporting_company", "")).strip()
    company = reporting_company or base_settings.company
    pack_id = company_dna_config_id(company) if company else (
        client_config.pack_id or base_settings.pack_id
    )

    use_local_data = os.getenv("MESHFLOW_LOCAL_DATA", "").strip().lower() in {"1", "true", "yes"}

    if reporting_company:
        client_env = get_environment_config(reporting_company, environment)
        bucket = base_settings.s3_bucket
        if not bucket and not use_local_data:
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
            company=reporting_company,
            pack_id=pack_id,
            pack_version=base_settings.pack_version,
        )

    if pack_id != base_settings.pack_id or company != base_settings.company:
        return DnaSettings(
            source=base_settings.source,
            data_dir=base_settings.data_dir,
            s3_bucket=base_settings.s3_bucket,
            company=company or base_settings.company,
            pack_id=pack_id,
            pack_version=base_settings.pack_version,
        )
    return base_settings


def _resolve_ui_mode(ui_mode: str | None = None) -> str:
    resolved = (ui_mode or os.getenv("MESHFLOW_UI_MODE", "full")).strip().lower()
    if resolved not in {"full", "global", "reporting", "admin"}:
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
    if resolved_ui_mode == "admin":
        rules.extend(
            [
                Rule("/", endpoint="admin_home"),
                Rule("/admin", endpoint="admin_home"),
                Rule("/admin/", endpoint="admin_home"),
                Rule("/admin/login", endpoint="admin_login", methods=["GET", "POST"]),
                Rule("/admin/logout", endpoint="admin_logout", methods=["GET", "POST"]),
                Rule("/admin/architecture", endpoint="admin_architecture", methods=["GET"]),
                Rule("/admin/onboarding", endpoint="admin_onboarding", methods=["GET"]),
                Rule("/admin/onboarding/new", endpoint="admin_onboarding_new", methods=["GET", "POST"]),
                Rule(
                    "/admin/onboarding/<company>/deploy",
                    endpoint="admin_onboarding_deploy",
                    methods=["POST"],
                ),
                Rule(
                    "/admin/onboarding/<company>/secrets",
                    endpoint="admin_onboarding_secrets",
                    methods=["POST"],
                ),
                Rule(
                    "/admin/onboarding/<company>/qwc",
                    endpoint="admin_onboarding_qwc",
                    methods=["GET"],
                ),
                Rule(
                    "/admin/onboarding/<company>/validate",
                    endpoint="admin_onboarding_validate",
                    methods=["POST"],
                ),
                Rule(
                    "/admin/onboarding/<company>",
                    endpoint="admin_onboarding_detail",
                    methods=["GET"],
                ),
                Rule("/admin/jobs/<job_id>/run", endpoint="admin_job_run", methods=["POST"]),
                Rule("/admin/jobs/<job_id>/status", endpoint="admin_job_status", methods=["GET"]),
            ]
        )
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
                # Legacy Team URL → Governance Users
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
                Rule("/portal/dna", endpoint="portal_dna"),
                Rule(
                    "/portal/dna/kpi-generator/status",
                    endpoint="portal_dna_kpi_generator_status",
                ),
                Rule(
                    "/portal/dna/kpi-generator",
                    endpoint="portal_dna_kpi_generator",
                    methods=["GET", "POST"],
                ),
                Rule("/portal/catalog/silver/<entity>", endpoint="portal_catalog_silver_entity"),
                Rule("/portal/catalog/silver", endpoint="portal_catalog_silver"),
                Rule("/portal/catalog/gold", endpoint="portal_catalog_gold"),
                Rule("/portal/catalog", endpoint="portal_catalog"),
                Rule("/portal/catalog/<output_id>", endpoint="portal_catalog_output"),
                Rule("/portal/governance", endpoint="portal_governance", methods=["GET", "POST"]),
                Rule(
                    "/portal/governance/users",
                    endpoint="portal_governance_users",
                    methods=["GET", "POST"],
                ),
                Rule(
                    "/portal/governance/config",
                    endpoint="portal_governance_config",
                    methods=["GET", "POST"],
                ),
                Rule(
                    "/portal/governance/config/preview/exit",
                    endpoint="portal_governance_config_preview_exit",
                ),
                Rule("/portal/semantics/source-docs", endpoint="portal_source_docs_inspector"),
                Rule(
                    "/portal/semantics/source-docs/<source>",
                    endpoint="portal_source_docs_inspector_source",
                ),
                # Legacy admin URLs
                Rule("/portal/admin/users", endpoint="portal_admin_users", methods=["GET", "POST"]),
                Rule(
                    "/portal/admin/config",
                    endpoint="portal_admin_config",
                    methods=["GET", "POST"],
                ),
                Rule(
                    "/portal/admin/config/preview/exit",
                    endpoint="portal_admin_config_preview_exit",
                ),
                Rule("/portal/executive", endpoint="portal_executive"),
                Rule("/portal/revenue", endpoint="portal_revenue"),
                Rule("/portal/revenue-trend", endpoint="portal_revenue_trend"),
                Rule("/portal/chart-demo", endpoint="portal_chart_demo"),
                # Catch-all for additional pages declared in reporting config.
                Rule("/portal/<path:subpath>", endpoint="portal_configured_page"),
                Rule("/api/pack", endpoint="api_pack"),
                Rule("/api/manifest", endpoint="api_manifest"),
                Rule("/api/outputs/<output_id>", endpoint="api_output"),
                Rule("/api/reporting/pages", endpoint="api_reporting_pages"),
                Rule("/api/reporting/pages/<path:subpath>", endpoint="api_reporting_page"),
                Rule("/api/reporting/catalog", endpoint="api_reporting_catalog"),
                Rule("/api/source-docs-gold", endpoint="api_source_docs_gold"),
                Rule("/api/source-docs-gold/build", endpoint="api_source_docs_gold_build", methods=["POST"]),
                Rule("/api/source-docs-gold/exclude", endpoint="api_source_docs_gold_exclude", methods=["POST"]),
                Rule(
                    "/api/source-docs-gold/undo-exclude",
                    endpoint="api_source_docs_gold_undo_exclude",
                    methods=["POST"],
                ),
                Rule("/api/source-docs-gold/submit", endpoint="api_source_docs_gold_submit", methods=["POST"]),
                Rule("/api/source-docs-gold/versions", endpoint="api_source_docs_gold_versions"),
                Rule(
                    "/api/source-docs-gold/versions/commit",
                    endpoint="api_source_docs_gold_versions_commit",
                    methods=["POST"],
                ),
                Rule("/api/source-docs-gold/restore", endpoint="api_source_docs_gold_restore", methods=["POST"]),
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
            PasswordResetError,
            authenticate_with_cognito,
            cognito_configured,
            complete_new_password_challenge,
            confirm_password_reset,
            request_password_reset,
        )

        url = lambda path: _app_url(request, path)
        login_modes = {"sign_in", "forgot_password", "reset_password", "set_password"}

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
            mode = request.args.get("mode", "sign_in")
            if mode not in login_modes or mode == "set_password":
                mode = "sign_in"
            return Response(
                render_login_page(url=url, next_path=next_path, mode=mode),
                mimetype="text/html",
            )

        action = request.form.get("action", "sign_in")
        next_path = request.form.get("next", "/portal") or "/portal"

        if action == "forgot_password":
            username = request.form.get("username", "")
            if not cognito_configured():
                return Response(
                    render_login_page(
                        url=url,
                        error="Password reset is only available for Cognito-managed portal accounts.",
                        next_path=next_path,
                        mode="forgot_password",
                        username=username,
                    ),
                    mimetype="text/html",
                    status=400,
                )
            try:
                request_password_reset(username, company=company, environment=environment)
            except PasswordResetError as exc:
                return Response(
                    render_login_page(
                        url=url,
                        error=exc.message,
                        next_path=next_path,
                        mode="forgot_password",
                        username=username,
                    ),
                    mimetype="text/html",
                    status=400,
                )
            return Response(
                render_login_page(
                    url=url,
                    success="If an account exists for that username, we sent a reset code to the email on file.",
                    next_path=next_path,
                    mode="reset_password",
                    username=username,
                ),
                mimetype="text/html",
            )

        if action == "confirm_forgot_password":
            username = request.form.get("username", "")
            confirmation_code = request.form.get("confirmation_code", "")
            new_password = request.form.get("new_password", "")
            confirm_password = request.form.get("confirm_password", "")
            if new_password != confirm_password:
                return Response(
                    render_login_page(
                        url=url,
                        error="Passwords do not match.",
                        next_path=next_path,
                        mode="reset_password",
                        username=username,
                    ),
                    mimetype="text/html",
                    status=400,
                )
            if not cognito_configured():
                return Response(
                    render_login_page(
                        url=url,
                        error="Password reset is only available for Cognito-managed portal accounts.",
                        next_path=next_path,
                        mode="reset_password",
                        username=username,
                    ),
                    mimetype="text/html",
                    status=400,
                )
            try:
                confirm_password_reset(
                    username=username,
                    confirmation_code=confirmation_code,
                    new_password=new_password,
                    company=company,
                    environment=environment,
                )
            except PasswordResetError as exc:
                return Response(
                    render_login_page(
                        url=url,
                        error=exc.message,
                        next_path=next_path,
                        mode="reset_password",
                        username=username,
                    ),
                    mimetype="text/html",
                    status=400,
                )
            return Response(
                render_login_page(
                    url=url,
                    success="Password updated. Sign in with your new password.",
                    next_path=next_path,
                    mode="sign_in",
                ),
                mimetype="text/html",
            )

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

    def _admin_authorized(request: Request):
        from meshflow.dna.web.admin.auth import is_allowed_admin_username

        session, redirect = require_portal_session(
            request,
            company=company,
            environment=environment,
            login_url=_app_url(request, "/admin/login"),
        )
        if session is None:
            return None, redirect
        if not is_allowed_admin_username(session.username):
            response = _redirect(request, "/admin/login")
            clear_session_cookie(response)
            return None, response
        return session, None

    def on_admin_login(request: Request) -> Response:
        from meshflow.dna.web.admin.auth import authenticate_admin, complete_admin_new_password
        from meshflow.dna.web.admin.views import render_admin_login_page
        from meshflow.dna.web.portal.cognito import cognito_configured

        url = lambda path: _app_url(request, path)
        next_path = request.values.get("next", "/admin") or "/admin"
        if not next_path.startswith("/admin"):
            next_path = "/admin"

        if request.method == "GET":
            return Response(
                render_admin_login_page(url=url, next_path=next_path),
                mimetype="text/html",
            )

        mode = str(request.form.get("mode") or "login").strip()
        if mode == "set_password":
            username = str(request.form.get("username") or "")
            session_token = str(request.form.get("session") or "")
            new_password = str(request.form.get("new_password") or "")
            user = complete_admin_new_password(
                username=username,
                session=session_token,
                new_password=new_password,
                company=company,
                environment=environment,
            )
            if user is None:
                return Response(
                    render_admin_login_page(
                        url=url,
                        error="Could not set password. Try again.",
                        next_path=next_path,
                        mode="set_password",
                        username=username,
                        session=session_token,
                    ),
                    mimetype="text/html",
                    status=401,
                )
            return login_response(
                user,
                company=company,
                environment=environment,
                redirect_to=_app_url(request, next_path),
            )

        username = str(request.form.get("username") or "")
        password = str(request.form.get("password") or "")
        if not cognito_configured():
            return Response(
                render_admin_login_page(
                    url=url,
                    error="Admin Cognito is not configured.",
                    next_path=next_path,
                ),
                mimetype="text/html",
                status=503,
            )
        login_result = authenticate_admin(
            username,
            password,
            company=company,
            environment=environment,
        )
        if login_result is None:
            return Response(
                render_admin_login_page(
                    url=url,
                    error="Invalid username or password.",
                    next_path=next_path,
                    username=username,
                ),
                mimetype="text/html",
                status=401,
            )
        if login_result.kind == "new_password" and login_result.challenge is not None:
            challenge = login_result.challenge
            return Response(
                render_admin_login_page(
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
                render_admin_login_page(
                    url=url,
                    error="Invalid username or password.",
                    next_path=next_path,
                ),
                mimetype="text/html",
                status=401,
            )
        return login_response(
            login_result.user,
            company=company,
            environment=environment,
            redirect_to=_app_url(request, next_path),
        )

    def on_admin_logout(request: Request) -> Response:
        response = _redirect(request, "/admin/login")
        clear_session_cookie(response)
        return response

    def on_admin_home(request: Request) -> Response:
        from meshflow.dna.web.admin.jobs import admin_jobs_status_snapshot
        from meshflow.dna.web.admin.views import render_admin_dashboard

        session, redirect = _admin_authorized(request)
        if session is None:
            return redirect
        flash_raw = request.args.get("flash", "")
        job_id = request.args.get("job", "")
        invoked = str(request.args.get("invoked") or "").strip().lower() in {"1", "true", "yes"}
        flash_by_job = {job_id: flash_raw} if job_id and flash_raw else {}
        optimistic_by_job = {job_id: "queued"} if job_id and invoked else {}
        return Response(
            render_admin_dashboard(
                url=lambda path: _app_url(request, path),
                username=session.username,
                statuses=admin_jobs_status_snapshot(),
                flash_by_job=flash_by_job,
                optimistic_by_job=optimistic_by_job,
            ),
            mimetype="text/html",
        )

    def on_admin_architecture(request: Request) -> Response:
        from meshflow.dna.web.admin.views import render_admin_architecture

        session, redirect = _admin_authorized(request)
        if session is None:
            return redirect
        return Response(
            render_admin_architecture(
                url=lambda path: _app_url(request, path),
                username=session.username,
            ),
            mimetype="text/html",
        )

    def on_admin_job_run(request: Request, job_id: str) -> Response:
        from meshflow.dna.web.admin.jobs import (
            AdminJobMisconfigured,
            UnknownAdminJob,
            enqueue_admin_job,
        )

        session, redirect = _admin_authorized(request)
        if session is None:
            return redirect
        try:
            result = enqueue_admin_job(job_id)
        except UnknownAdminJob:
            return Response("Unknown job", status=404)
        except AdminJobMisconfigured as exc:
            return Response(str(exc), status=503)
        status = str(result.get("status") or "queued")
        if status == "queued":
            flash = "Invoked — badge will move to Running, then Completed or Failed."
        elif status == "dry_run":
            flash = "Dry run only (local) — Lambda was not invoked."
        else:
            flash = f"Invoke returned status {status}."
        if result.get("follow_ons"):
            flash += f" Follow-ons: {', '.join(result['follow_ons'])}."
        params = {"job": job_id, "flash": flash}
        if status == "queued":
            params["invoked"] = "1"
        return _redirect(request, f"/admin?{urlencode(params)}")

    def on_admin_job_status(request: Request, job_id: str) -> Response:
        from meshflow.dna.web.admin.jobs import (
            AdminJobMisconfigured,
            UnknownAdminJob,
            admin_job_status,
        )

        session, redirect = _admin_authorized(request)
        if session is None:
            return redirect
        try:
            payload = admin_job_status(job_id)
        except UnknownAdminJob:
            return Response("Unknown job", status=404)
        except AdminJobMisconfigured as exc:
            return Response(str(exc), status=503)
        return _json_response(payload)

    def on_admin_onboarding(request: Request) -> Response:
        from meshflow.dna.web.admin.onboarding import list_onboarding_clients, render_onboarding_home

        session, redirect = _admin_authorized(request)
        if session is None:
            return redirect
        flash = str(request.args.get("flash", ""))
        return Response(
            render_onboarding_home(
                url=lambda path: _app_url(request, path),
                username=session.username,
                clients=list_onboarding_clients(),
                flash=flash,
            ),
            mimetype="text/html",
        )

    def on_admin_onboarding_new(request: Request) -> Response:
        from meshflow.dna.web.admin.onboarding import create_client_from_form, render_onboarding_wizard

        session, redirect = _admin_authorized(request)
        if session is None:
            return redirect
        url = lambda path: _app_url(request, path)
        if request.method == "GET":
            return Response(
                render_onboarding_wizard(url=url, username=session.username, step=1),
                mimetype="text/html",
            )

        form = {key: str(value) for key, value in request.form.items()}
        try:
            result = create_client_from_form(form)
        except Exception as exc:
            return Response(
                render_onboarding_wizard(
                    url=url,
                    username=session.username,
                    step=1,
                    form_values=form,
                    error=str(exc),
                ),
                mimetype="text/html",
                status=400,
            )
        client = result["client"]
        return _redirect(
            request,
            f"/admin/onboarding/{client['company'].lower()}?environment={client['environment']}&client_id={client['client_id']}&flash=Client+config+saved",
        )

    def _onboarding_company_context(request: Request, company: str) -> tuple[str, str, str]:
        environment = str(request.values.get("environment", "dev")).strip().lower()
        client_id = str(request.values.get("client_id", "")).strip().lower()
        return company.strip().upper(), environment, client_id

    def on_admin_onboarding_detail(request: Request, company: str) -> Response:
        from meshflow.client_registry import ClientRegistry
        from meshflow.dna.web.admin.onboarding import client_deploy_status, render_client_detail

        session, redirect = _admin_authorized(request)
        if session is None:
            return redirect
        company_key, environment, client_id = _onboarding_company_context(request, company)
        registry = ClientRegistry()
        record = registry.get_client(company_key, environment=environment, client_id=client_id or None)
        if record is None:
            return Response("Client not found", status=404)
        status_payload = client_deploy_status(
            company=record.company,
            environment=record.environment,
            client_id=record.client_id,
        )
        return Response(
            render_client_detail(
                url=lambda path: _app_url(request, path),
                username=session.username,
                company=record.company,
                client_id=record.client_id,
                environment=record.environment,
                connector_sources=record.connector_sources,
                status_payload=status_payload,
                flash=str(request.args.get("flash", "")),
                build_id=str(request.args.get("build_id", "")),
            ),
            mimetype="text/html",
        )

    def on_admin_onboarding_deploy(request: Request, company: str) -> Response:
        from meshflow.dna.web.admin.onboarding import trigger_deploy

        session, redirect = _admin_authorized(request)
        if session is None:
            return redirect
        company_key, environment, client_id = _onboarding_company_context(request, company)
        result = trigger_deploy(company=company_key, environment=environment, client_id=client_id)
        build_id = str(result.get("build_id", ""))
        flash = str(result.get("message") or result.get("status") or "deploy triggered")
        params = f"environment={environment}&client_id={client_id}&flash={flash}"
        if build_id:
            params += f"&build_id={build_id}"
        return _redirect(request, f"/admin/onboarding/{company_key.lower()}?{params}")

    def on_admin_onboarding_secrets(request: Request, company: str) -> Response:
        from meshflow.dna.web.admin.onboarding import save_connector_secret

        session, redirect = _admin_authorized(request)
        if session is None:
            return redirect
        company_key, environment, client_id = _onboarding_company_context(request, company)
        source = str(request.form.get("connector_source", "dbc")).strip().lower()
        credentials = {key: str(value) for key, value in request.form.items() if key.isupper()}
        save_connector_secret(
            company=company_key,
            environment=environment,
            source=source,
            credentials=credentials,
        )
        return _redirect(
            request,
            f"/admin/onboarding/{company_key.lower()}?environment={environment}&client_id={client_id}&flash=Secret+saved",
        )

    def on_admin_onboarding_validate(request: Request, company: str) -> Response:
        from meshflow.client_registry import ClientRegistry
        from meshflow.dna.web.admin.onboarding import validate_connector

        session, redirect = _admin_authorized(request)
        if session is None:
            return redirect
        company_key, environment, client_id = _onboarding_company_context(request, company)
        source = str(request.form.get("connector_source", "dbc")).strip().lower()
        credentials = {key: str(value) for key, value in request.form.items() if key.isupper()}
        registry = ClientRegistry()
        record = registry.get_client(company_key, environment=environment, client_id=client_id or None)
        secret_id = registry.secret_name(record, source=source) if record else None
        result = validate_connector(source=source, credentials=credentials, secret_id=secret_id)
        flash = str(result.get("message") or result.get("error") or result)
        return _redirect(
            request,
            f"/admin/onboarding/{company_key.lower()}?environment={environment}&client_id={client_id}&flash={flash}",
        )

    def on_admin_onboarding_qwc(request: Request, company: str) -> Response:
        from meshflow.dna.web.admin.onboarding.handlers import generate_qwc_download

        session, redirect = _admin_authorized(request)
        if session is None:
            return redirect
        soap_url = str(request.args.get("soap_url", "")).strip()
        username = str(request.args.get("username", "")).strip()
        if not soap_url or not username:
            return Response("soap_url and username are required", status=400)
        xml = generate_qwc_download(soap_url=soap_url, username=username)
        return Response(
            xml,
            mimetype="application/xml",
            headers={"Content-Disposition": 'attachment; filename="meshflow.qwc"'},
        )

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

    def _resolve_reporting_override(
        request: Request,
        *,
        portal_settings: DnaSettings,
        is_admin: bool,
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        if not is_admin:
            return None, None
        _ = preview_proposal_id(request)
        return None, None

    def _render_reporting_path(request: Request, path: str) -> Response:
        session, redirect = _authorized(request)
        if redirect is not None:
            return redirect
        client = _client_config(session.client_id)
        portal_settings = _portal_settings(settings, client, environment=environment)
        is_admin = _portal_is_admin(session.username)
        reporting_override, preview_meta = _resolve_reporting_override(
            request, portal_settings=portal_settings, is_admin=is_admin
        )
        page = find_reporting_page(portal_settings, path, override=reporting_override)
        if page is None:
            return Response("Report page is not configured for this client.", status=404, mimetype="text/plain")
        return render_configured_page(
            request,
            settings=portal_settings,
            client=client,
            page=page,
            is_admin=is_admin,
            reporting_override=reporting_override,
            preview_meta=preview_meta,
        )

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
        return _render_reporting_path(request, "/portal")

    def on_portal_executive(request: Request) -> Response:
        return _render_reporting_path(request, "/portal/executive")

    def on_portal_revenue(request: Request) -> Response:
        return _render_reporting_path(request, "/portal/revenue")

    def on_portal_revenue_trend(request: Request) -> Response:
        return _render_reporting_path(request, "/portal/revenue-trend")

    def on_portal_chart_demo(request: Request) -> Response:
        return _render_reporting_path(request, "/portal/chart-demo")

    def on_portal_configured_page(request: Request, subpath: str) -> Response:
        reserved = {"login", "logout", "catalog", "governance", "semantics", "dna", "admin", "api"}
        first = (subpath or "").split("/", 1)[0].strip().lower()
        if first in reserved:
            return Response("Not found", status=404, mimetype="text/plain")
        return _render_reporting_path(request, f"/portal/{subpath}")

    def on_portal_dna(request: Request) -> Response:
        session, redirect = _authorized(request)
        if redirect is not None:
            return redirect
        from meshflow.dna.web.portal.views import render_dna

        client = _client_config(session.client_id)
        return render_dna(
            request,
            settings=settings,
            client=client,
            is_admin=_portal_is_admin(session.username),
        )


    def on_portal_catalog(request: Request) -> Response:
        session, redirect = _authorized(request)
        if redirect is not None:
            return redirect
        from meshflow.dna.web.portal.views import render_catalog

        client = _client_config(session.client_id)
        return render_catalog(
            request,
            settings=settings,
            client=client,
            is_admin=_portal_is_admin(session.username),
        )

    def on_portal_catalog_gold(request: Request) -> Response:
        session, redirect = _authorized(request)
        if redirect is not None:
            return redirect
        from meshflow.dna.web.portal.views import render_catalog_gold

        client = _client_config(session.client_id)
        return render_catalog_gold(
            request,
            settings=settings,
            client=client,
            is_admin=_portal_is_admin(session.username),
        )

    def on_portal_catalog_silver(request: Request) -> Response:
        session, redirect = _authorized(request)
        if redirect is not None:
            return redirect
        from meshflow.dna.web.portal.views import render_catalog_silver

        client = _client_config(session.client_id)
        return render_catalog_silver(
            request,
            settings=settings,
            client=client,
            is_admin=_portal_is_admin(session.username),
        )

    def on_portal_catalog_silver_entity(request: Request, entity: str) -> Response:
        session, redirect = _authorized(request)
        if redirect is not None:
            return redirect
        from meshflow.dna.web.portal.views import render_catalog_silver

        client = _client_config(session.client_id)
        return render_catalog_silver(
            request,
            settings=settings,
            client=client,
            entity=entity,
            is_admin=_portal_is_admin(session.username),
        )

    def on_portal_catalog_output(request: Request, output_id: str) -> Response:
        session, redirect = _authorized(request)
        if redirect is not None:
            return redirect
        from meshflow.dna.web.portal.views import render_catalog_table

        client = _client_config(session.client_id)
        return render_catalog_table(
            request,
            settings=settings,
            client=client,
            output_id=output_id,
            is_admin=_portal_is_admin(session.username),
        )

    def on_portal_governance_config(request: Request) -> Response:
        return _redirect(request, "/portal/governance")

    def on_portal_governance_config_preview_exit(request: Request) -> Response:
        session, redirect = _authorized(request)
        if redirect is not None:
            return redirect
        if not _portal_is_admin(session.username):
            return Response("Forbidden", status=403, mimetype="text/plain")
        response = _redirect(request, "/portal/governance")
        clear_preview_cookie(response)
        return response

    def on_portal_admin_config(request: Request) -> Response:
        return _redirect(request, "/portal/governance")

    def on_portal_admin_config_preview_exit(request: Request) -> Response:
        return _redirect(request, "/portal/governance/config/preview/exit")

    def on_portal_dna_kpi_generator(request: Request) -> Response:
        from meshflow.dna.web.portal.dna_manual_refresh import (
            gold_refresh_status,
            quota_summary as manual_refresh_quota_summary,
            trigger_manual_refresh,
        )
        from meshflow.dna.web.portal.governance_helpers.bedrock_usage import BedrockBudgetExceeded
        from meshflow.dna.web.portal.kpi_generator.service import (
            approve_all_kpi_drafts,
            approve_kpi_draft_group,
            approve_kpi_proposal,
            close_working_kpi_proposals,
            discard_kpi_proposal,
            enqueue_kpi_generation,
            load_kpi_generator_workspace,
            load_kpi_proposal,
            parse_validation_filters,
            publish_all_approved_kpis,
            reject_all_kpi_drafts,
            reject_kpi_draft_group,
            reject_kpi_proposal,
            run_validation,
            save_kpi_governance_draft,
            save_validation_criteria,
            update_kpi_draft_sql,
            validate_kpi_draft_group,
            validation_criteria_from_proposal,
        )
        from meshflow.dna.web.portal.kpi_generator.drafts import proposal_generation_status
        from meshflow.dna.web.portal.views import render_kpi_generator
        from meshflow.dna.workflow import load_production_pack, load_workflow_state

        session, redirect = _authorized(request)
        if redirect is not None:
            return redirect
        client = _client_config(session.client_id)
        portal_settings = _portal_settings(settings, client, environment=environment)
        is_admin = _portal_is_admin(session.username)
        message = str(request.args.get("msg") or "")
        error = str(request.args.get("err") or "")
        active_tab = str(request.args.get("tab") or "generator").strip().lower()
        if active_tab not in {"generator", "review"}:
            active_tab = "generator"
        proposal = None
        validation = None
        pending_drafts: list = []
        approved_drafts: list = []
        proposal_id = str(request.args.get("proposal_id") or "").strip()
        workspace_working = None
        if is_admin and request.method != "POST":
            workspace_working, pending_drafts, approved_drafts = load_kpi_generator_workspace(
                portal_settings
            )
        if proposal_id:
            loaded = load_kpi_proposal(portal_settings, proposal_id)
            if loaded and str(loaded.get("status") or "").strip().lower() == "working":
                proposal = loaded
        elif request.method != "POST" and is_admin:
            proposal = workspace_working
            if proposal:
                proposal_id = str(proposal.get("proposal_id") or "").strip()
        if proposal_generation_status(proposal) == "error":
            error = error or str(proposal.get("generation_error") or "KPI generation failed.")

        if request.method == "POST":
            if not is_admin:
                return Response("Forbidden", status=403, mimetype="text/plain")
            action = str(request.form.get("action", "")).strip()
            try:
                if action == "generate":
                    prior_proposal_id = str(request.form.get("prior_proposal_id") or "").strip()
                    prior_chat_history: list[dict[str, str]] | None = None
                    prior_validation_criteria = None
                    if prior_proposal_id:
                        prior = load_kpi_proposal(portal_settings, prior_proposal_id)
                        if prior and str(prior.get("status") or "").strip().lower() == "working":
                            prior_chat_history = prior.get("chat_history") or []
                            prior_validation_criteria = validation_criteria_from_proposal(prior)
                    proposal = enqueue_kpi_generation(
                        portal_settings,
                        prompt=str(request.form.get("prompt") or ""),
                        client_id=client.client_id,
                        monthly_budget_usd=client.config_assistant_monthly_budget_usd,
                        username=session.username,
                        prior_chat_history=prior_chat_history,
                        prior_validation_criteria=prior_validation_criteria,
                        prior_proposal_id=prior_proposal_id,
                    )
                    params = {"proposal_id": proposal["proposal_id"]}
                    if proposal_generation_status(proposal) != "pending":
                        params["msg"] = (
                            "Draft generated. Validate, then save as a DNA draft for review."
                        )
                    return _redirect(
                        request,
                        f"/portal/dna/kpi-generator?{urlencode(params)}",
                    )
                elif action == "validate":
                    proposal_id = str(request.form.get("proposal_id") or "").strip()
                    try:
                        sql = str(request.form.get("sql") or "").strip()
                        sql_by_layer = {
                            "silver": str(request.form.get("sql_silver") or "").strip(),
                            "gold": str(request.form.get("sql_gold") or "").strip(),
                        }
                        if any(sql_by_layer.values()) or sql:
                            update_kpi_draft_sql(
                                portal_settings,
                                proposal_id=proposal_id,
                                sql=sql,
                                sql_by_layer=sql_by_layer,
                            )
                        filters = parse_validation_filters(
                            request.form.getlist("filter_fact"),
                            request.form.getlist("filter_field"),
                            request.form.getlist("filter_value"),
                        )
                        save_validation_criteria(
                            portal_settings,
                            proposal_id=proposal_id,
                            filters=filters,
                        )
                        run_validation(
                            portal_settings,
                            proposal_id=proposal_id,
                            filters=filters,
                            company=portal_settings.company,
                            environment=environment,
                        )
                        return _kpi_generator_redirect(
                            request,
                            proposal_id=proposal_id,
                            message="Validation query completed.",
                        )
                    except BedrockBudgetExceeded as exc:
                        return _kpi_generator_redirect(
                            request,
                            proposal_id=proposal_id,
                            error=(
                                f"Monthly Bedrock allowance reached "
                                f"(${exc.estimated_cost_usd:.2f} / ${exc.monthly_budget_usd:.2f})."
                            ),
                        )
                    except Exception as exc:  # noqa: BLE001
                        if proposal_id:
                            try:
                                filters = parse_validation_filters(
                                    request.form.getlist("filter_fact"),
                                    request.form.getlist("filter_field"),
                                    request.form.getlist("filter_value"),
                                )
                                save_validation_criteria(
                                    portal_settings,
                                    proposal_id=proposal_id,
                                    filters=filters,
                                )
                            except Exception:  # noqa: BLE001
                                pass
                        return _kpi_generator_redirect(
                            request,
                            proposal_id=proposal_id,
                            error=str(exc),
                        )
                elif action == "save_draft":
                    proposal_id = str(request.form.get("proposal_id") or "").strip()
                    sql = str(request.form.get("sql") or "").strip()
                    sql_by_layer = {
                        "silver": str(request.form.get("sql_silver") or "").strip(),
                        "gold": str(request.form.get("sql_gold") or "").strip(),
                    }
                    if any(sql_by_layer.values()) or sql:
                        update_kpi_draft_sql(
                            portal_settings,
                            proposal_id=proposal_id,
                            sql=sql,
                            sql_by_layer=sql_by_layer,
                        )
                    result = save_kpi_governance_draft(
                        portal_settings,
                        proposal_id=proposal_id,
                        username=session.username,
                    )
                    message = (
                        f"Saved DNA draft v{result['version']} ({result['sql_file']}). "
                        "Review it on the Review Drafts tab."
                    )
                    close_working_kpi_proposals(
                        portal_settings,
                        username=session.username,
                    )
                    return _redirect(
                        request,
                        f"/portal/dna/kpi-generator?{urlencode({'tab': 'review', 'msg': message})}",
                    )
                elif action == "discard_draft":
                    proposal_id = str(request.form.get("proposal_id") or "").strip()
                    if proposal_id:
                        discard_kpi_proposal(
                            portal_settings,
                            proposal_id=proposal_id,
                            username=session.username,
                        )
                    close_working_kpi_proposals(
                        portal_settings,
                        username=session.username,
                    )
                    return _redirect(
                        request,
                        f"/portal/dna/kpi-generator?{urlencode({'msg': 'Draft discarded.'})}",
                    )
                elif action == "validate_integrity":
                    target_key = str(request.form.get("target_key") or "").strip()
                    proposal_ids = [
                        str(pid).strip()
                        for pid in request.form.getlist("proposal_ids")
                        if str(pid).strip()
                    ]
                    validation = validate_kpi_draft_group(
                        portal_settings,
                        target_key=target_key,
                        proposal_ids=proposal_ids,
                        company=portal_settings.company,
                        environment=environment,
                    )
                    if str(validation.get("status") or "").strip().lower() == "passed":
                        message = f"Integrity validation passed for {target_key}."
                    else:
                        errors = validation.get("errors") or ["Integrity validation failed"]
                        error = "; ".join(str(err) for err in errors)
                    active_tab = "review"
                elif action == "approve_group":
                    target_key = str(request.form.get("target_key") or "").strip()
                    proposal_ids = [
                        str(pid).strip()
                        for pid in request.form.getlist("proposal_ids")
                        if str(pid).strip()
                    ]
                    next_version = str(request.form.get("next_sql_version") or "").strip() or None
                    result = approve_kpi_draft_group(
                        portal_settings,
                        target_key=target_key,
                        proposal_ids=proposal_ids,
                        username=session.username,
                        version=next_version,
                        company=portal_settings.company,
                        environment=environment,
                    )
                    message = (
                        f"Approved {len(result.get('approved') or [])} draft(s) in group "
                        f"{target_key}. Move to Publish to materialize tables."
                    )
                    active_tab = "review"
                elif action == "publish_approved":
                    result = publish_all_approved_kpis(
                        portal_settings,
                        client_id=client.client_id,
                        username=session.username,
                        company=portal_settings.company,
                        environment=environment,
                        monthly_limit=client.dna_manual_refresh_monthly_limit,
                    )
                    published_count = len(result.get("published") or [])
                    message = (
                        f"Started DNA refresh for {published_count} approved KPI(s)."
                    )
                    active_tab = "review"
                elif action == "reject_group":
                    target_key = str(request.form.get("target_key") or "").strip()
                    proposal_ids = [
                        str(pid).strip()
                        for pid in request.form.getlist("proposal_ids")
                        if str(pid).strip()
                    ]
                    result = reject_kpi_draft_group(
                        portal_settings,
                        target_key=target_key,
                        proposal_ids=proposal_ids,
                        username=session.username,
                    )
                    message = (
                        f"Rejected {len(result.get('rejected') or [])} draft(s) in group {target_key}."
                    )
                    active_tab = "review"
                elif action == "approve":
                    proposal_id = str(request.form.get("proposal_id") or "").strip()
                    next_version = str(request.form.get("next_sql_version") or "").strip() or None
                    result = approve_kpi_proposal(
                        portal_settings,
                        proposal_id=proposal_id,
                        username=session.username,
                        version=next_version,
                        company=portal_settings.company,
                        environment=environment,
                    )
                    message = (
                        f"Approved and pinned SQL pack v{result['version']} "
                        f"({result['sql_file']}). Publish from Review Drafts to materialize."
                    )
                    proposal = load_kpi_proposal(portal_settings, proposal_id)
                    active_tab = "review"
                elif action == "reject":
                    proposal_id = str(request.form.get("proposal_id") or "").strip()
                    result = reject_kpi_proposal(
                        portal_settings,
                        proposal_id=proposal_id,
                        username=session.username,
                    )
                    if str(result.get("prior_status") or "") == "approved":
                        message = (
                            f"Removed {proposal_id} from the ready-to-publish queue."
                        )
                    else:
                        message = f"Rejected draft {proposal_id}."
                    active_tab = "review"
                elif action == "approve_all":
                    results = approve_all_kpi_drafts(
                        portal_settings,
                        username=session.username,
                    )
                    message = f"Approved {len(results)} KPI draft(s) to production."
                    active_tab = "review"
                elif action == "reject_all":
                    results = reject_all_kpi_drafts(
                        portal_settings,
                        username=session.username,
                    )
                    message = f"Rejected {len(results)} KPI draft(s)."
                    active_tab = "review"
                elif action == "manual_dna_refresh":
                    workflow = load_workflow_state(portal_settings, portal_settings.dna_config_id)
                    pinned_version = str(workflow.get("active_version") or "").strip()
                    if not pinned_version:
                        try:
                            pinned_version = str(
                                load_production_pack(portal_settings).version or ""
                            ).strip()
                        except Exception:  # noqa: BLE001
                            pinned_version = ""
                    if not pinned_version:
                        raise ValueError("No production DNA version is pinned yet.")
                    reporting_company = str(client.reporting_company or "").strip() or company
                    result = trigger_manual_refresh(
                        portal_settings,
                        client_id=client.client_id,
                        username=session.username,
                        pinned_version=pinned_version,
                        company=reporting_company,
                        environment=environment,
                        monthly_limit=client.dna_manual_refresh_monthly_limit,
                    )
                    remaining = int((result.get("quota") or {}).get("remaining") or 0)
                    message = (
                        "DNA refresh started. Silver and gold tables will update when the run "
                        f"completes. {remaining} manual refresh(es) remaining this month."
                    )
                else:
                    error = f"Unknown action {action!r}"
            except BedrockBudgetExceeded as exc:
                error = (
                    f"Monthly Bedrock allowance reached "
                    f"(${exc.estimated_cost_usd:.2f} / ${exc.monthly_budget_usd:.2f})."
                )
            except Exception as exc:  # noqa: BLE001
                error = str(exc)
            if is_admin:
                _, pending_drafts, approved_drafts = load_kpi_generator_workspace(
                    portal_settings
                )

        refresh_status = None
        refresh_quota = None
        if is_admin:
            workflow = load_workflow_state(portal_settings, portal_settings.dna_config_id)
            pinned_version = str(workflow.get("active_version") or "").strip()
            if not pinned_version:
                try:
                    pinned_version = str(load_production_pack(portal_settings).version or "").strip()
                except Exception:  # noqa: BLE001
                    pinned_version = ""
            refresh_status = gold_refresh_status(
                portal_settings,
                pinned_version=pinned_version,
            ).to_dict()
            refresh_quota = manual_refresh_quota_summary(
                portal_settings,
                client_id=client.client_id,
                monthly_limit=client.dna_manual_refresh_monthly_limit,
            ).to_dict()

        return render_kpi_generator(
            request,
            settings=portal_settings,
            client=client,
            is_admin=is_admin,
            proposal=proposal,
            validation=validation,
            message=message,
            error=error,
            active_tab=active_tab,
            pending_drafts=pending_drafts,
            approved_drafts=approved_drafts,
            refresh_status=refresh_status,
            refresh_quota=refresh_quota,
        )


    def on_portal_dna_kpi_generator_status(request: Request) -> Response:
        from meshflow.dna.web.portal.kpi_generator.drafts import proposal_generation_status
        from meshflow.dna.web.portal.kpi_generator.service import load_kpi_proposal

        session, redirect = _authorized(request)
        if redirect is not None:
            return redirect
        if not _portal_is_admin(session.username):
            return _json_response({"error": "forbidden"}, status=403)
        client = _client_config(session.client_id)
        portal_settings = _portal_settings(settings, client, environment=environment)
        proposal_id = str(request.args.get("proposal_id") or "").strip()
        if not proposal_id:
            return _json_response({"error": "proposal_id required"}, status=400)
        proposal = load_kpi_proposal(portal_settings, proposal_id) or {}
        gen_status = proposal_generation_status(proposal) or "complete"
        return _json_response(
            {
                "proposal_id": proposal_id,
                "generation_status": gen_status,
                "error": str(proposal.get("generation_error") or ""),
            }
        )


    def on_portal_governance(request: Request) -> Response:
        from meshflow.dna.web.portal.governance_restore import restore_governance_target
        from meshflow.dna.web.portal.views import render_governance

        session, redirect = _authorized(request)
        if redirect is not None:
            return redirect
        client = _client_config(session.client_id)
        portal_settings = _portal_settings(settings, client, environment=environment)
        is_admin = _portal_is_admin(session.username)
        message = str(request.args.get("msg") or "")
        error = str(request.args.get("err") or "")

        if request.method == "POST":
            if not is_admin:
                return Response("Forbidden", status=403, mimetype="text/plain")
            action = str(request.form.get("action", "")).strip()
            try:
                if action in {"restore_dna", "restore_reporting"}:
                    target = "dna" if action == "restore_dna" else "reporting"
                    source_version = str(request.form.get("source_version", "")).strip()
                    result = restore_governance_target(
                        portal_settings,
                        target=target,
                        source_version=source_version,
                        username=session.username,
                    )
                    label = "DNA" if target == "dna" else "reporting"
                    message = (
                        f"Restored {label} from v{result['restored_from']} "
                        f"as v{result['version']} and pinned production. "
                        "Gold outputs are unchanged until compile and publish."
                    )
                    return _redirect(
                        request,
                        f"/portal/governance?{urlencode({'msg': message})}",
                    )
                raise ValueError(f"Unknown action {action!r}")
            except Exception as exc:  # noqa: BLE001 — surface governance errors in UI
                error = str(exc)

        return render_governance(
            request,
            settings=portal_settings,
            client=client,
            is_admin=is_admin,
            message=message,
            error=error,
        )

    def on_portal_governance_users(request: Request) -> Response:
        from meshflow.dna.web.portal.cognito import (
            PORTAL_ROLE_MEMBER,
            PortalUserAlreadyExists,
            PortalUserLimitExceeded,
            cognito_configured,
            invite_portal_user,
            list_portal_users_for_client,
            set_portal_user_role,
        )

        session, redirect = _authorized(request)
        if redirect is not None:
            return redirect
        if not _portal_is_admin(session.username):
            return Response(
                "Admin access required for Users. "
                "Your Cognito user needs custom:portal_role=admin.",
                status=403,
                mimetype="text/plain",
            )

        client = _client_config(session.client_id)
        portal_settings = _portal_settings(settings, client, environment=environment)
        message = ""
        error = ""
        invites_enabled = cognito_configured()

        if request.method == "POST":
            action = str(request.form.get("action", "")).strip()
            if action == "invite":
                if not invites_enabled:
                    error = "User invites require Cognito authentication."
                else:
                    username = request.form.get("username", "").strip()
                    email = request.form.get("email", "").strip()
                    role = request.form.get("role", PORTAL_ROLE_MEMBER).strip()
                    try:
                        invite_portal_user(
                            username=username,
                            client_id=session.client_id,
                            email=email,
                            company=company,
                            environment=environment,
                            max_users=client.max_users,
                            role=role,
                        )
                        message = f"Invite sent to {email} as {role}."
                    except PortalUserLimitExceeded:
                        error = f"Seat limit reached ({client.max_users} users)."
                    except PortalUserAlreadyExists:
                        error = f"Username {username!r} is already taken."
                    except ValueError as exc:
                        error = str(exc)
                    except RuntimeError as exc:
                        error = str(exc)
            elif action == "set_role":
                if not invites_enabled:
                    error = "Role changes require Cognito authentication."
                else:
                    username = request.form.get("username", "").strip()
                    role = request.form.get("role", PORTAL_ROLE_MEMBER).strip()
                    if username.casefold() == session.username.strip().casefold():
                        error = "You cannot change your own role."
                    else:
                        try:
                            set_portal_user_role(
                                username=username,
                                role=role,
                                company=company,
                                environment=environment,
                            )
                            message = f"Updated {username} to {role}."
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
            is_admin=True,
            settings=portal_settings,
        )

    def on_portal_admin_users(request: Request) -> Response:
        if resolved_ui_mode == "global":
            session, redirect = _authorized(request)
            if redirect is not None:
                return redirect
            reporting_url = _client_reporting_site_url(session.client_id)
            if reporting_url:
                return _external_redirect(f"{reporting_url.rstrip('/')}/governance/users")
        return _redirect(request, "/portal/governance/users")


    def on_portal_source_docs_inspector(request: Request) -> Response:
        return _render_source_docs_inspector(request, source=None)

    def on_portal_source_docs_inspector_source(request: Request, source: str) -> Response:
        return _render_source_docs_inspector(request, source=source)

    def _configured_reference_sources(portal_settings) -> list[str]:
        from meshflow.project_config import get_environment_config, iter_configured_connectors

        try:
            env_cfg = get_environment_config(portal_settings.company, environment)
        except Exception:  # noqa: BLE001
            return [portal_settings.source]
        return [name for name, _cfg in iter_configured_connectors(env_cfg)]

    def _render_source_docs_inspector(request: Request, *, source: str | None) -> Response:
        session, redirect = _authorized(request)
        if redirect is not None:
            return redirect
        from meshflow.dna.web.portal.views import render_source_docs_inspector

        client = _client_config(session.client_id)
        portal_settings = _portal_settings(settings, client, environment=environment)
        return render_source_docs_inspector(
            request,
            settings=portal_settings,
            client=client,
            is_admin=_portal_is_admin(session.username),
            source=source,
            configured_sources=_configured_reference_sources(portal_settings),
        )


    def _semantics_portal_settings(request: Request) -> tuple[DnaSettings, Any, Response | None]:
        if (failure := _api_authorized(request)) is not None:
            return settings, None, failure
        session = session_from_request(request, company=company, environment=environment)
        assert session is not None
        client = _client_config(session.client_id)
        portal_settings = _portal_settings(settings, client, environment=environment)
        return portal_settings, session, None


    def on_api_source_docs_gold(request: Request) -> Response:
        portal_settings, session, failure = _semantics_portal_settings(request)
        if failure is not None:
            return failure
        from meshflow.dna.web.portal.semantics.source_docs_service import source_docs_gold_status

        source = str(request.args.get("source") or "").strip() or None
        return _json_response(source_docs_gold_status(portal_settings, source=source))

    def on_api_source_docs_gold_build(request: Request) -> Response:
        portal_settings, session, failure = _semantics_portal_settings(request)
        if failure is not None:
            return failure
        if not _portal_is_admin(session.username):
            return _json_response({"error": "forbidden"}, status=403)
        from meshflow.dna.web.portal.semantics.source_docs_service import (
            enqueue_source_docs_gold_build,
        )

        body = request.get_json(silent=True) or {}
        source = str(body.get("source") or request.args.get("source") or "").strip() or None
        try:
            result = enqueue_source_docs_gold_build(
                portal_settings,
                company=company,
                environment=environment,
                source=source,
                seed_missing_overlays=bool(body.get("seed_missing_overlays", True)),
                publish_schemas=bool(body.get("publish_schemas", False)),
            )
            status_code = 200
            if result.get("status") == "error":
                status_code = 500
            return _json_response(result, status=status_code)
        except Exception as exc:  # noqa: BLE001
            return _json_response({"error": str(exc)}, status=500)

    def on_api_source_docs_gold_exclude(request: Request) -> Response:
        portal_settings, session, failure = _semantics_portal_settings(request)
        if failure is not None:
            return failure
        if not _portal_is_admin(session.username):
            return _json_response({"error": "forbidden"}, status=403)
        from meshflow.dna.web.portal.semantics.source_docs_service import source_docs_exclude

        body = request.get_json(silent=True) or {}
        try:
            return _json_response(source_docs_exclude(portal_settings, body))
        except ValueError as exc:
            return _json_response({"error": str(exc)}, status=400)
        except Exception as exc:  # noqa: BLE001
            return _json_response({"error": str(exc)}, status=500)

    def on_api_source_docs_gold_undo_exclude(request: Request) -> Response:
        portal_settings, session, failure = _semantics_portal_settings(request)
        if failure is not None:
            return failure
        if not _portal_is_admin(session.username):
            return _json_response({"error": "forbidden"}, status=403)
        from meshflow.dna.web.portal.semantics.source_docs_service import source_docs_undo_exclude

        body = request.get_json(silent=True) or {}
        try:
            return _json_response(source_docs_undo_exclude(portal_settings, body))
        except ValueError as exc:
            return _json_response({"error": str(exc)}, status=400)
        except Exception as exc:  # noqa: BLE001
            return _json_response({"error": str(exc)}, status=500)

    def on_api_source_docs_gold_submit(request: Request) -> Response:
        portal_settings, session, failure = _semantics_portal_settings(request)
        if failure is not None:
            return failure
        if not _portal_is_admin(session.username):
            return _json_response({"error": "forbidden"}, status=403)
        from meshflow.dna.web.portal.semantics.source_docs_service import source_docs_submit_changes

        body = request.get_json(silent=True) or {}
        source = str(body.get("source") or request.args.get("source") or "").strip() or None
        raw_excludes = body.get("excludes")
        excludes = raw_excludes if isinstance(raw_excludes, list) else None
        try:
            result = source_docs_submit_changes(
                portal_settings,
                company=company,
                environment=environment,
                source=source,
                excludes=excludes,
            )
            status_code = 200
            if result.get("status") == "error":
                status_code = 400 if result.get("reason") == "no_pending" else 500
            return _json_response(result, status=status_code)
        except Exception as exc:  # noqa: BLE001
            return _json_response({"error": str(exc)}, status=500)

    def on_api_source_docs_gold_versions(request: Request) -> Response:
        portal_settings, session, failure = _semantics_portal_settings(request)
        if failure is not None:
            return failure
        from meshflow.dna.web.portal.semantics.source_docs_service import source_docs_versions

        source = str(request.args.get("source") or "").strip() or None
        return _json_response(source_docs_versions(portal_settings, source=source))

    def on_api_source_docs_gold_versions_commit(request: Request) -> Response:
        portal_settings, session, failure = _semantics_portal_settings(request)
        if failure is not None:
            return failure
        if not _portal_is_admin(session.username):
            return _json_response({"error": "forbidden"}, status=403)
        from meshflow.dna.web.portal.semantics.source_docs_service import source_docs_commit_version

        body = request.get_json(silent=True) or {}
        source = str(body.get("source") or request.args.get("source") or "").strip() or None
        note = str(body.get("note") or "Submitted").strip() or "Submitted"
        try:
            return _json_response(
                source_docs_commit_version(portal_settings, source=source, note=note)
            )
        except ValueError as exc:
            return _json_response({"error": str(exc)}, status=400)
        except Exception as exc:  # noqa: BLE001
            return _json_response({"error": str(exc)}, status=500)

    def on_api_source_docs_gold_restore(request: Request) -> Response:
        portal_settings, session, failure = _semantics_portal_settings(request)
        if failure is not None:
            return failure
        if not _portal_is_admin(session.username):
            return _json_response({"error": "forbidden"}, status=403)
        from meshflow.dna.web.portal.semantics.source_docs_service import source_docs_restore_version

        body = request.get_json(silent=True) or {}
        source = str(body.get("source") or request.args.get("source") or "").strip() or None
        try:
            version = int(body.get("version"))
        except (TypeError, ValueError):
            return _json_response({"error": "version must be an integer"}, status=400)
        try:
            return _json_response(
                source_docs_restore_version(portal_settings, version=version, source=source)
            )
        except ValueError as exc:
            return _json_response({"error": str(exc)}, status=400)
        except Exception as exc:  # noqa: BLE001
            return _json_response({"error": str(exc)}, status=500)


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

    def on_api_output(request: Request, output_id: str) -> Response:
        if (failure := _api_authorized(request)) is not None:
            return failure
        session = session_from_request(request, company=company, environment=environment)
        assert session is not None
        client = _client_config(session.client_id)
        portal_settings = _portal_settings(settings, client, environment=environment)
        limit_raw = request.args.get("limit")
        limit = int(limit_raw) if limit_raw and limit_raw.isdigit() else None
        sort_column = str(request.args.get("sort_column") or "").strip() or None
        sort_direction = str(request.args.get("sort_direction") or "desc").strip().lower()
        try:
            return _json_response(
                fetch_output_rows(
                    portal_settings,
                    output_id,
                    limit=limit,
                    sort_column=sort_column,
                    sort_direction=sort_direction,
                )
            )
        except ValueError as exc:
            return _json_response({"error": str(exc)}, status=400)

    def on_api_reporting_pages(request: Request) -> Response:
        if (failure := _api_authorized(request)) is not None:
            return failure
        session = session_from_request(request, company=company, environment=environment)
        assert session is not None
        client = _client_config(session.client_id)
        portal_settings = _portal_settings(settings, client, environment=environment)
        return _json_response({"pages": list_reporting_pages_json(portal_settings)})

    def on_api_reporting_page(request: Request, subpath: str) -> Response:
        if (failure := _api_authorized(request)) is not None:
            return failure
        session = session_from_request(request, company=company, environment=environment)
        assert session is not None
        client = _client_config(session.client_id)
        portal_settings = _portal_settings(settings, client, environment=environment)
        path = f"/portal/{subpath.strip('/')}"
        try:
            return _json_response(fetch_page_data(portal_settings, path))
        except KeyError:
            return _json_response({"error": "page_not_found", "path": path}, status=404)

    def on_api_reporting_catalog(request: Request) -> Response:
        if (failure := _api_authorized(request)) is not None:
            return failure
        session = session_from_request(request, company=company, environment=environment)
        assert session is not None
        client = _client_config(session.client_id)
        portal_settings = _portal_settings(settings, client, environment=environment)
        return _json_response(build_reporting_binding_catalog(portal_settings))


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
    elif resolved_ui_mode == "admin":
        enabled_endpoints = ADMIN_UI_ENDPOINTS

    endpoints = {
        "landing": on_landing,
        "platform": on_platform,
        "pricing": on_pricing,
        "admin_home": on_admin_home,
        "admin_login": on_admin_login,
        "admin_logout": on_admin_logout,
        "admin_architecture": on_admin_architecture,
        "admin_job_run": on_admin_job_run,
        "admin_job_status": on_admin_job_status,
        "admin_onboarding": on_admin_onboarding,
        "admin_onboarding_new": on_admin_onboarding_new,
        "admin_onboarding_detail": on_admin_onboarding_detail,
        "admin_onboarding_deploy": on_admin_onboarding_deploy,
        "admin_onboarding_secrets": on_admin_onboarding_secrets,
        "admin_onboarding_validate": on_admin_onboarding_validate,
        "admin_onboarding_qwc": on_admin_onboarding_qwc,
        "portal_login": on_portal_login,
        "portal_logout": on_portal_logout,
        "portal_home": on_portal_home,
        "portal_executive": on_portal_executive,
        "portal_revenue": on_portal_revenue,
        "portal_revenue_trend": on_portal_revenue_trend,
        "portal_chart_demo": on_portal_chart_demo,
        "portal_configured_page": on_portal_configured_page,
        "portal_catalog": on_portal_catalog,
        "portal_catalog_output": on_portal_catalog_output,
        "portal_catalog_gold": on_portal_catalog_gold,
        "portal_catalog_silver": on_portal_catalog_silver,
        "portal_catalog_silver_entity": on_portal_catalog_silver_entity,
        "portal_dna": on_portal_dna,
        "portal_dna_kpi_generator": on_portal_dna_kpi_generator,
        "portal_dna_kpi_generator_status": on_portal_dna_kpi_generator_status,
        "portal_governance": on_portal_governance,
        "portal_governance_users": on_portal_governance_users,
        "portal_governance_config": on_portal_governance_config,
        "portal_governance_config_preview_exit": on_portal_governance_config_preview_exit,
        "portal_admin_config": on_portal_admin_config,
        "portal_admin_config_preview_exit": on_portal_admin_config_preview_exit,
        "portal_admin_users": on_portal_admin_users,
        "portal_source_docs_inspector": on_portal_source_docs_inspector,
        "portal_source_docs_inspector_source": on_portal_source_docs_inspector_source,
        "static": on_static,
        "api_pack": on_api_pack,
        "api_manifest": on_api_manifest,
        "api_output": on_api_output,
        "api_reporting_pages": on_api_reporting_pages,
        "api_reporting_page": on_api_reporting_page,
        "api_reporting_catalog": on_api_reporting_catalog,
        "api_source_docs_gold": on_api_source_docs_gold,
        "api_source_docs_gold_build": on_api_source_docs_gold_build,
        "api_source_docs_gold_exclude": on_api_source_docs_gold_exclude,
        "api_source_docs_gold_undo_exclude": on_api_source_docs_gold_undo_exclude,
        "api_source_docs_gold_submit": on_api_source_docs_gold_submit,
        "api_source_docs_gold_versions": on_api_source_docs_gold_versions,
        "api_source_docs_gold_versions_commit": on_api_source_docs_gold_versions_commit,
        "api_source_docs_gold_restore": on_api_source_docs_gold_restore,
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
        except NotFound:
            response = Response("Not found", status=404)
        except Exception as exc:  # noqa: BLE001 — surface errors in dev UI
            response = _json_response({"error": str(exc)}, status=500)
        return response(environ, start_response)

    application.load_portal_users = lambda: load_portal_users(company=company, environment=environment)  # type: ignore[attr-defined]
    return application


def run_server(
    settings: DnaSettings,
    *,
    host: str = "127.0.0.1",
    port: int = 8080,
    reload: bool = False,
) -> None:
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
    if reload:
        print("Dev reload enabled — code changes restart the server automatically.")
    elif os.getenv("HIVEFLOW_DEV", "").strip().lower() in {"1", "true", "yes"}:
        reload = True
        print("Dev reload enabled — code changes restart the server automatically.")
    run_simple(host, port, app, use_reloader=reload, use_debugger=reload)
