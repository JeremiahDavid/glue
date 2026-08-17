"""HTML views for the platform admin onboarding wizard."""

from __future__ import annotations

from html import escape
from typing import Any, Callable

from meshflow.dna.web.admin.views import _ADMIN_NAV, _ADMIN_SHELL_CSS
from meshflow.client_registry import CLIENT_ID_HTML_PATTERN
from meshflow.dna.web.theme import render_page

UrlFn = Callable[[str], str]

_ONBOARDING_STYLES = """
      .admin-onboarding-section { margin-bottom: 1rem; }
      .admin-onboarding-section h2,
      .admin-onboarding-section-card h2 {
        font-size: 1.2rem;
        margin: 0 0 0.75rem;
        color: var(--text);
      }
      .admin-onboarding-form .admin-onboarding-section-card + .admin-onboarding-section-card {
        margin-top: 1rem;
      }
      .admin-onboarding-form-grid {
        display: grid;
        gap: 0.85rem;
      }
      .admin-onboarding-form {
        color-scheme: dark;
      }
      .admin-onboarding-form .form-field { margin-bottom: 0; }
      .admin-onboarding-form select.admin-onboarding-select {
        width: 100%;
        padding: 0.6rem 2rem 0.6rem 0.75rem;
        border-radius: var(--radius-sm);
        border: 1px solid var(--border);
        color: var(--text);
        font: inherit;
        font-size: inherit;
        color-scheme: dark;
        -webkit-appearance: none;
        -moz-appearance: none;
        appearance: none;
        background: #060912
          url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%238b97ad' d='M2.5 4.5 6 8l3.5-3.5'/%3E%3C/svg%3E")
          no-repeat right 0.75rem center / 12px !important;
      }
      .admin-onboarding-form select.admin-onboarding-select::-ms-expand {
        display: none;
      }
      .admin-onboarding-form select.admin-onboarding-select:focus {
        background: #060912
          url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%238b97ad' d='M2.5 4.5 6 8l3.5-3.5'/%3E%3C/svg%3E")
          no-repeat right 0.75rem center / 12px !important;
        outline: none;
        border-color: rgba(56, 189, 248, 0.45);
        box-shadow: 0 0 0 3px rgba(56, 189, 248, 0.12);
      }
      .admin-onboarding-form select.admin-onboarding-select option {
        background-color: #060912;
        color: var(--text);
      }
      .admin-onboarding-form .admin-onboarding-section-card {
        overflow: visible;
      }
      .admin-onboarding-form-grid {
        overflow: visible;
      }
      .admin-onboarding-actions {
        display: flex;
        gap: 0.65rem;
        flex-wrap: wrap;
        align-items: center;
        margin-top: 0.85rem;
      }
      .admin-onboarding-section .table-wrap + .admin-onboarding-actions,
      .admin-onboarding-section .pack-card-lead + .admin-onboarding-actions {
        margin-top: 0;
        padding-top: 1.5rem;
      }
      .admin-onboarding-form > .admin-onboarding-actions {
        margin-top: 1.25rem;
      }
      .admin-preview-panel {
        margin-top: 0.75rem;
        border: 1px solid var(--border);
        border-radius: var(--radius);
        background: var(--bg-elevated);
        padding: 1rem 1.1rem;
        overflow-x: auto;
      }
      .admin-preview-panel pre {
        margin: 0;
        font-family: var(--font-mono);
        font-size: 0.82rem;
        line-height: 1.55;
        white-space: pre-wrap;
        color: var(--text-muted);
      }
"""


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
    lead_html = f'<p class="pack-card-lead">{lead}</p>' if lead else ""
    action_block = action_html or (
        f'<form method="post" action="{escape(url("/admin/logout"))}">'
        f'<button type="submit" class="btn secondary">Sign out</button></form>'
    )
    return f"""
      <header class="admin-shell-header">
        <div>
          <p class="admin-eyebrow">{escape(eyebrow)}</p>
          <h1>{escape(heading)}</h1>
          {lead_html}
          <p class="pack-card-lead">Signed in as <strong>{escape(username)}</strong>.</p>
        </div>
        {action_block}
      </header>
    """


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


