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
from meshflow.dna.web.portal.config_assistant.gold_bindings import build_reporting_binding_catalog
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
    "/semantics": "/portal/semantics",
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
        "portal_dna_mappings",
        "portal_dna_engine",
        "portal_governance",
        "portal_governance_users",
        "portal_governance_config",
        "portal_governance_config_preview_exit",
        "portal_semantics",
        "portal_semantic_builder",
        "portal_semantic_builder_keys",
        "portal_semantic_builder_relationships",
        "portal_semantic_builder_tags",
        "portal_semantic_builder_decisions",
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
        "api_config_assistant",
        "api_semantics_concepts",
        "api_semantics_entities",
        "api_semantics_entity",
        "api_semantics_draft",
        "api_semantics_publish",
        "api_semantics_discard",
        "api_semantics_custom_concepts",
        "portal_semantics_entity",
        "api_semantic_model",
        "api_semantic_model_builder_ui",
        "api_semantic_model_init",
        "api_semantic_model_publish",
        "api_semantic_model_discard",
        "api_semantic_model_discard_step",
        "api_semantic_model_relationship_approve",
        "api_semantic_model_relationship_reject",
        "api_semantic_model_relationship_propose",
        "api_semantic_model_entity_approve",
        "api_semantic_model_entity_reject",
        "api_semantic_model_entity_propose",
        "api_semantic_model_entity_pk_approve",
        "api_semantic_model_entity_pk_reject",
        "api_semantic_model_entity_pk_propose",
        "api_semantic_model_fk_approve",
        "api_semantic_model_fk_reject",
        "api_semantic_model_fk_propose",
        "api_semantic_model_complete_step",
        "api_semantic_model_question_resolve",
        "api_semantic_model_attributes",
        "api_semantic_model_attribute_approve",
        "api_semantic_model_attribute_reject",
        "api_semantic_model_attribute_propose",
        "api_semantic_model_approve_all_keys",
        "api_semantic_model_approve_all_primary_keys",
        "api_semantic_model_approve_all_foreign_keys",
        "api_semantic_model_approve_all_tags",
        "api_semantic_model_approve_all_structure",
        "api_semantic_model_assistant",
        "api_semantic_model_builder_primary_key",
        "api_semantic_model_builder_foreign_key",
        "api_semantic_model_builder_relationship",
        "api_semantic_model_builder_column_tag",
        "api_semantic_model_builder_generate_relationships",
        "api_semantic_model_builder_rerun_tagging",
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


