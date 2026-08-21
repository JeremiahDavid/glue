"""HTML views for the platform admin onboarding wizard."""

from __future__ import annotations

from functools import lru_cache
from importlib.resources import files
from html import escape
from typing import Any, Callable

from meshflow.dna.web.admin.views import _ADMIN_NAV, _ADMIN_SHELL_CSS
from meshflow.client_registry import CLIENT_ID_HTML_PATTERN
from meshflow.dna.web.admin.onboarding.guides import (
    dbc_permission_sets_requirement_html,
    render_connector_guide_html,
    render_credential_summary_fields,
)
from meshflow.dna.web.admin.onboarding.handlers import (
    ONBOARDING_STEP_LABELS,
    WIZARD_STEP_COUNT,
    _CONNECTOR_DEFAULTS,
    ConnectorCredentialSnapshot,
    entity_bundles_for_connector,
)
from markupsafe import Markup

from meshflow.dna.web.templating import render_template
from meshflow.dna.web.theme import render_page

UrlFn = Callable[[str], str]

_CONNECTOR_LABELS = {
    "dbc": "Business Central",
    "qbo": "QuickBooks Online",
    "qbd": "QuickBooks Desktop",
}


def _format_connector_sources(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        labels = [_CONNECTOR_LABELS.get(str(item), str(item)) for item in value if str(item).strip()]
        return ", ".join(labels)
    source = str(value).strip().lower()
    if not source:
        return ""
    return _CONNECTOR_LABELS.get(source, source)


def _onboarding_page(
    *,
    title: str,
    url: UrlFn,
    body: str,
) -> str:
    return render_page(
        title=title,
        body=body,
        url=url,
        active_path="/admin/onboarding",
        nav_links=_ADMIN_NAV,
    )


def _shell_header(
    *,
    url: UrlFn,
    username: str,
    eyebrow: str,
    heading: str,
    lead: str = "",
    action_html: str = "",
) -> str:
    action_block = action_html or (
        f'<form method="post" action="{escape(url("/admin/logout"))}">'
        f'<button type="submit" class="btn secondary">Sign out</button></form>'
    )
    return render_template(
        "admin/onboarding/_shell_header.html",
        eyebrow=eyebrow,
        heading=heading,
        lead=lead,
        username=username,
        action_block=Markup(action_block),
    )


def _flash(message: str, *, error: bool = False) -> str:
    if not message.strip():
        return ""
    css = "form-error" if error else "admin-job-flash"
    return f'<p class="{css}">{escape(message)}</p>'


def _stack_state_css(status: str) -> str:
    key = status.strip().lower().replace("_", " ")
    if any(token in key for token in ("complete", "ok", "success")):
        return "is-ok"
    if any(token in key for token in ("progress", "pending", "running", "queued")):
        return "is-running"
    if any(token in key for token in ("fail", "error", "rollback")):
        return "is-error"
    return "is-unknown"


def _stack_progress_state(status: str) -> str:
    key = status.strip().lower()
    if key == "complete":
        return "is-complete"
    if key == "failed":
        return "is-error"
    if key == "in_progress":
        return "is-indeterminate"
    return "is-idle"


def _stack_progress_width(status: str) -> str:
    key = status.strip().lower()
    if key == "complete":
        return "100"
    if key == "failed":
        return "100"
    if key == "not_found":
        return "0"
    if key == "in_progress":
        return ""
    return "8"


def _stack_status_cell(status: str) -> str:
    status_label = escape(status.replace("_", " ").title())
    progress_state = _stack_progress_state(status)
    width = _stack_progress_width(status)
    width_attr = f' style="width: {width}%;"' if width else ""
    return (
        f'<span class="admin-job-state {_stack_state_css(status)}" data-stack-status-badge>{status_label}</span>'
        f'<div class="admin-stack-progress {progress_state}" data-stack-progress>'
        f'<div class="admin-stack-progress-bar" data-stack-progress-bar{width_attr}></div>'
        "</div>"
    )


def _stack_rows(stacks: list[dict[str, Any]]) -> str:
    items = [
        {
            "stack_name": str(item.get("stack_name", "")),
            "status": str(item.get("status", "unknown")),
            "status_cell": Markup(_stack_status_cell(str(item.get("status", "unknown")))),
            "status_reason": str(item.get("status_reason", "")),
        }
        for item in stacks
    ]
    return render_template("admin/onboarding/_stack_rows.html", stacks=items)


def _form_section(title: str, content: str) -> str:
    return render_template(
        "admin/onboarding/_form_section.html", title=title, content=Markup(content)
    )


def _field_label(name: str, label: str, *, hint: str = "") -> str:
    title_attr = f' title="{escape(hint)}"' if hint.strip() else ""
    return f'<label for="{escape(name)}"{title_attr}>{escape(label)}</label>'


def _initial_admin_wizard_section(values: dict[str, str]) -> str:
    return render_template(
        "admin/onboarding/_initial_admin_wizard_section.html",
        username_field=Markup(
            _form_field(
                "initial_admin_username",
                "Admin username",
                value=values.get("initial_admin_username", ""),
                hint="Optional. Cognito username for the client's first portal admin.",
            )
        ),
        email_field=Markup(
            _form_field(
                "initial_admin_email",
                "Admin email",
                value=values.get("initial_admin_email", ""),
                field_type="email",
                hint="Optional. Cognito sends a temporary password to this address when you invite from the deploy step.",
            )
        ),
    )


def _initial_admin_invite_section(
    *,
    url: UrlFn,
    company: str,
    environment: str,
    client_id: str,
    values: dict[str, str],
    ready: bool,
    portal_dns_required: bool = False,
) -> str:
    pending = None
    if not ready:
        pending = "ReportingStack deploy completes"
        if portal_dns_required:
            pending = "ReportingStack and GlobalDnsStack deploy complete"
    return render_template(
        "admin/onboarding/_initial_admin_invite_section.html",
        pending=pending,
        invite_action_url=url(f"/admin/onboarding/{company.lower()}/invite-admin"),
        environment=environment,
        client_id=client_id,
        ready=ready,
        username_field=Markup(
            _form_field(
                "initial_admin_username",
                "Admin username",
                value=values.get("initial_admin_username", ""),
                hint="Cognito username for the client's first portal admin.",
            )
        ),
        email_field=Markup(
            _form_field(
                "initial_admin_email",
                "Admin email",
                value=values.get("initial_admin_email", ""),
                field_type="email",
                hint="Cognito sends a temporary password to this address.",
            )
        ),
    )


def _client_portal_url_section(
    *,
    portal_urls: dict[str, str],
    ready: bool,
    portal_dns_required: bool = False,
) -> str:
    if not portal_urls:
        return ""
    portal_url = portal_urls.get("portal", "")
    governance_url = portal_urls.get("governance_users", "")
    if not portal_url:
        return ""
    pending = None
    if not ready:
        pending = "ReportingStack deploy completes"
        if portal_dns_required:
            pending = "ReportingStack and GlobalDnsStack deploy complete"
    return render_template(
        "admin/onboarding/_client_portal_url_section.html",
        pending=pending,
        portal_url=portal_url,
        governance_url=governance_url,
    )


def _form_field(
    name: str,
    label: str,
    *,
    value: str = "",
    field_type: str = "text",
    required: bool = False,
    hint: str = "",
    min_value: int | None = None,
    max_value: int | None = None,
    pattern: str = "",
    maxlength: int | None = None,
) -> str:
    return render_template(
        "admin/onboarding/_form_field.html",
        label_html=Markup(_field_label(name, label, hint=hint)),
        name=name,
        field_type=field_type,
        value=value,
        required=required,
        min_value=min_value,
        max_value=max_value,
        pattern=pattern,
        maxlength=maxlength,
        hint=hint,
    )


def _form_select(
    name: str,
    label: str,
    options_html: str,
    *,
    hint: str = "",
) -> str:
    return render_template(
        "admin/onboarding/_form_select.html",
        label_html=Markup(_field_label(name, label, hint=hint)),
        name=name,
        options_html=Markup(options_html),
    )


def _connector_enabled(values: dict[str, str], source: str, *, default: bool = False) -> bool:
    key = f"connector_{source}_enabled"
    if key in values:
        return str(values[key]).strip().lower() in {"on", "true", "1", "yes"}
    return default


def _entity_bundle_options(source: str, selected: str) -> str:
    bundles = entity_bundles_for_connector(source)
    selected_key = selected.strip().lower()
    if selected_key and selected_key not in bundles:
        bundles = [selected_key, *bundles]
    return render_template(
        "admin/onboarding/_entity_bundle_options.html", bundles=bundles, selected_key=selected_key
    )


def _connector_wizard_block(source: str, values: dict[str, str]) -> str:
    defaults = _CONNECTOR_DEFAULTS[source]
    prefix = f"connector_{source}"
    enabled = _connector_enabled(values, source, default=(source == "dbc"))
    selected_bundle = values.get(f"{prefix}_entity_bundle", str(defaults["entity_bundle"]))
    fields = [
        Markup(
            _form_select(
                f"{prefix}_entity_bundle",
                "Entity bundle",
                _entity_bundle_options(source, selected_bundle),
                hint="Named entity set to sync for this connector.",
            )
        ),
    ]
    if source in {"dbc", "qbo"}:
        fields.extend(
            [
                Markup(
                    _form_field(
                        f"{prefix}_schedule_hour",
                        "Schedule hour (Eastern)",
                        value=values.get(f"{prefix}_schedule_hour", str(defaults["schedule_hour"])),
                        field_type="number",
                        min_value=0,
                        max_value=23,
                        hint="Hour in US Eastern time (0–23) for the daily bronze ingest schedule.",
                    )
                ),
                Markup(
                    _form_field(
                        f"{prefix}_schedule_minute",
                        "Schedule minute",
                        value=values.get(f"{prefix}_schedule_minute", str(defaults["schedule_minute"])),
                        field_type="number",
                        min_value=0,
                        max_value=59,
                        hint="Minute (0–59) in US Eastern time, paired with schedule hour.",
                    )
                ),
            ]
        )
    if source == "qbo":
        fields.append(
            Markup(
                _form_field(
                    f"{prefix}_tier",
                    "QBO environment",
                    value=values.get(f"{prefix}_tier", str(defaults.get("tier", "sandbox"))),
                    hint="Intuit API tier: sandbox for testing or production for live company data.",
                )
            )
        )
    return render_template(
        "admin/onboarding/_connector_wizard_block.html",
        prefix=prefix,
        enabled=enabled,
        label=_CONNECTOR_LABELS[source],
        fields=fields,
    )


def _connectors_wizard_section(values: dict[str, str]) -> str:
    blocks = "".join(_connector_wizard_block(source, values) for source in ("dbc", "qbo", "qbd"))
    return f'<div class="admin-onboarding-connector-list">{blocks}</div>'


def _onboarding_step_href(
    step_number: int,
    current_step: int,
    *,
    url: UrlFn,
    company: str = "",
    environment: str = "",
    client_id: str = "",
) -> str:
    if step_number == current_step:
        return ""
    if step_number == 1:
        if company and environment and client_id:
            return url(
                f"/admin/onboarding/new?company={company}&environment={environment}&client_id={client_id}"
            )
        return url("/admin/onboarding/new")
    if step_number == 2 and company and environment and client_id:
        return url(f"/admin/onboarding/{company.lower()}?environment={environment}&client_id={client_id}")
    if step_number == 3 and company and environment and client_id:
        return url(
            f"/admin/onboarding/{company.lower()}/deploy"
            f"?environment={environment}&client_id={client_id}"
        )
    if step_number == 4 and company and environment and client_id:
        return url(
            f"/admin/onboarding/{company.lower()}/pipelines"
            f"?environment={environment}&client_id={client_id}"
        )
    return ""


def _steps_flow_html(
    current_step: int,
    *,
    url: UrlFn,
    company: str = "",
    environment: str = "",
    client_id: str = "",
) -> str:
    steps = []
    for step_number in range(1, WIZARD_STEP_COUNT + 1):
        label = ONBOARDING_STEP_LABELS[step_number]
        if step_number < current_step:
            state = "is-complete"
        elif step_number == current_step:
            state = "is-active"
        else:
            state = "is-upcoming"
        href = _onboarding_step_href(
            step_number,
            current_step,
            url=url,
            company=company,
            environment=environment,
            client_id=client_id,
        )
        steps.append({"marker": f"Step {step_number}", "state": state, "label": label, "href": href})
    return render_template("admin/onboarding/_steps_flow.html", steps=steps)


def render_onboarding_home(
    *,
    url: UrlFn,
    username: str,
    clients: list[dict[str, Any]],
    flash: str = "",
) -> str:
    rows = []
    for client in clients:
        company = escape(str(client.get("company", "")))
        client_id = escape(str(client.get("client_id", "")))
        environment = escape(str(client.get("environment", "")))
        detail_url = escape(
            url(f"/admin/onboarding/{company.lower()}?environment={environment}&client_id={client_id}")
        )
        rows.append(
            {
                "company": Markup(company),
                "client_id": Markup(client_id),
                "environment": Markup(environment),
                "connectors": _format_connector_sources(
                    client.get("connector_sources", client.get("connector_source", ""))
                ),
                "detail_url": Markup(detail_url),
            }
        )
    table = render_template("admin/onboarding/_onboarding_home_table.html", rows=rows)
    body = f"""
    <div class="admin-shell">
      {_shell_header(
          url=url,
          username=username,
          eyebrow="Platform admin",
          heading="Client onboarding",
          lead="Provision ingest, DNA, and portal stacks for new clients.",
          action_html=(
              f'<div class="admin-onboarding-actions">'
              f'<a class="btn" href="{escape(url("/admin/onboarding/new"))}">New client</a>'
              f'<form method="post" action="{escape(url("/admin/logout"))}">'
              f'<button type="submit" class="btn secondary">Sign out</button></form>'
              f"</div>"
          ),
      )}
      {_flash(flash)}
      {table}
    </div>
    <style>
      {_ADMIN_SHELL_CSS}
    </style>
    <link rel="stylesheet" href="{escape(url("/static/admin-onboarding.css"))}" />
    """
    return _onboarding_page(title="Onboarding", url=url, body=body)


def render_onboarding_wizard(
    *,
    url: UrlFn,
    username: str,
    form_values: dict[str, str] | None = None,
    error: str = "",
    company: str = "",
    environment: str = "",
    client_id: str = "",
) -> str:
    values = dict(form_values or {})
    company = company or str(values.get("onboarding_company", "")).strip().lower()
    environment = environment or str(values.get("onboarding_environment", "")).strip().lower()
    client_id = client_id or str(values.get("onboarding_client_id", "")).strip().lower()
    editing = bool(company and environment and client_id)
    hidden_context = ""
    if editing:
        hidden_context = (
            f'<input type="hidden" name="onboarding_company" value="{escape(company)}" />'
            f'<input type="hidden" name="onboarding_environment" value="{escape(environment)}" />'
            f'<input type="hidden" name="onboarding_client_id" value="{escape(client_id)}" />'
        )
    body = f"""
    <div class="admin-shell">
      {_shell_header(
          url=url,
          username=username,
          eyebrow="Onboarding wizard",
          heading=f"Step 1 of {WIZARD_STEP_COUNT}",
          lead="Create a client registry entry and default portal settings.",
      )}
      {_flash(error, error=True)}
      {_steps_flow_html(1, url=url, company=company, environment=environment, client_id=client_id)}
      <form method="post" action="{escape(url('/admin/onboarding/new'))}" class="admin-onboarding-form">
        {hidden_context}
        {_form_section(
            "Client identity",
            f'''<div class="admin-onboarding-form-grid">
            {_form_field(
                "display_name",
                "Display name",
                value=values.get("display_name", ""),
                required=True,
                hint="Friendly business name shown in the portal header, invites, and welcome screens. Also used to derive the data tenant id.",
            )}
            {_form_field(
                "client_id",
                "Portal client id",
                value=values.get("client_id", ""),
                required=True,
                pattern=CLIENT_ID_HTML_PATTERN,
                maxlength=63,
                hint="Lowercase letters and numbers only (e.g. acme, poc2). Used for the reporting stack, Cognito client mapping, and subdomain acme.hive-flow-ai.com.",
            )}
          </div>''',
        )}
        {_form_section(
            "Connectors",
            _connectors_wizard_section(values),
        )}
        {_form_section(
            "Initial portal admin (optional)",
            f'''<p class="pack-card-lead">
            Pre-fill the first client admin invite. Leave blank to assign users later from the client portal.
            GlobalAdmin can always sign in and manage users at <code>/portal/governance/users</code>.
          </p>
          {_initial_admin_wizard_section(values)}''',
        )}
        <div class="admin-onboarding-actions">
          <button type="submit" class="btn">Save client config</button>
          <a class="btn secondary" href="{escape(url('/admin/onboarding'))}">Cancel</a>
        </div>
      </form>
    </div>
    <style>
      {_ADMIN_SHELL_CSS}
    </style>
    <link rel="stylesheet" href="{escape(url("/static/admin-onboarding.css"))}" />
    """
    return _onboarding_page(title="New client", url=url, body=body)


def _connector_guide_dialog(
    *,
    source: str,
) -> str:
    label = _CONNECTOR_LABELS.get(source, source)
    dialog_id = f"connector-guide-{source}"
    form_id = f"connector-secrets-{source}"
    guide_html = render_connector_guide_html(source)
    return f"""
      <dialog id="{escape(dialog_id)}" class="admin-connector-guide-dialog" aria-labelledby="{escape(dialog_id)}-title">
        <div class="admin-connector-guide-dialog-head">
          <h3 id="{escape(dialog_id)}-title">{escape(label)} credential setup</h3>
          <button type="button" class="btn secondary" data-connector-guide-close="{escape(dialog_id)}">Close</button>
        </div>
        <div class="admin-connector-guide-dialog-body">{guide_html}</div>
        <div class="admin-connector-guide-dialog-foot">
          <button type="button" class="btn" data-connector-guide-apply="{escape(dialog_id)}">Apply to form</button>
          <button type="button" class="btn secondary" data-connector-guide-close="{escape(dialog_id)}">Close</button>
        </div>
      </dialog>
    """


@lru_cache(maxsize=1)
def _admin_onboarding_js() -> str:
    return files("meshflow.dna.web").joinpath("static/admin_onboarding.js").read_text(encoding="utf-8")


def _connector_guide_script() -> str:
    # Inline so validate/load-companies work in Lambda without a separate static fetch.
    return f"<script>\n{_admin_onboarding_js()}\n</script>"


def _connector_credential_status_html(snapshot: ConnectorCredentialSnapshot | None) -> str:
    if snapshot is None:
        return ""
    if snapshot.error:
        return (
            f'<p class="pack-card-lead admin-credential-status">'
            f"Could not load saved credentials: {escape(snapshot.error)}</p>"
        )
    if not snapshot.secret_id:
        return ""
    if snapshot.exists:
        return (
            f'<p class="pack-card-lead admin-credential-status">'
            f"Saved secret: <code>{escape(snapshot.secret_id)}</code></p>"
        )
    return (
        f'<p class="pack-card-lead admin-credential-status">'
        f"No saved secret yet (<code>{escape(snapshot.secret_id)}</code>).</p>"
    )


def _connector_credentials_section(
    *,
    url: UrlFn,
    company: str,
    environment: str,
    client_id: str,
    source: str,
    credential_snapshot: ConnectorCredentialSnapshot | None = None,
) -> str:
    form_id = f"connector-secrets-{source}"
    saved_values = credential_snapshot.values if credential_snapshot else {}
    summary_fields = render_credential_summary_fields(source, form_id=form_id, values=saved_values)
    credential_status = _connector_credential_status_html(credential_snapshot)
    companies_url = None
    if source == "dbc":
        companies_url = url(f"/admin/onboarding/{company.lower()}/dbc/companies")
    qwc_href = None
    if source == "qbd":
        qwc_href = url(f"/admin/onboarding/{company.lower()}/qwc") + "?soap_url=SOAP_URL&username=QBWC_USER"
    dbc_note = dbc_permission_sets_requirement_html() if source == "dbc" else ""
    dialog_id = f"connector-guide-{source}"
    label = _CONNECTOR_LABELS.get(source, source)
    return render_template(
        "admin/onboarding/_connector_credentials_section.html",
        source=source,
        label=label,
        dialog_id=dialog_id,
        credential_status=Markup(credential_status),
        dbc_note=Markup(dbc_note),
        form_id=form_id,
        form_action_url=url(f"/admin/onboarding/{company.lower()}/secrets"),
        validate_url=url(f"/admin/onboarding/{company.lower()}/validate"),
        companies_url=companies_url,
        environment=environment,
        client_id=client_id,
        connector_guide_dialog=Markup(_connector_guide_dialog(source=source)),
        summary_fields=Markup(summary_fields),
        qwc_href=qwc_href,
    )


def render_connector_credentials(
    *,
    url: UrlFn,
    username: str,
    company: str,
    client_id: str,
    environment: str,
    connector_sources: list[str] | tuple[str, ...],
    connector_credentials: dict[str, ConnectorCredentialSnapshot] | None = None,
    flash: str = "",
) -> str:
    sources = [str(item).strip().lower() for item in connector_sources if str(item).strip()]
    if not sources:
        sources = ["dbc"]
    credential_snapshots = connector_credentials or {}
    credentials_html = "".join(
        _connector_credentials_section(
            url=url,
            company=company,
            environment=environment,
            client_id=client_id,
            source=source,
            credential_snapshot=credential_snapshots.get(source),
        )
        for source in sources
    )
    deploy_step_url = escape(
        url(
            f"/admin/onboarding/{company.lower()}/deploy"
            f"?environment={environment}&client_id={client_id}"
        )
    )
    body = f"""
    <div class="admin-shell" data-onboarding-connectors data-connector-count="{len(sources)}">
      {_shell_header(
          url=url,
          username=username,
          eyebrow=f"{company} / {client_id}",
          heading=f"Step 2 of {WIZARD_STEP_COUNT}",
          lead="Save connector secrets and validate each connector before deploying stacks.",
      )}
      {_flash(flash)}
      {_steps_flow_html(2, url=url, company=company, environment=environment, client_id=client_id)}
      <section class="card pack-card admin-onboarding-section">
        <h2>Connector credentials</h2>
        {credentials_html}
        <div class="admin-onboarding-actions">
          <a class="btn is-disabled admin-onboarding-continue-deploy"
             data-connector-continue-deploy
             href="{deploy_step_url}"
             aria-disabled="true">Continue to deploy</a>
        </div>
        <p class="admin-onboarding-continue-hint" data-connector-continue-hint>
          Validate every connector above to continue.
        </p>
      </section>
    </div>
    <style>
      {_ADMIN_SHELL_CSS}
    </style>
    <link rel="stylesheet" href="{escape(url("/static/admin-onboarding.css"))}" />
    {_connector_guide_script()}
    """
    return _onboarding_page(title=f"{company} connectors", url=url, body=body)


def render_client_deploy(
    *,
    url: UrlFn,
    username: str,
    company: str,
    client_id: str,
    environment: str,
    status_payload: dict[str, Any] | None = None,
    flash: str = "",
    build_id: str = "",
    initial_admin: dict[str, str] | None = None,
    portal_ready: bool = False,
    portal_dns_required: bool = False,
    portal_urls: dict[str, str] | None = None,
) -> str:
    deploy = (status_payload or {}).get("deploy", {})
    verification = (status_payload or {}).get("verification", {})
    stacks = deploy.get("stacks", [])
    build_html = f'<p class="pack-card-lead">Build: <code>{escape(build_id)}</code></p>' if build_id else ""
    status_url = escape(
        url(
            f"/admin/onboarding/{company.lower()}/deploy/status"
            f"?environment={environment}&client_id={client_id}"
            + (f"&build_id={build_id}" if build_id else "")
        )
    )
    credentials_step_url = escape(
        url(f"/admin/onboarding/{company.lower()}?environment={environment}&client_id={client_id}")
    )
    pipelines_step_url = escape(
        url(
            f"/admin/onboarding/{company.lower()}/pipelines"
            f"?environment={environment}&client_id={client_id}"
        )
    )
    body = f"""
    <div class="admin-shell">
      {_shell_header(
          url=url,
          username=username,
          eyebrow=f"{company} / {client_id}",
          heading=f"Step 3 of {WIZARD_STEP_COUNT}",
          lead="Deploy CloudFormation stacks and verify the client environment.",
      )}
      {_flash(flash)}
      {_steps_flow_html(3, url=url, company=company, environment=environment, client_id=client_id)}
      <section class="card pack-card admin-onboarding-section"
               data-stack-status-section
               data-stack-status-url="{status_url}"
               data-stack-poll-ms="30000"
               data-stack-build-id="{escape(build_id)}">
        <h2>Stack status</h2>
        {_stack_rows(stacks)}
        <div class="admin-onboarding-actions">
          <form method="post"
                action="{escape(url(f'/admin/onboarding/{company.lower()}/deploy'))}"
                data-stack-deploy-form>
            <input type="hidden" name="environment" value="{escape(environment)}" />
            <input type="hidden" name="client_id" value="{escape(client_id)}" />
            <button type="submit" class="btn" data-stack-deploy-btn>Deploy stacks</button>
          </form>
          <a class="btn secondary" href="{credentials_step_url}">Back to connectors</a>
          <a class="btn secondary" href="{pipelines_step_url}">Continue to pipelines</a>
        </div>
        <p class="admin-stack-deploy-status" data-stack-deploy-status hidden></p>
        {build_html}
      </section>
      <section class="card pack-card admin-onboarding-section">
        <h2>Post-deploy verification</h2>
        <div class="admin-preview-panel"><pre>{escape(str(verification))}</pre></div>
      </section>
      {_client_portal_url_section(
          portal_urls=portal_urls or {},
          ready=portal_ready,
          portal_dns_required=portal_dns_required,
      )}
      {_initial_admin_invite_section(
          url=url,
          company=company,
          environment=environment,
          client_id=client_id,
          values=initial_admin or {},
          ready=portal_ready,
          portal_dns_required=portal_dns_required,
      )}
    </div>
    <style>
      {_ADMIN_SHELL_CSS}
    </style>
    <link rel="stylesheet" href="{escape(url("/static/admin-onboarding.css"))}" />
    {_connector_guide_script()}
    """
    return _onboarding_page(title=f"{company} deploy", url=url, body=body)


def _pipeline_status_badge(status: str) -> str:
    return (
        f'<span class="admin-job-state {_stack_state_css(status)}" data-pipeline-status-badge>'
        f"{escape(status.replace('_', ' ').title())}</span>"
    )


def _pipeline_row(
    *,
    pipeline_key: str,
    label: str,
    status: str,
    note: str = "",
    execution_arn: str = "",
    has_report: bool = False,
) -> str:
    return render_template(
        "admin/onboarding/_pipeline_row.html",
        pipeline_key=pipeline_key,
        label=label,
        status=status,
        note=note,
        execution_arn=execution_arn,
        has_report=has_report,
        status_badge=Markup(_pipeline_status_badge(status)),
    )


def _ingest_report_dialog() -> str:
    return """
      <dialog id="admin-ingest-report-dialog" class="admin-ingest-report-dialog"
              aria-labelledby="admin-ingest-report-title">
        <div class="admin-ingest-report-dialog-head">
          <h3 id="admin-ingest-report-title">Ingest validation report</h3>
          <button type="button" class="btn secondary" data-ingest-report-close>Close</button>
        </div>
        <div class="admin-ingest-report-dialog-body" data-ingest-report-body>
          <p class="pack-card-lead">Loading report…</p>
        </div>
      </dialog>
    """


def render_client_pipelines(
    *,
    url: UrlFn,
    username: str,
    company: str,
    client_id: str,
    environment: str,
    connector_sources: list[str] | tuple[str, ...],
    dna_enabled: bool = True,
    status_payload: dict[str, Any] | None = None,
    flash: str = "",
) -> str:
    payload = status_payload or {}
    ingest_status = payload.get("ingest", {})
    dna_status = payload.get("dna", {})
    sources = [str(item).strip().lower() for item in connector_sources if str(item).strip()]
    if not sources:
        sources = ["dbc"]

    pipeline_rows: list[str] = []
    for source in sources:
        connector_payload = ingest_status.get(source, {}) if isinstance(ingest_status, dict) else {}
        pipeline_rows.append(
            _pipeline_row(
                pipeline_key=source,
                label=str(connector_payload.get("label") or _CONNECTOR_LABELS.get(source, source)),
                status=str(connector_payload.get("status") or "not_started"),
                note=str(connector_payload.get("note") or ""),
                execution_arn=str(connector_payload.get("execution_arn") or ""),
                has_report=bool(connector_payload.get("has_report")),
            )
        )

    dna_section = ""
    if dna_enabled:
        dna_section = f"""
        <section class="card pack-card admin-onboarding-section">
          <h2>DNA refresh</h2>
          {_pipeline_row(
              pipeline_key="dna",
              label="DNA silver + gold refresh",
              status=str(dna_status.get("status") or "not_started"),
              note="Runs the DNA apply Step Functions workflow after ingest completes.",
              execution_arn=str(dna_status.get("execution_arn") or ""),
          )}
        </section>
        """

    status_url = escape(
        url(
            f"/admin/onboarding/{company.lower()}/pipelines/status"
            f"?environment={environment}&client_id={client_id}"
        )
    )
    deploy_step_url = escape(
        url(
            f"/admin/onboarding/{company.lower()}/deploy"
            f"?environment={environment}&client_id={client_id}"
        )
    )
    ingest_kickoff_url = escape(
        url(f"/admin/onboarding/{company.lower()}/pipelines/ingest")
    )
    dna_kickoff_url = escape(url(f"/admin/onboarding/{company.lower()}/pipelines/dna"))
    ingest_report_url = escape(
        url(f"/admin/onboarding/{company.lower()}/pipelines/ingest/report")
    )

    body = f"""
    <div class="admin-shell"
         data-pipeline-status-section
         data-pipeline-status-url="{status_url}"
         data-pipeline-ingest-url="{ingest_kickoff_url}"
         data-pipeline-dna-url="{dna_kickoff_url}"
         data-pipeline-report-url="{ingest_report_url}"
         data-pipeline-environment="{escape(environment)}"
         data-pipeline-client-id="{escape(client_id)}">
      {_shell_header(
          url=url,
          username=username,
          eyebrow=f"{company} / {client_id}",
          heading=f"Step 4 of {WIZARD_STEP_COUNT}",
          lead="Manually kick off ingest and DNA refreshes, then validate bronze ingest results.",
      )}
      {_flash(flash)}
      {_steps_flow_html(4, url=url, company=company, environment=environment, client_id=client_id)}
      <section class="card pack-card admin-onboarding-section">
        <h2>Ingest refresh</h2>
        <p class="pack-card-lead">
          Start connector refresh Step Functions and monitor execution status.
          After a successful run, open the ingest validation report to review table and row counts.
        </p>
        {"".join(pipeline_rows)}
        <p class="admin-stack-deploy-status" data-pipeline-action-status hidden></p>
      </section>
      {dna_section}
      <div class="admin-onboarding-actions">
        <a class="btn secondary" href="{deploy_step_url}">Back to deploy</a>
      </div>
      {_ingest_report_dialog()}
    </div>
    <style>
      {_ADMIN_SHELL_CSS}
    </style>
    <link rel="stylesheet" href="{escape(url("/static/admin-onboarding.css"))}" />
    {_connector_guide_script()}
    """
    return _onboarding_page(title=f"{company} pipelines", url=url, body=body)


def render_client_detail(
    *,
    url: UrlFn,
    username: str,
    company: str,
    client_id: str,
    environment: str,
    connector_sources: list[str] | tuple[str, ...],
    connector_credentials: dict[str, ConnectorCredentialSnapshot] | None = None,
    status_payload: dict[str, Any] | None = None,
    flash: str = "",
    build_id: str = "",
) -> str:
    return render_connector_credentials(
        url=url,
        username=username,
        company=company,
        client_id=client_id,
        environment=environment,
        connector_sources=connector_sources,
        connector_credentials=connector_credentials,
        flash=flash,
    )