def _stack_rows(stacks: list[dict[str, Any]]) -> str:
    if not stacks:
        return '<p class="pack-card-lead">No stacks configured.</p>'
    rows = []
    for item in stacks:
        status = str(item.get("status", "unknown"))
        status_label = escape(status.replace("_", " ").title())
        rows.append(
            "<tr>"
            f"<td><code>{escape(str(item.get('stack_name', '')))}</code></td>"
            f'<td><span class="admin-job-state {_stack_state_css(status)}">{status_label}</span></td>'
            f"<td>{escape(str(item.get('status_reason', '')))}</td>"
            "</tr>"
        )
    return (
        '<div class="table-wrap"><table><thead><tr>'
        "<th>Stack</th><th>Status</th><th>Reason</th>"
        f"</tr></thead><tbody>{''.join(rows)}</tbody></table></div>"
    )


def _form_section(title: str, content: str) -> str:
    return f"""
      <section class="card pack-card admin-onboarding-section-card">
        <h2>{escape(title)}</h2>
        {content}
      </section>
    """


def _field_label(name: str, label: str, *, hint: str = "") -> str:
    title_attr = f' title="{escape(hint)}"' if hint.strip() else ""
    return f'<label for="{escape(name)}"{title_attr}>{escape(label)}</label>'


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
    req = " required" if required else ""
    min_attr = f' min="{min_value}"' if min_value is not None else ""
    max_attr = f' max="{max_value}"' if max_value is not None else ""
    pattern_attr = f' pattern="{escape(pattern)}"' if pattern else ""
    maxlength_attr = f' maxlength="{maxlength}"' if maxlength is not None else ""
    title_attr = f' title="{escape(hint)}"' if hint else ""
    return f"""
      <div class="form-field">
        {_field_label(name, label, hint=hint)}
        <input id="{escape(name)}" name="{escape(name)}" type="{escape(field_type)}"
               value="{escape(value)}"{req}{min_attr}{max_attr}{pattern_attr}{maxlength_attr}{title_attr} />
      </div>
    """