def _governance_redirect(
    request: Request,
    *,
    update_tab: str = "assist",
    message: str = "",
    error: str = "",
) -> Response:
    """Post/Redirect/Get so browser refresh does not replay the last form POST."""
    params: dict[str, str] = {"update": update_tab if update_tab in {"assist", "manual"} else "assist"}
    if message:
        params["msg"] = message
    if error:
        params["err"] = error
    # Keep the viewport on the update section after form POST redirects.
    return _redirect(request, f"/portal/dna/engine?{urlencode(params)}#governance-update")


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
                Rule("/portal/dna/mappings", endpoint="portal_dna_mappings"),
                Rule("/portal/dna/engine", endpoint="portal_dna_engine", methods=["GET", "POST"]),
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
                Rule("/portal/semantics/builder", endpoint="portal_semantic_builder"),
                Rule("/portal/semantics/builder/keys", endpoint="portal_semantic_builder_keys"),
                Rule(
                    "/portal/semantics/builder/relationships",
                    endpoint="portal_semantic_builder_relationships",
                ),
                Rule("/portal/semantics/builder/tags", endpoint="portal_semantic_builder_tags"),
                Rule(
                    "/portal/semantics/builder/decisions",
                    endpoint="portal_semantic_builder_decisions",
                ),
                Rule("/portal/semantics", endpoint="portal_semantics"),
                Rule("/portal/semantics/<entity>", endpoint="portal_semantics_entity"),
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
                Rule("/api/config-assistant", endpoint="api_config_assistant"),
                Rule("/api/semantics/concepts", endpoint="api_semantics_concepts"),
                Rule("/api/semantics/entities", endpoint="api_semantics_entities"),
                Rule("/api/semantics/entities/<entity>", endpoint="api_semantics_entity"),
                Rule("/api/semantics/draft", endpoint="api_semantics_draft", methods=["GET", "PUT"]),
                Rule("/api/semantics/publish", endpoint="api_semantics_publish", methods=["POST"]),
                Rule("/api/semantics/discard", endpoint="api_semantics_discard", methods=["POST"]),
                Rule(
                    "/api/semantics/custom-concepts",
                    endpoint="api_semantics_custom_concepts",
                    methods=["POST"],
                ),
                Rule("/api/semantic-model", endpoint="api_semantic_model"),
                Rule("/api/semantic-model/builder-ui", endpoint="api_semantic_model_builder_ui"),
                Rule("/api/semantic-model/init", endpoint="api_semantic_model_init", methods=["POST"]),
                Rule("/api/semantic-model/publish", endpoint="api_semantic_model_publish", methods=["POST"]),
                Rule("/api/semantic-model/discard", endpoint="api_semantic_model_discard", methods=["POST"]),
                Rule(
                    "/api/semantic-model/discard-step",
                    endpoint="api_semantic_model_discard_step",
                    methods=["POST"],
                ),
                Rule(
                    "/api/semantic-model/relationships/<relationship_id>/approve",
                    endpoint="api_semantic_model_relationship_approve",
                    methods=["POST"],
                ),
                Rule(
                    "/api/semantic-model/relationships/<relationship_id>/reject",
                    endpoint="api_semantic_model_relationship_reject",
                    methods=["POST"],
                ),
                Rule(
                    "/api/semantic-model/relationships/<relationship_id>/propose",
                    endpoint="api_semantic_model_relationship_propose",
                    methods=["POST"],
                ),
                Rule(
                    "/api/semantic-model/entities/<entity_id>/approve",
                    endpoint="api_semantic_model_entity_approve",
                    methods=["POST"],
                ),
                Rule(
                    "/api/semantic-model/entities/<entity_id>/reject",
                    endpoint="api_semantic_model_entity_reject",
                    methods=["POST"],
                ),
                Rule(
                    "/api/semantic-model/entities/<entity_id>/propose",
                    endpoint="api_semantic_model_entity_propose",
                    methods=["POST"],
                ),
                Rule(
                    "/api/semantic-model/entities/<entity_id>/primary-key/approve",
                    endpoint="api_semantic_model_entity_pk_approve",
                    methods=["POST"],
                ),
                Rule(
                    "/api/semantic-model/entities/<entity_id>/primary-key/reject",
                    endpoint="api_semantic_model_entity_pk_reject",
                    methods=["POST"],
                ),
                Rule(
                    "/api/semantic-model/entities/<entity_id>/primary-key/propose",
                    endpoint="api_semantic_model_entity_pk_propose",
                    methods=["POST"],
                ),
                Rule(
                    "/api/semantic-model/attributes/<entity>/<column>/foreign-key/approve",
                    endpoint="api_semantic_model_fk_approve",
                    methods=["POST"],
                ),
                Rule(
                    "/api/semantic-model/attributes/<entity>/<column>/foreign-key/reject",
                    endpoint="api_semantic_model_fk_reject",
                    methods=["POST"],
                ),
                Rule(
                    "/api/semantic-model/attributes/<entity>/<column>/foreign-key/propose",
                    endpoint="api_semantic_model_fk_propose",
                    methods=["POST"],
                ),
                Rule(
                    "/api/semantic-model/workflow/complete-step",
                    endpoint="api_semantic_model_complete_step",
                    methods=["POST"],
                ),
                Rule(
                    "/api/semantic-model/builder/primary-key",
                    endpoint="api_semantic_model_builder_primary_key",
                    methods=["POST"],
                ),
                Rule(
                    "/api/semantic-model/builder/foreign-key",
                    endpoint="api_semantic_model_builder_foreign_key",
                    methods=["POST"],
                ),
                Rule(
                    "/api/semantic-model/builder/relationship",
                    endpoint="api_semantic_model_builder_relationship",
                    methods=["POST"],
                ),
                Rule(
                    "/api/semantic-model/builder/column-tag",
                    endpoint="api_semantic_model_builder_column_tag",
                    methods=["POST"],
                ),
                Rule(
                    "/api/semantic-model/builder/generate-relationships",
                    endpoint="api_semantic_model_builder_generate_relationships",
                    methods=["POST"],
                ),
                Rule(
                    "/api/semantic-model/builder/rerun-tagging",
                    endpoint="api_semantic_model_builder_rerun_tagging",
                    methods=["POST"],
                ),
                Rule(
                    "/api/semantic-model/questions/<question_id>/resolve",
                    endpoint="api_semantic_model_question_resolve",
                    methods=["POST"],
                ),
                Rule("/api/semantic-model/attributes", endpoint="api_semantic_model_attributes"),
                Rule(
                    "/api/semantic-model/attributes/<entity>/<column>/approve",
                    endpoint="api_semantic_model_attribute_approve",
                    methods=["POST"],
                ),
                Rule(
                    "/api/semantic-model/attributes/<entity>/<column>/reject",
                    endpoint="api_semantic_model_attribute_reject",
                    methods=["POST"],
                ),
                Rule(
                    "/api/semantic-model/attributes/<entity>/<column>/propose",
                    endpoint="api_semantic_model_attribute_propose",
                    methods=["POST"],
                ),
                Rule(
                    "/api/semantic-model/approve-all-keys",
                    endpoint="api_semantic_model_approve_all_keys",
                    methods=["POST"],
                ),
                Rule(
                    "/api/semantic-model/approve-all-primary-keys",
                    endpoint="api_semantic_model_approve_all_primary_keys",
                    methods=["POST"],
                ),
                Rule(
                    "/api/semantic-model/approve-all-foreign-keys",
                    endpoint="api_semantic_model_approve_all_foreign_keys",
                    methods=["POST"],
                ),
                Rule(
                    "/api/semantic-model/approve-all-tags",
                    endpoint="api_semantic_model_approve_all_tags",
                    methods=["POST"],
                ),
                Rule(
                    "/api/semantic-model/approve-all-structure",
                    endpoint="api_semantic_model_approve_all_structure",
                    methods=["POST"],
                ),
                Rule(
                    "/api/semantic-model/assistant",
                    endpoint="api_semantic_model_assistant",
                    methods=["POST"],
                ),
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
        proposal_id = preview_proposal_id(request)
        if not proposal_id:
            return None, None
        try:
            from meshflow.dna.web.portal.config_assistant import load_proposal_reporting
            from meshflow.dna.web.portal.config_assistant.proposals import load_proposal

            reporting = load_proposal_reporting(portal_settings, proposal_id)
            proposal = load_proposal(portal_settings, proposal_id)
            meta = (proposal or {}).get("meta") or {}
            return reporting, {
                "proposal_id": proposal_id,
                "next_version": str(meta.get("next_version") or ""),
            }
        except FileNotFoundError:
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

    def on_portal_dna_mappings(request: Request) -> Response:
        session, redirect = _authorized(request)
        if redirect is not None:
            return redirect
        from meshflow.dna.web.portal.views import render_semantic_mappings

        client = _client_config(session.client_id)
        return render_semantic_mappings(
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
        if request.method == "GET":
            return _redirect(request, "/portal/dna/engine?update=assist")
        return on_portal_dna_engine(request)

    def on_portal_governance_config_preview_exit(request: Request) -> Response:
        session, redirect = _authorized(request)
        if redirect is not None:
            return redirect
        if not _portal_is_admin(session.username):
            return Response("Forbidden", status=403, mimetype="text/plain")
        response = _redirect(request, "/portal/dna/engine?update=assist")
        clear_preview_cookie(response)
        return response

    def on_portal_admin_config(request: Request) -> Response:
        return _redirect(request, "/portal/dna/engine?update=assist")

    def on_portal_admin_config_preview_exit(request: Request) -> Response:
        return _redirect(request, "/portal/governance/config/preview/exit")

    def on_portal_dna_engine(request: Request) -> Response:
        from meshflow.dna.web.portal.config_assistant import (
            approve_proposal,
            deny_proposal,
            load_base_configs,
            proposal_view,
            submit_chat_turn,
        )
        from meshflow.dna.web.portal.config_assistant.service import (
            cancel_running_proposal,
            ensure_running_chat_progress,
        )
        from meshflow.dna.web.portal.views import (
            is_config_assistant_action,
            render_dna_engine,
            save_governance_dna_from_portal,
            save_governance_reporting_from_portal,
        )
        from meshflow.dna.workflow import load_production_pack, load_workflow_state

        session, redirect = _authorized(request)
        if redirect is not None:
            return redirect
        client = _client_config(session.client_id)
        portal_settings = _portal_settings(settings, client, environment=environment)
        is_admin = _portal_is_admin(session.username)
        message = str(request.args.get("msg") or "")
        error = str(request.args.get("err") or "")
        dna_yaml_override = None
        reporting_yaml_override = None
        dna_version_override = None
        reporting_version_override = None
        update_tab = "manual" if request.args.get("update") == "manual" else "assist"

        if request.method == "POST":
            if not is_admin:
                return Response("Forbidden", status=403, mimetype="text/plain")
            action = str(request.form.get("action", "")).strip()
            proposal_id = str(request.form.get("proposal_id", "")).strip()
            update_tab = "assist" if is_config_assistant_action(action) else "manual"
            try:
                if action in {"manual_draft_dna", "manual_approve_dna"}:
                    dna_yaml_override = request.form.get("dna_yaml", "")
                    dna_version = str(request.form.get("dna_version", "")).strip()
                    dna_version_override = dna_version
                    result = save_governance_dna_from_portal(
                        portal_settings,
                        dna_yaml=str(dna_yaml_override or ""),
                        dna_version=dna_version,
                        pin_production=action == "manual_approve_dna",
                        approver=session.username,
                    )
                    verb = (
                        "Approved and pinned DNA"
                        if action == "manual_approve_dna"
                        else "Saved DNA draft"
                    )
                    message = f"{verb} v{result['dna_version']}."
                    if result.get("warning"):
                        message = f"{message} {result['warning']}"
                    return _governance_redirect(
                        request, update_tab="manual", message=message
                    )
                elif action in {"manual_draft_reporting", "manual_approve_reporting"}:
                    reporting_yaml_override = request.form.get("reporting_yaml", "")
                    reporting_version = str(request.form.get("reporting_version", "")).strip()
                    reporting_version_override = reporting_version
                    result = save_governance_reporting_from_portal(
                        portal_settings,
                        reporting_yaml=str(reporting_yaml_override or ""),
                        reporting_version=reporting_version,
                        pin_production=action == "manual_approve_reporting",
                        approver=session.username,
                    )
                    verb = (
                        "Approved and pinned reporting"
                        if action == "manual_approve_reporting"
                        else "Saved reporting draft"
                    )
                    message = f"{verb} v{result['reporting_version']}."
                    if result.get("warning"):
                        message = f"{message} {result['warning']}"
                    return _governance_redirect(
                        request, update_tab="manual", message=message
                    )
                elif action == "manual_dna_refresh":
                    workflow = load_workflow_state(portal_settings, portal_settings.dna_config_id)
                    pinned_version = str(workflow.get("active_version") or "").strip()
                    if not pinned_version:
                        try:
                            pinned_version = str(load_production_pack(portal_settings).version or "").strip()
                        except Exception:  # noqa: BLE001
                            pinned_version = ""
                    if not pinned_version:
                        raise ValueError("No production DNA version is pinned yet.")
                    from meshflow.dna.web.portal.dna_manual_refresh import trigger_manual_refresh

                    reporting_company = (
                        str(client.reporting_company or "").strip() or company
                    )
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
                        "DNA gold refresh started. Certified tables will update when the run "
                        f"completes. {remaining} manual refresh(es) remaining this month."
                    )
                    return _governance_redirect(
                        request, update_tab="assist", message=message
                    )
                elif action == "chat":
                    user_message = str(request.form.get("message", "")).strip()
                    if not user_message:
                        raise ValueError("Message is required")
                    view = submit_chat_turn(
                        portal_settings,
                        user_message=user_message,
                        username=session.username,
                        client_id=client.client_id,
                        monthly_budget_usd=client.config_assistant_monthly_budget_usd,
                    )
                    if view.get("meta", {}).get("status") == "running":
                        message = "Assistant is working — chat updates automatically."
                    else:
                        message = "Assistant updated the open proposal."
                    return _governance_redirect(
                        request, update_tab="assist", message=message
                    )
                elif action == "cancel_running":
                    if not proposal_id:
                        raise ValueError("proposal_id is required")
                    cancel_running_proposal(
                        portal_settings,
                        proposal_id=proposal_id,
                        username=session.username,
                    )
                    return _governance_redirect(
                        request,
                        update_tab="assist",
                        message="Cancelled the in-progress assistant run.",
                    )
                elif action == "preview":
                    if not proposal_id:
                        raise ValueError("proposal_id is required")
                    preview_response = _redirect(request, "/portal")
                    set_preview_cookie(preview_response, proposal_id)
                    return preview_response
                elif action in {"approve_dna", "approve_reporting"}:
                    if not proposal_id:
                        raise ValueError("proposal_id is required")
                    target = "dna" if action == "approve_dna" else "reporting"
                    version_field = (
                        "next_dna_version" if target == "dna" else "next_reporting_version"
                    )
                    next_version = str(request.form.get(version_field, "")).strip() or None
                    result = approve_proposal(
                        portal_settings,
                        proposal_id,
                        username=session.username,
                        target=target,
                        next_version=next_version,
                    )
                    label = "DNA" if target == "dna" else "reporting"
                    message = f"Approved and pinned {label} v{result['version']}."
                    redirect_response = _governance_redirect(
                        request, update_tab="assist", message=message
                    )
                    if result.get("fully_resolved"):
                        clear_preview_cookie(redirect_response)
                    return redirect_response
                elif action in {"deny", "deny_dna", "deny_reporting"}:
                    if not proposal_id:
                        raise ValueError("proposal_id is required")
                    deny_target = None
                    if action == "deny_dna":
                        deny_target = "dna"
                    elif action == "deny_reporting":
                        deny_target = "reporting"
                    result = deny_proposal(
                        portal_settings,
                        proposal_id,
                        username=session.username,
                        target=deny_target,
                    )
                    if deny_target is None:
                        message = "Proposal denied."
                    else:
                        label = "DNA" if deny_target == "dna" else "reporting"
                        message = f"Denied {label} changes."
                    redirect_response = _governance_redirect(
                        request, update_tab="assist", message=message
                    )
                    if result.get("fully_resolved"):
                        clear_preview_cookie(redirect_response)
                    return redirect_response
                else:
                    raise ValueError(f"Unknown action {action!r}")
            except Exception as exc:  # noqa: BLE001 — surface governance errors in UI
                error = str(exc)
                if is_config_assistant_action(action) or action == "manual_dna_refresh":
                    return _governance_redirect(
                        request, update_tab="assist", error=error
                    )

        proposal_view_data = None
        base_version = ""
        if is_admin:
            try:
                base = load_base_configs(portal_settings)
                base_version = base["base_version"]
                active = ensure_running_chat_progress(portal_settings)
                proposal_view_data = (
                    proposal_view(portal_settings, active, base) if active else None
                )
                if proposal_view_data and update_tab == "manual":
                    status = str(proposal_view_data.get("meta", {}).get("status") or "")
                    if status in {"open", "running"}:
                        update_tab = "assist"
            except FileNotFoundError:
                proposal_view_data = None
                base_version = ""

        return render_dna_engine(
            request,
            settings=portal_settings,
            client=client,
            is_admin=is_admin,
            message=message,
            error=error,
            dna_yaml_override=dna_yaml_override,
            reporting_yaml_override=reporting_yaml_override,
            dna_version_override=dna_version_override,
            reporting_version_override=reporting_version_override,
            proposal_view_data=proposal_view_data,
            base_version=base_version,
            update_tab=update_tab,
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

    def on_portal_semantic_builder(request: Request) -> Response:
        session, redirect = _authorized(request)
        if redirect is not None:
            return redirect
        from meshflow.dna.web.portal.views import render_semantic_builder

        client = _client_config(session.client_id)
        portal_settings = _portal_settings(settings, client, environment=environment)
        return render_semantic_builder(
            request,
            settings=portal_settings,
            client=client,
            is_admin=_portal_is_admin(session.username),
            page_step=None,
        )

    def on_portal_semantic_builder_keys(request: Request) -> Response:
        session, redirect = _authorized(request)
        if redirect is not None:
            return redirect
        from meshflow.dna.web.portal.views import render_semantic_builder

        client = _client_config(session.client_id)
        portal_settings = _portal_settings(settings, client, environment=environment)
        return render_semantic_builder(
            request,
            settings=portal_settings,
            client=client,
            is_admin=_portal_is_admin(session.username),
            page_step="keys",
        )

    def on_portal_semantic_builder_relationships(request: Request) -> Response:
        session, redirect = _authorized(request)
        if redirect is not None:
            return redirect
        from meshflow.dna.web.portal.views import render_semantic_builder

        client = _client_config(session.client_id)
        portal_settings = _portal_settings(settings, client, environment=environment)
        return render_semantic_builder(
            request,
            settings=portal_settings,
            client=client,
            is_admin=_portal_is_admin(session.username),
            page_step="relationships",
        )

    def on_portal_semantic_builder_tags(request: Request) -> Response:
        session, redirect = _authorized(request)
        if redirect is not None:
            return redirect
        from meshflow.dna.web.portal.views import render_semantic_builder

        client = _client_config(session.client_id)
        portal_settings = _portal_settings(settings, client, environment=environment)
        return render_semantic_builder(
            request,
            settings=portal_settings,
            client=client,
            is_admin=_portal_is_admin(session.username),
            page_step="tags",
        )

    def on_portal_semantic_builder_decisions(request: Request) -> Response:
        session, redirect = _authorized(request)
        if redirect is not None:
            return redirect
        from meshflow.dna.web.portal.views import render_semantic_builder

        client = _client_config(session.client_id)
        portal_settings = _portal_settings(settings, client, environment=environment)
        return render_semantic_builder(
            request,
            settings=portal_settings,
            client=client,
            is_admin=_portal_is_admin(session.username),
            page_step="decisions",
        )

    def on_portal_semantics(request: Request) -> Response:
        session, redirect = _authorized(request)
        if redirect is not None:
            return redirect
        from meshflow.dna.web.portal.views import render_semantics

        client = _client_config(session.client_id)
        portal_settings = _portal_settings(settings, client, environment=environment)
        return render_semantics(
            request,
            settings=portal_settings,
            client=client,
            is_admin=_portal_is_admin(session.username),
        )

    def on_portal_semantics_entity(request: Request, entity: str) -> Response:
        session, redirect = _authorized(request)
        if redirect is not None:
            return redirect
        from meshflow.dna.web.portal.views import render_semantics

        client = _client_config(session.client_id)
        portal_settings = _portal_settings(settings, client, environment=environment)
        return render_semantics(
            request,
            settings=portal_settings,
            client=client,
            entity=entity,
            is_admin=_portal_is_admin(session.username),
        )

    def _semantics_portal_settings(request: Request) -> tuple[DnaSettings, Any, Response | None]:
        if (failure := _api_authorized(request)) is not None:
            return settings, None, failure
        session = session_from_request(request, company=company, environment=environment)
        assert session is not None
        client = _client_config(session.client_id)
        portal_settings = _portal_settings(settings, client, environment=environment)
        return portal_settings, session, None

    def on_api_semantics_concepts(request: Request) -> Response:
        portal_settings, _session, failure = _semantics_portal_settings(request)
        if failure is not None:
            return failure
        from meshflow.dna.web.portal.semantics.api import concepts_payload

        return _json_response(concepts_payload(portal_settings))

    def on_api_semantics_entities(request: Request) -> Response:
        portal_settings, _session, failure = _semantics_portal_settings(request)
        if failure is not None:
            return failure
        from meshflow.dna.web.portal.semantics.api import entities_payload

        return _json_response(entities_payload(portal_settings))

    def on_api_semantics_entity(request: Request, entity: str) -> Response:
        portal_settings, _session, failure = _semantics_portal_settings(request)
        if failure is not None:
            return failure
        from meshflow.dna.web.portal.semantics.api import entity_detail_payload

        try:
            return _json_response(entity_detail_payload(portal_settings, entity))
        except ValueError as exc:
            return _json_response({"error": str(exc)}, status=400)

    def on_api_semantics_draft(request: Request) -> Response:
        portal_settings, session, failure = _semantics_portal_settings(request)
        if failure is not None:
            return failure
        from meshflow.dna.field_semantics import draft_differs_from_production, save_field_semantics_draft
        from meshflow.dna.web.portal.semantics.api import draft_payload

        if request.method == "GET":
            return _json_response(draft_payload(portal_settings))

        if not _portal_is_admin(session.username):
            return _json_response({"error": "forbidden"}, status=403)
        try:
            payload = request.get_json(silent=True) or {}
            saved = save_field_semantics_draft(
                portal_settings,
                payload,
                username=session.username,
            )
            return _json_response(
                {
                    "draft": saved,
                    "draft_differs_from_production": draft_differs_from_production(portal_settings),
                }
            )
        except ValueError as exc:
            return _json_response({"error": str(exc)}, status=400)

    def on_api_semantics_publish(request: Request) -> Response:
        portal_settings, session, failure = _semantics_portal_settings(request)
        if failure is not None:
            return failure
        if not _portal_is_admin(session.username):
            return _json_response({"error": "forbidden"}, status=403)
        from meshflow.dna.field_semantics import publish_field_semantics

        try:
            published = publish_field_semantics(
                portal_settings,
                username=session.username,
            )
            return _json_response(published)
        except ValueError as exc:
            return _json_response({"error": str(exc)}, status=400)

    def on_api_semantics_discard(request: Request) -> Response:
        portal_settings, session, failure = _semantics_portal_settings(request)
        if failure is not None:
            return failure
        if not _portal_is_admin(session.username):
            return _json_response({"error": "forbidden"}, status=403)
        from meshflow.dna.field_semantics import discard_field_semantics_draft

        try:
            draft = discard_field_semantics_draft(
                portal_settings,
                username=session.username,
            )
            return _json_response({"draft": draft})
        except ValueError as exc:
            return _json_response({"error": str(exc)}, status=400)

    def on_api_semantics_custom_concepts(request: Request) -> Response:
        portal_settings, session, failure = _semantics_portal_settings(request)
        if failure is not None:
            return failure
        if not _portal_is_admin(session.username):
            return _json_response({"error": "forbidden"}, status=403)
        from meshflow.dna.field_semantics import (
            load_field_semantics_draft,
            save_field_semantics_draft,
            slugify_concept_id,
        )

        body = request.get_json(silent=True) or {}
        label = str(body.get("label") or "").strip()
        category = str(body.get("category") or "").strip().lower()
        if not label or not category:
            return _json_response({"error": "label and category are required"}, status=400)
        try:
            concept_id = slugify_concept_id(label)
            draft = load_field_semantics_draft(portal_settings)
            custom = list(draft.get("custom_concepts") or [])
            if any(str(item.get("id") or "") == concept_id for item in custom):
                return _json_response({"error": f"Custom concept {concept_id!r} already exists"}, status=400)
            custom.append({"id": concept_id, "label": label, "category": category})
            draft["custom_concepts"] = custom
            saved = save_field_semantics_draft(
                portal_settings,
                draft,
                username=session.username,
            )
            return _json_response({"custom_concepts": saved.get("custom_concepts") or []})
        except ValueError as exc:
            return _json_response({"error": str(exc)}, status=400)

    def _semantic_model_portal_settings(
        request: Request,
    ) -> tuple[DnaSettings, Any, Response | None]:
        return _semantics_portal_settings(request)

    def on_api_semantic_model(request: Request) -> Response:
        portal_settings, _session, failure = _semantic_model_portal_settings(request)
        if failure is not None:
            return failure
        from meshflow.dna.web.portal.semantics.model_api import builder_payload

        return _json_response(builder_payload(portal_settings))

    def on_api_semantic_model_builder_ui(request: Request) -> Response:
        portal_settings, session, failure = _semantic_model_portal_settings(request)
        if failure is not None:
            return failure
        from meshflow.dna.web.portal.semantics.model_api import builder_ui_payload

        page_step = str(request.args.get("page") or "").strip().lower()
        if page_step not in {"keys", "relationships", "tags", "decisions"}:
            page_step = None
        portal_url = lambda path: f"{request.script_root}{path if path.startswith('/') else f'/{path}'}"
        return _json_response(
            builder_ui_payload(
                portal_settings,
                is_admin=_portal_is_admin(session.username),
                page_step=page_step,
                portal_url=portal_url,
            )
        )

    def on_api_semantic_model_init(request: Request) -> Response:
        portal_settings, session, failure = _semantic_model_portal_settings(request)
        if failure is not None:
            return failure
        if not _portal_is_admin(session.username):
            return _json_response({"error": "forbidden"}, status=403)
        from meshflow.dna.semantic_model import ensure_semantic_model_seed
        from meshflow.dna.web.portal.semantics.init_service import run_portal_semantic_init

        body = request.get_json(silent=True) or {}
        ensure_semantic_model_seed(portal_settings)
        try:
            result = run_portal_semantic_init(
                portal_settings,
                username=session.username,
                company=company,
                force=bool(body.get("force")),
            )
            return _json_response(result)
        except ValueError as exc:
            return _json_response({"error": str(exc)}, status=400)
        except Exception as exc:  # noqa: BLE001 — surface unexpected failures to the UI
            return _json_response({"error": str(exc)}, status=500)

    def on_api_semantic_model_publish(request: Request) -> Response:
        portal_settings, session, failure = _semantic_model_portal_settings(request)
        if failure is not None:
            return failure
        if not _portal_is_admin(session.username):
            return _json_response({"error": "forbidden"}, status=403)
        from meshflow.dna.semantic_model import publish_semantic_model

        try:
            published = publish_semantic_model(portal_settings, username=session.username)
            return _json_response(published)
        except ValueError as exc:
            return _json_response({"error": str(exc)}, status=400)

    def on_api_semantic_model_discard(request: Request) -> Response:
        portal_settings, session, failure = _semantic_model_portal_settings(request)
        if failure is not None:
            return failure
        if not _portal_is_admin(session.username):
            return _json_response({"error": "forbidden"}, status=403)
        from meshflow.dna.semantic_model import discard_semantic_model_draft

        try:
            draft = discard_semantic_model_draft(portal_settings, username=session.username)
            return _json_response({"draft": draft})
        except ValueError as exc:
            return _json_response({"error": str(exc)}, status=400)

    def on_api_semantic_model_discard_step(request: Request) -> Response:
        portal_settings, session, failure = _semantic_model_portal_settings(request)
        if failure is not None:
            return failure
        if not _portal_is_admin(session.username):
            return _json_response({"error": "forbidden"}, status=403)
        body = request.get_json(silent=True) or {}
        step = str(body.get("step") or "").strip().lower()
        from meshflow.dna.semantic_model import discard_semantic_model_step_decisions

        try:
            draft = discard_semantic_model_step_decisions(
                portal_settings,
                step,
                username=session.username,
            )
            return _json_response({"draft": draft, "step": step})
        except ValueError as exc:
            return _json_response({"error": str(exc)}, status=400)

    def on_api_semantic_model_relationship_approve(
        request: Request, relationship_id: str
    ) -> Response:
        portal_settings, session, failure = _semantic_model_portal_settings(request)
        if failure is not None:
            return failure
        if not _portal_is_admin(session.username):
            return _json_response({"error": "forbidden"}, status=403)
        from meshflow.dna.semantic_model import update_relationship_status

        try:
            draft = update_relationship_status(
                portal_settings,
                relationship_id,
                "approved",
                username=session.username,
            )
            return _json_response({"draft": draft})
        except ValueError as exc:
            return _json_response({"error": str(exc)}, status=400)

    def on_api_semantic_model_relationship_reject(
        request: Request, relationship_id: str
    ) -> Response:
        portal_settings, session, failure = _semantic_model_portal_settings(request)
        if failure is not None:
            return failure
        if not _portal_is_admin(session.username):
            return _json_response({"error": "forbidden"}, status=403)
        from meshflow.dna.semantic_model import update_relationship_status

        try:
            draft = update_relationship_status(
                portal_settings,
                relationship_id,
                "rejected",
                username=session.username,
            )
            return _json_response({"draft": draft})
        except ValueError as exc:
            return _json_response({"error": str(exc)}, status=400)

    def on_api_semantic_model_relationship_propose(
        request: Request, relationship_id: str
    ) -> Response:
        portal_settings, session, failure = _semantic_model_portal_settings(request)
        if failure is not None:
            return failure
        if not _portal_is_admin(session.username):
            return _json_response({"error": "forbidden"}, status=403)
        from meshflow.dna.semantic_model import update_relationship_status

        try:
            draft = update_relationship_status(
                portal_settings,
                relationship_id,
                "proposed",
                username=session.username,
            )
            return _json_response({"draft": draft})
        except ValueError as exc:
            return _json_response({"error": str(exc)}, status=400)

    def on_api_semantic_model_entity_approve(request: Request, entity_id: str) -> Response:
        portal_settings, session, failure = _semantic_model_portal_settings(request)
        if failure is not None:
            return failure
        if not _portal_is_admin(session.username):
            return _json_response({"error": "forbidden"}, status=403)
        from meshflow.dna.semantic_model import update_entity_status

        try:
            draft = update_entity_status(
                portal_settings,
                entity_id,
                "approved",
                username=session.username,
            )
            return _json_response({"draft": draft})
        except ValueError as exc:
            return _json_response({"error": str(exc)}, status=400)

    def on_api_semantic_model_entity_reject(request: Request, entity_id: str) -> Response:
        portal_settings, session, failure = _semantic_model_portal_settings(request)
        if failure is not None:
            return failure
        if not _portal_is_admin(session.username):
            return _json_response({"error": "forbidden"}, status=403)
        from meshflow.dna.semantic_model import update_entity_status

        try:
            draft = update_entity_status(
                portal_settings,
                entity_id,
                "rejected",
                username=session.username,
            )
            return _json_response({"draft": draft})
        except ValueError as exc:
            return _json_response({"error": str(exc)}, status=400)

    def on_api_semantic_model_entity_propose(request: Request, entity_id: str) -> Response:
        portal_settings, session, failure = _semantic_model_portal_settings(request)
        if failure is not None:
            return failure
        if not _portal_is_admin(session.username):
            return _json_response({"error": "forbidden"}, status=403)
        from meshflow.dna.semantic_model import update_entity_status

        try:
            draft = update_entity_status(
                portal_settings,
                entity_id,
                "proposed",
                username=session.username,
            )
            return _json_response({"draft": draft})
        except ValueError as exc:
            return _json_response({"error": str(exc)}, status=400)

    def on_api_semantic_model_entity_pk_approve(request: Request, entity_id: str) -> Response:
        return _semantic_model_entity_pk_status(request, entity_id, "approved")

    def on_api_semantic_model_entity_pk_reject(request: Request, entity_id: str) -> Response:
        return _semantic_model_entity_pk_status(request, entity_id, "rejected")

    def on_api_semantic_model_entity_pk_propose(request: Request, entity_id: str) -> Response:
        return _semantic_model_entity_pk_status(request, entity_id, "proposed")

    def _semantic_model_entity_pk_status(request: Request, entity_id: str, status: str) -> Response:
        portal_settings, session, failure = _semantic_model_portal_settings(request)
        if failure is not None:
            return failure
        if not _portal_is_admin(session.username):
            return _json_response({"error": "forbidden"}, status=403)
        from meshflow.dna.semantic_model import update_entity_primary_key_status

        try:
            draft = update_entity_primary_key_status(
                portal_settings,
                entity_id,
                status,
                username=session.username,
            )
            return _json_response({"draft": draft})
        except ValueError as exc:
            return _json_response({"error": str(exc)}, status=400)

    def on_api_semantic_model_fk_approve(request: Request, entity: str, column: str) -> Response:
        return _semantic_model_fk_status(request, entity, column, "approved")

    def on_api_semantic_model_fk_reject(request: Request, entity: str, column: str) -> Response:
        return _semantic_model_fk_status(request, entity, column, "rejected")

    def on_api_semantic_model_fk_propose(request: Request, entity: str, column: str) -> Response:
        return _semantic_model_fk_status(request, entity, column, "proposed")

    def _semantic_model_fk_status(request: Request, entity: str, column: str, status: str) -> Response:
        portal_settings, session, failure = _semantic_model_portal_settings(request)
        if failure is not None:
            return failure
        if not _portal_is_admin(session.username):
            return _json_response({"error": "forbidden"}, status=403)
        from meshflow.dna.semantic_model import update_attribute_key_role

        try:
            draft = update_attribute_key_role(
                portal_settings,
                entity,
                column,
                role="foreign_key",
                status=status,
                username=session.username,
            )
            return _json_response({"draft": draft})
        except ValueError as exc:
            return _json_response({"error": str(exc)}, status=400)

    def on_api_semantic_model_complete_step(request: Request) -> Response:
        portal_settings, session, failure = _semantic_model_portal_settings(request)
        if failure is not None:
            return failure
        if not _portal_is_admin(session.username):
            return _json_response({"error": "forbidden"}, status=403)
        from meshflow.dna.web.portal.semantics.init_service import run_portal_complete_builder_step

        body = request.get_json(silent=True) or {}
        step = str(body.get("step") or "").strip().lower()
        try:
            result = run_portal_complete_builder_step(
                portal_settings,
                step,
                username=session.username,
                company=company,
            )
            return _json_response(result)
        except ValueError as exc:
            return _json_response({"error": str(exc)}, status=400)

    def on_api_semantic_model_builder_primary_key(request: Request) -> Response:
        portal_settings, session, failure = _semantic_model_portal_settings(request)
        if failure is not None:
            return failure
        if not _portal_is_admin(session.username):
            return _json_response({"error": "forbidden"}, status=403)
        from meshflow.dna.semantic_model import manual_assign_primary_key

        body = request.get_json(silent=True) or {}
        try:
            draft = manual_assign_primary_key(
                portal_settings,
                str(body.get("entity") or ""),
                str(body.get("column") or ""),
                username=session.username,
            )
            return _json_response({"draft": draft})
        except ValueError as exc:
            return _json_response({"error": str(exc)}, status=400)

    def on_api_semantic_model_builder_foreign_key(request: Request) -> Response:
        portal_settings, session, failure = _semantic_model_portal_settings(request)
        if failure is not None:
            return failure
        if not _portal_is_admin(session.username):
            return _json_response({"error": "forbidden"}, status=403)
        from meshflow.dna.semantic_model import manual_assign_foreign_key

        body = request.get_json(silent=True) or {}
        try:
            draft = manual_assign_foreign_key(
                portal_settings,
                str(body.get("entity") or ""),
                str(body.get("column") or ""),
                str(body.get("to_entity") or ""),
                str(body.get("to_column") or "id"),
                username=session.username,
            )
            return _json_response({"draft": draft})
        except ValueError as exc:
            return _json_response({"error": str(exc)}, status=400)

    def on_api_semantic_model_builder_relationship(request: Request) -> Response:
        portal_settings, session, failure = _semantic_model_portal_settings(request)
        if failure is not None:
            return failure
        if not _portal_is_admin(session.username):
            return _json_response({"error": "forbidden"}, status=403)
        from meshflow.dna.semantic_model import manual_create_relationship

        body = request.get_json(silent=True) or {}
        try:
            draft = manual_create_relationship(
                portal_settings,
                str(body.get("from_entity") or ""),
                str(body.get("from_column") or ""),
                str(body.get("to_entity") or ""),
                str(body.get("to_column") or "id"),
                str(body.get("cardinality") or "many_to_one"),
                username=session.username,
            )
            return _json_response({"draft": draft})
        except ValueError as exc:
            return _json_response({"error": str(exc)}, status=400)

    def on_api_semantic_model_builder_column_tag(request: Request) -> Response:
        portal_settings, session, failure = _semantic_model_portal_settings(request)
        if failure is not None:
            return failure
        if not _portal_is_admin(session.username):
            return _json_response({"error": "forbidden"}, status=403)
        from meshflow.dna.semantic_model import manual_assign_column_tag

        body = request.get_json(silent=True) or {}
        concepts_raw = body.get("concepts")
        concepts = (
            [str(c) for c in concepts_raw]
            if isinstance(concepts_raw, list)
            else [str(body.get("concept") or "")]
        )
        try:
            draft = manual_assign_column_tag(
                portal_settings,
                str(body.get("entity") or ""),
                str(body.get("column") or ""),
                concepts,
                username=session.username,
            )
            return _json_response({"draft": draft})
        except ValueError as exc:
            return _json_response({"error": str(exc)}, status=400)

    def on_api_semantic_model_builder_generate_relationships(request: Request) -> Response:
        portal_settings, session, failure = _semantic_model_portal_settings(request)
        if failure is not None:
            return failure
        if not _portal_is_admin(session.username):
            return _json_response({"error": "forbidden"}, status=403)
        from meshflow.dna.semantic_model import generate_relationships_from_keys, load_semantic_model_draft

        body = request.get_json(silent=True) or {}
        approve_proposed = str(body.get("approve_proposed") or "true").lower() in {
            "1",
            "true",
            "yes",
        }
        try:
            result = generate_relationships_from_keys(
                portal_settings,
                username=session.username,
                approve_proposed=approve_proposed,
            )
            draft = load_semantic_model_draft(portal_settings)
            return _json_response({"draft": draft, "result": result})
        except ValueError as exc:
            return _json_response({"error": str(exc)}, status=400)

    def on_api_semantic_model_builder_rerun_tagging(request: Request) -> Response:
        portal_settings, session, failure = _semantic_model_portal_settings(request)
        if failure is not None:
            return failure
        if not _portal_is_admin(session.username):
            return _json_response({"error": "forbidden"}, status=403)
        from meshflow.dna.web.portal.semantics.init_service import run_portal_rerun_tag_generation

        try:
            result = run_portal_rerun_tag_generation(
                portal_settings,
                username=session.username,
                company=company,
            )
            return _json_response(result)
        except ValueError as exc:
            return _json_response({"error": str(exc)}, status=400)

    def on_api_semantic_model_question_resolve(request: Request, question_id: str) -> Response:
        portal_settings, session, failure = _semantic_model_portal_settings(request)
        if failure is not None:
            return failure
        if not _portal_is_admin(session.username):
            return _json_response({"error": "forbidden"}, status=403)
        from meshflow.dna.semantic_model import resolve_question

        body = request.get_json(silent=True) or {}
        try:
            draft = resolve_question(
                portal_settings,
                question_id,
                username=session.username,
                resolution=str(body.get("resolution") or ""),
                choice=str(body.get("choice") or ""),
            )
            return _json_response({"draft": draft})
        except ValueError as exc:
            return _json_response({"error": str(exc)}, status=400)

    def on_api_semantic_model_attributes(request: Request) -> Response:
        portal_settings, _session, failure = _semantic_model_portal_settings(request)
        if failure is not None:
            return failure
        from meshflow.dna.web.portal.semantics.model_api import attributes_payload

        proposed_only = str(request.args.get("proposed") or "").lower() in {"1", "true", "yes"}
        return _json_response(attributes_payload(portal_settings, proposed_only=proposed_only))

    def on_api_semantic_model_attribute_approve(
        request: Request, entity: str, column: str
    ) -> Response:
        portal_settings, session, failure = _semantic_model_portal_settings(request)
        if failure is not None:
            return failure
        if not _portal_is_admin(session.username):
            return _json_response({"error": "forbidden"}, status=403)
        from meshflow.dna.semantic_model import update_attribute_status

        try:
            draft = update_attribute_status(
                portal_settings,
                entity,
                column,
                "approved",
                username=session.username,
            )
            return _json_response({"draft": draft})
        except ValueError as exc:
            return _json_response({"error": str(exc)}, status=400)

    def on_api_semantic_model_attribute_reject(
        request: Request, entity: str, column: str
    ) -> Response:
        portal_settings, session, failure = _semantic_model_portal_settings(request)
        if failure is not None:
            return failure
        if not _portal_is_admin(session.username):
            return _json_response({"error": "forbidden"}, status=403)
        from meshflow.dna.semantic_model import update_attribute_status

        try:
            draft = update_attribute_status(
                portal_settings,
                entity,
                column,
                "rejected",
                username=session.username,
            )
            return _json_response({"draft": draft})
        except ValueError as exc:
            return _json_response({"error": str(exc)}, status=400)

    def on_api_semantic_model_attribute_propose(
        request: Request, entity: str, column: str
    ) -> Response:
        portal_settings, session, failure = _semantic_model_portal_settings(request)
        if failure is not None:
            return failure
        if not _portal_is_admin(session.username):
            return _json_response({"error": "forbidden"}, status=403)
        from meshflow.dna.semantic_model import update_attribute_status

        try:
            draft = update_attribute_status(
                portal_settings,
                entity,
                column,
                "proposed",
                username=session.username,
            )
            return _json_response({"draft": draft})
        except ValueError as exc:
            return _json_response({"error": str(exc)}, status=400)

    def on_api_semantic_model_approve_all_keys(request: Request) -> Response:
        portal_settings, session, failure = _semantic_model_portal_settings(request)
        if failure is not None:
            return failure
        if not _portal_is_admin(session.username):
            return _json_response({"error": "forbidden"}, status=403)
        from meshflow.dna.semantic_model import approve_proposed_keys

        try:
            return _json_response(
                approve_proposed_keys(portal_settings, username=session.username)
            )
        except ValueError as exc:
            return _json_response({"error": str(exc)}, status=400)

    def on_api_semantic_model_approve_all_primary_keys(request: Request) -> Response:
        portal_settings, session, failure = _semantic_model_portal_settings(request)
        if failure is not None:
            return failure
        if not _portal_is_admin(session.username):
            return _json_response({"error": "forbidden"}, status=403)
        from meshflow.dna.semantic_model import approve_proposed_keys

        try:
            return _json_response(
                approve_proposed_keys(
                    portal_settings,
                    username=session.username,
                    primary=True,
                    foreign=False,
                )
            )
        except ValueError as exc:
            return _json_response({"error": str(exc)}, status=400)

    def on_api_semantic_model_approve_all_foreign_keys(request: Request) -> Response:
        portal_settings, session, failure = _semantic_model_portal_settings(request)
        if failure is not None:
            return failure
        if not _portal_is_admin(session.username):
            return _json_response({"error": "forbidden"}, status=403)
        from meshflow.dna.semantic_model import approve_proposed_keys

        try:
            return _json_response(
                approve_proposed_keys(
                    portal_settings,
                    username=session.username,
                    primary=False,
                    foreign=True,
                )
            )
        except ValueError as exc:
            return _json_response({"error": str(exc)}, status=400)

    def on_api_semantic_model_approve_all_tags(request: Request) -> Response:
        portal_settings, session, failure = _semantic_model_portal_settings(request)
        if failure is not None:
            return failure
        if not _portal_is_admin(session.username):
            return _json_response({"error": "forbidden"}, status=403)
        from meshflow.dna.semantic_model import approve_all_proposed_tags

        try:
            return _json_response(
                approve_all_proposed_tags(portal_settings, username=session.username)
            )
        except ValueError as exc:
            return _json_response({"error": str(exc)}, status=400)

    def on_api_semantic_model_approve_all_structure(request: Request) -> Response:
        portal_settings, session, failure = _semantic_model_portal_settings(request)
        if failure is not None:
            return failure
        if not _portal_is_admin(session.username):
            return _json_response({"error": "forbidden"}, status=403)
        from meshflow.dna.semantic_model import approve_all_proposed_entities_and_joins

        try:
            return _json_response(
                approve_all_proposed_entities_and_joins(
                    portal_settings,
                    username=session.username,
                )
            )
        except ValueError as exc:
            return _json_response({"error": str(exc)}, status=400)

    def on_api_semantic_model_assistant(request: Request) -> Response:
        portal_settings, session, failure = _semantic_model_portal_settings(request)
        if failure is not None:
            return failure
        if not _portal_is_admin(session.username):
            return _json_response({"error": "forbidden"}, status=403)
        from meshflow.dna.web.portal.semantics.assistant_service import chat_semantic_assistant

        body = request.get_json(silent=True) or {}
        try:
            result = chat_semantic_assistant(
                portal_settings,
                user_message=str(body.get("message") or ""),
                history=body.get("history") if isinstance(body.get("history"), list) else None,
                username=session.username,
            )
            return _json_response(result)
        except ValueError as exc:
            return _json_response({"error": str(exc)}, status=400)
        except Exception as exc:  # noqa: BLE001 — surface Bedrock failures to UI
            return _json_response({"error": str(exc)}, status=502)

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

    def on_api_config_assistant(request: Request) -> Response:
        if (failure := _api_authorized(request)) is not None:
            return failure
        session = session_from_request(request, company=company, environment=environment)
        assert session is not None
        if not _portal_is_admin(session.username):
            return _json_response({"error": "forbidden"}, status=403)
        from meshflow.dna.web.portal.config_assistant.bedrock_usage import usage_summary as bedrock_usage_summary
        from meshflow.dna.web.portal.config_assistant import load_base_configs, proposal_view
        from meshflow.dna.web.portal.config_assistant.service import ensure_running_chat_progress
        from meshflow.dna.web.portal.views import config_assistant_poll_payload

        client = _client_config(session.client_id)
        portal_settings = _portal_settings(settings, client, environment=environment)
        assistant_usage = bedrock_usage_summary(
            portal_settings,
            client_id=client.client_id,
            monthly_budget_usd=client.config_assistant_monthly_budget_usd,
        )
        try:
            base = load_base_configs(portal_settings)
            active = ensure_running_chat_progress(portal_settings)
            proposal_view_data = (
                proposal_view(portal_settings, active, base) if active else None
            )
        except FileNotFoundError:
            proposal_view_data = None
        return _json_response(
            config_assistant_poll_payload(
                lambda path: _app_url(request, path),
                governance_path="/portal/dna/engine",
                proposal_view_data=proposal_view_data,
                usage_at_limit=assistant_usage.at_limit,
            )
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
        "portal_configured_page": on_portal_configured_page,
        "portal_catalog": on_portal_catalog,
        "portal_catalog_output": on_portal_catalog_output,
        "portal_catalog_gold": on_portal_catalog_gold,
        "portal_catalog_silver": on_portal_catalog_silver,
        "portal_catalog_silver_entity": on_portal_catalog_silver_entity,
        "portal_dna": on_portal_dna,
        "portal_dna_mappings": on_portal_dna_mappings,
        "portal_dna_engine": on_portal_dna_engine,
        "portal_governance": on_portal_governance,
        "portal_governance_users": on_portal_governance_users,
        "portal_governance_config": on_portal_governance_config,
        "portal_governance_config_preview_exit": on_portal_governance_config_preview_exit,
        "portal_admin_config": on_portal_admin_config,
        "portal_admin_config_preview_exit": on_portal_admin_config_preview_exit,
        "portal_admin_users": on_portal_admin_users,
        "portal_semantics": on_portal_semantics,
        "portal_semantic_builder": on_portal_semantic_builder,
        "portal_semantic_builder_keys": on_portal_semantic_builder_keys,
        "portal_semantic_builder_relationships": on_portal_semantic_builder_relationships,
        "portal_semantic_builder_tags": on_portal_semantic_builder_tags,
        "portal_semantic_builder_decisions": on_portal_semantic_builder_decisions,
        "portal_semantics_entity": on_portal_semantics_entity,
        "static": on_static,
        "api_pack": on_api_pack,
        "api_manifest": on_api_manifest,
        "api_output": on_api_output,
        "api_reporting_pages": on_api_reporting_pages,
        "api_reporting_page": on_api_reporting_page,
        "api_reporting_catalog": on_api_reporting_catalog,
        "api_config_assistant": on_api_config_assistant,
        "api_semantics_concepts": on_api_semantics_concepts,
        "api_semantics_entities": on_api_semantics_entities,
        "api_semantics_entity": on_api_semantics_entity,
        "api_semantics_draft": on_api_semantics_draft,
        "api_semantics_publish": on_api_semantics_publish,
        "api_semantics_discard": on_api_semantics_discard,
        "api_semantics_custom_concepts": on_api_semantics_custom_concepts,
        "api_semantic_model": on_api_semantic_model,
        "api_semantic_model_builder_ui": on_api_semantic_model_builder_ui,
        "api_semantic_model_init": on_api_semantic_model_init,
        "api_semantic_model_publish": on_api_semantic_model_publish,
        "api_semantic_model_discard": on_api_semantic_model_discard,
        "api_semantic_model_discard_step": on_api_semantic_model_discard_step,
        "api_semantic_model_relationship_approve": on_api_semantic_model_relationship_approve,
        "api_semantic_model_relationship_reject": on_api_semantic_model_relationship_reject,
        "api_semantic_model_relationship_propose": on_api_semantic_model_relationship_propose,
        "api_semantic_model_entity_approve": on_api_semantic_model_entity_approve,
        "api_semantic_model_entity_reject": on_api_semantic_model_entity_reject,
        "api_semantic_model_entity_propose": on_api_semantic_model_entity_propose,
        "api_semantic_model_entity_pk_approve": on_api_semantic_model_entity_pk_approve,
        "api_semantic_model_entity_pk_reject": on_api_semantic_model_entity_pk_reject,
        "api_semantic_model_entity_pk_propose": on_api_semantic_model_entity_pk_propose,
        "api_semantic_model_fk_approve": on_api_semantic_model_fk_approve,
        "api_semantic_model_fk_reject": on_api_semantic_model_fk_reject,
        "api_semantic_model_fk_propose": on_api_semantic_model_fk_propose,
        "api_semantic_model_complete_step": on_api_semantic_model_complete_step,
        "api_semantic_model_builder_primary_key": on_api_semantic_model_builder_primary_key,
        "api_semantic_model_builder_foreign_key": on_api_semantic_model_builder_foreign_key,
        "api_semantic_model_builder_relationship": on_api_semantic_model_builder_relationship,
        "api_semantic_model_builder_column_tag": on_api_semantic_model_builder_column_tag,
        "api_semantic_model_builder_generate_relationships": on_api_semantic_model_builder_generate_relationships,
        "api_semantic_model_builder_rerun_tagging": on_api_semantic_model_builder_rerun_tagging,
        "api_semantic_model_question_resolve": on_api_semantic_model_question_resolve,
        "api_semantic_model_attributes": on_api_semantic_model_attributes,
        "api_semantic_model_attribute_approve": on_api_semantic_model_attribute_approve,
        "api_semantic_model_attribute_reject": on_api_semantic_model_attribute_reject,
        "api_semantic_model_attribute_propose": on_api_semantic_model_attribute_propose,
        "api_semantic_model_approve_all_keys": on_api_semantic_model_approve_all_keys,
        "api_semantic_model_approve_all_primary_keys": on_api_semantic_model_approve_all_primary_keys,
        "api_semantic_model_approve_all_foreign_keys": on_api_semantic_model_approve_all_foreign_keys,
        "api_semantic_model_approve_all_tags": on_api_semantic_model_approve_all_tags,
        "api_semantic_model_approve_all_structure": on_api_semantic_model_approve_all_structure,
        "api_semantic_model_assistant": on_api_semantic_model_assistant,
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