def _form_select(
    name: str,
    label: str,
    options_html: str,
    *,
    hint: str = "",
) -> str:
    return f"""
      <div class="form-field">
        {_field_label(name, label, hint=hint)}
        <select id="{escape(name)}" name="{escape(name)}" class="admin-onboarding-select">{options_html}</select>
      </div>
    """


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
            "<tr>"
            f"<td>{company}</td>"
            f"<td>{client_id}</td>"
            f"<td>{environment}</td>"
            f"<td>{escape(str(client.get('connector_source', '')))}</td>"
            f'<td><a class="btn secondary" href="{detail_url}">Manage</a></td>'
            "</tr>"
        )
    table = (
        '<div class="table-wrap"><table><thead><tr>'
        "<th>Company</th><th>Client</th><th>Env</th><th>Connector</th><th></th>"
        f"</tr></thead><tbody>{''.join(rows) or '<tr><td colspan=\"5\">No clients yet.</td></tr>'}</tbody></table></div>"
    )
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
      {_ONBOARDING_STYLES}
      .admin-job-state {{
        font-size: 0.75rem; font-weight: 600; padding: 0.2rem 0.5rem;
        border-radius: var(--radius-sm); border: 1px solid var(--border);
        background: rgba(255, 255, 255, 0.02); color: var(--text-muted);
        text-transform: capitalize;
      }}
      .admin-job-state.is-ok {{
        border-color: rgba(20, 184, 166, 0.28); background: rgba(20, 184, 166, 0.06);
        color: #99f6e4;
      }}
      .admin-job-state.is-running {{
        border-color: rgba(56, 189, 248, 0.35); background: rgba(56, 189, 248, 0.08);
        color: #7dd3fc;
      }}
      .admin-job-state.is-error {{
        border-color: rgba(239, 68, 68, 0.28); background: rgba(239, 68, 68, 0.1);
        color: #fca5a5;
      }}
    </style>
    """
    return _onboarding_page(title="Onboarding", url=url, body=body)


def render_onboarding_wizard(
    *,
    url: UrlFn,
    username: str,
    step: int,
    form_values: dict[str, str] | None = None,
    error: str = "",
    preview: dict[str, Any] | None = None,
) -> str:
    values = dict(form_values or {})
    preview_html = ""
    if preview:
        preview_html = (
            '<div class="admin-preview-panel"><pre>'
            + escape(str(preview))
            + "</pre></div>"
        )
    connector_options = (
        f'<option value="dbc" {"selected" if values.get("connector_source", "dbc") == "dbc" else ""}>'
        "Business Central</option>"
        f'<option value="qbo" {"selected" if values.get("connector_source") == "qbo" else ""}>'
        "QuickBooks Online</option>"
        f'<option value="qbd" {"selected" if values.get("connector_source") == "qbd" else ""}>'
        "QuickBooks Desktop</option>"
    )
    body = f"""
    <div class="admin-shell">
      {_shell_header(
          url=url,
          username=username,
          eyebrow="Onboarding wizard",
          heading=f"Step {step} of 5",
          lead="Create a client registry entry and default portal settings.",
      )}
      {_flash(error, error=True)}
      <form method="post" action="{escape(url('/admin/onboarding/new'))}" class="admin-onboarding-form">
        <input type="hidden" name="step" value="{step}" />
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
            "Connector",
            f'''<div class="admin-onboarding-form-grid">
            {_form_select(
                "connector_source",
                "Source",
                connector_options,
                hint="ERP or accounting system for bronze ingest. Drives which connector stack and secret fields are provisioned.",
            )}
            {_form_field(
                "entity_bundle",
                "Entity bundle",
                value=values.get("entity_bundle", "full"),
                hint="Named entity set to sync (e.g. full, full_accounting). Controls which tables are included in scheduled ingest.",
            )}
            {_form_field(
                "schedule_hour",
                "Schedule hour (Eastern)",
                value=values.get("schedule_hour", "6"),
                field_type="number",
                min_value=0,
                max_value=23,
                hint="Hour in US Eastern time (0–23) for the daily bronze ingest schedule. Not used for QuickBooks Desktop (Web Connector pull).",
            )}
            {_form_field(
                "schedule_minute",
                "Schedule minute",
                value=values.get("schedule_minute", "0"),
                field_type="number",
                min_value=0,
                max_value=59,
                hint="Minute (0–59) in US Eastern time, paired with schedule hour for EventBridge cron.",
            )}
          </div>''',
        )}
        {preview_html}
        <div class="admin-onboarding-actions">
          <button type="submit" class="btn">Save client config</button>
          <a class="btn secondary" href="{escape(url('/admin/onboarding'))}">Cancel</a>
        </div>
      </form>
    </div>
    <style>
      {_ADMIN_SHELL_CSS}
      {_ONBOARDING_STYLES}
    </style>
    """
    return _onboarding_page(title="New client", url=url, body=body)


def render_client_detail(
    *,
    url: UrlFn,
    username: str,
    company: str,
    client_id: str,
    environment: str,
    connector_source: str,
    status_payload: dict[str, Any] | None = None,
    flash: str = "",
    build_id: str = "",
) -> str:
    deploy = (status_payload or {}).get("deploy", {})
    verification = (status_payload or {}).get("verification", {})
    stacks = deploy.get("stacks", [])
    secret_form = "".join(
        _form_field(name, label, hint=hint) for name, label, hint in _connector_secret_fields(connector_source)
    )
    qbd_note = ""
    if connector_source == "qbd":
        qwc_url = escape(url(f"/admin/onboarding/{company.lower()}/qwc")) + "?soap_url=SOAP_URL&username=QBWC_USER"
        qbd_note = (
            f'<p class="pack-card-lead">After ingest deploy, download the '
            f'<a href="{qwc_url}">.qwc file</a> for QuickBooks Web Connector.</p>'
        )
    build_html = f'<p class="pack-card-lead">Build: <code>{escape(build_id)}</code></p>' if build_id else ""
    body = f"""
    <div class="admin-shell">
      {_shell_header(
          url=url,
          username=username,
          eyebrow=f"{company} / {client_id}",
          heading="Onboarding status",
          lead="Deploy stacks, store connector credentials, and verify the client environment.",
      )}
      {_flash(flash)}
      <section class="card pack-card admin-onboarding-section">
        <h2>Stack status</h2>
        {_stack_rows(stacks)}
        <div class="admin-onboarding-actions">
          <form method="post" action="{escape(url(f'/admin/onboarding/{company.lower()}/deploy'))}">
            <input type="hidden" name="environment" value="{escape(environment)}" />
            <input type="hidden" name="client_id" value="{escape(client_id)}" />
            <button type="submit" class="btn">Deploy stacks</button>
          </form>
        </div>
        {build_html}
      </section>
      <section class="card pack-card admin-onboarding-section">
        <h2>Connector credentials</h2>
        <form method="post" action="{escape(url(f'/admin/onboarding/{company.lower()}/secrets'))}" class="admin-onboarding-form">
          <input type="hidden" name="environment" value="{escape(environment)}" />
          <input type="hidden" name="client_id" value="{escape(client_id)}" />
          <input type="hidden" name="connector_source" value="{escape(connector_source)}" />
          <div class="admin-onboarding-form-grid">
            {secret_form}
          </div>
          <div class="admin-onboarding-actions">
            <button type="submit" class="btn">Save secret</button>
            <button formaction="{escape(url(f'/admin/onboarding/{company.lower()}/validate'))}" formmethod="post" class="btn secondary">Validate connector</button>
          </div>
        </form>
        {qbd_note}
      </section>
      <section class="card pack-card admin-onboarding-section">
        <h2>Post-deploy verification</h2>
        <div class="admin-preview-panel"><pre>{escape(str(verification))}</pre></div>
      </section>
    </div>
    <style>
      {_ADMIN_SHELL_CSS}
      {_ONBOARDING_STYLES}
      .admin-job-state {{
        font-size: 0.75rem; font-weight: 600; padding: 0.2rem 0.5rem;
        border-radius: var(--radius-sm); border: 1px solid var(--border);
        background: rgba(255, 255, 255, 0.02); color: var(--text-muted);
        text-transform: capitalize;
      }}
      .admin-job-state.is-ok {{
        border-color: rgba(20, 184, 166, 0.28); background: rgba(20, 184, 166, 0.06);
        color: #99f6e4;
      }}
      .admin-job-state.is-running {{
        border-color: rgba(56, 189, 248, 0.35); background: rgba(56, 189, 248, 0.08);
        color: #7dd3fc;
      }}
      .admin-job-state.is-error {{
        border-color: rgba(239, 68, 68, 0.28); background: rgba(239, 68, 68, 0.1);
        color: #fca5a5;
      }}
    </style>
    """
    return _onboarding_page(title=f"{company} onboarding", url=url, body=body)


def _connector_secret_fields(source: str) -> list[tuple[str, str, str]]:
    if source == "qbo":
        return [
            (
                "QBO_CLIENT_ID",
                "QBO client id",
                "Intuit developer application client id used for OAuth and API access.",
            ),
            (
                "QBO_CLIENT_SECRET",
                "QBO client secret",
                "Intuit app client secret. Stored in Secrets Manager for the ingest Lambda.",
            ),
            (
                "QBO_ENVIRONMENT",
                "QBO environment",
                "Intuit API tier: sandbox for testing or production for live company data.",
            ),
            (
                "QBO_REDIRECT_URI",
                "QBO redirect URI",
                "OAuth redirect URL registered in the Intuit developer portal for this app.",
            ),
        ]
    if source == "qbd":
        return [
            (
                "QBD_QBWC_USERNAME",
                "QBWC username",
                "Username QuickBooks Web Connector uses to authenticate to the ingest SOAP endpoint.",
            ),
            (
                "QBD_QBWC_PASSWORD",
                "QBWC password",
                "Password paired with the QBWC username for SOAP authentication.",
            ),
            (
                "QBWC_SOAP_URL",
                "SOAP URL (after ingest deploy)",
                "API Gateway SOAP endpoint URL from the deployed QBD ingest stack output.",
            ),
            (
                "QBD_COMPANY_NAME",
                "Company name",
                "QuickBooks company file name as shown in Web Connector.",
            ),
        ]
    return [
        (
            "BC_CLIENT_ID",
            "Entra client id",
            "Microsoft Entra application (client) id authorized for Business Central API access.",
        ),
        (
            "BC_CLIENT_SECRET",
            "Entra client secret",
            "Client secret for the Entra app. Stored in Secrets Manager for ingest.",
        ),
        (
            "BC_TENANT_ID",
            "Entra tenant id",
            "Microsoft Entra directory id that owns the Business Central environment.",
        ),
        (
            "BC_ENVIRONMENT_NAME",
            "BC environment name",
            "Business Central environment name, such as Production or a named sandbox.",
        ),
        (
            "BC_COMPANY_ID",
            "BC company id",
            "GUID of the Business Central company to sync into the lake.",
        ),
    ]
