"""HTML views for the platform admin onboarding wizard."""

from __future__ import annotations

from html import escape
from typing import Any, Callable

from meshflow.dna.web.theme import render_page

UrlFn = Callable[[str], str]

_ONBOARDING_NAV = (
    ("/admin", "Jobs"),
    ("/admin/onboarding", "Onboarding"),
    ("/admin/architecture", "Architecture"),
)


def _nav_html(active_path: str, *, url: UrlFn) -> str:
    items = []
    for href, label in _ONBOARDING_NAV:
        active = ' class="is-active"' if active_path.startswith(href) else ""
        items.append(f'<a href="{escape(url(href))}"{active}>{escape(label)}</a>')
    return '<nav class="admin-top-nav">' + "".join(items) + "</nav>"


def _flash(message: str) -> str:
    if not message.strip():
        return ""
    return f'<p class="admin-flash">{escape(message)}</p>'


def _stack_rows(stacks: list[dict[str, Any]]) -> str:
    if not stacks:
        return "<p>No stacks configured.</p>"
    rows = []
    for item in stacks:
        status = escape(str(item.get("status", "unknown")))
        rows.append(
            "<tr>"
            f"<td><code>{escape(str(item.get('stack_name', '')))}</code></td>"
            f'<td><span class="admin-job-state">{status}</span></td>'
            f"<td>{escape(str(item.get('status_reason', '')))}</td>"
            "</tr>"
        )
    return (
        "<table class='admin-table'><thead><tr><th>Stack</th><th>Status</th><th>Reason</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def render_onboarding_home(
    *,
    url: UrlFn,
    clients: list[dict[str, Any]],
    flash: str = "",
) -> str:
    rows = []
    for client in clients:
        company = escape(str(client.get("company", "")))
        client_id = escape(str(client.get("client_id", "")))
        environment = escape(str(client.get("environment", "")))
        detail_url = escape(url(f"/admin/onboarding/{company.lower()}?environment={environment}&client_id={client_id}"))
        rows.append(
            "<tr>"
            f"<td>{company}</td>"
            f"<td>{client_id}</td>"
            f"<td>{environment}</td>"
            f"<td>{escape(str(client.get('connector_source', '')))}</td>"
            f'<td><a href="{detail_url}">Manage</a></td>'
            "</tr>"
        )
    table = (
        "<table class='admin-table'><thead><tr><th>Company</th><th>Client</th><th>Env</th><th>Connector</th><th></th></tr></thead>"
        f"<tbody>{''.join(rows) or '<tr><td colspan=\"5\">No clients yet.</td></tr>'}</tbody></table>"
    )
    body = f"""
    <div class="admin-shell">
      {_nav_html("/admin/onboarding", url=url)}
      <header class="admin-shell-header">
        <div>
          <p class="admin-eyebrow">Platform admin</p>
          <h1>Client onboarding</h1>
          <p>Provision ingest, DNA, and portal stacks for new clients.</p>
        </div>
        <a class="admin-button" href="{escape(url('/admin/onboarding/new'))}">New client</a>
      </header>
      {_flash(flash)}
      {table}
    </div>
    """
    return render_page(title="Onboarding", body=body, active_path="/admin/onboarding")


def render_onboarding_wizard(
    *,
    url: UrlFn,
    step: int,
    form_values: dict[str, str] | None = None,
    error: str = "",
    preview: dict[str, Any] | None = None,
) -> str:
    values = dict(form_values or {})
    preview_html = ""
    if preview:
        preview_html = "<pre class='admin-preview'>" + escape(str(preview)) + "</pre>"

    body = f"""
    <div class="admin-shell">
      {_nav_html("/admin/onboarding", url=url)}
      <header class="admin-shell-header">
        <div>
          <p class="admin-eyebrow">Onboarding wizard</p>
          <h1>Step {step} of 5</h1>
        </div>
      </header>
      {_flash(error)}
      <form method="post" action="{escape(url('/admin/onboarding/new'))}" class="admin-form">
        <input type="hidden" name="step" value="{step}" />
        <fieldset>
          <legend>Client identity</legend>
          <label>Company (data tenant)<input name="company" value="{escape(values.get('company', ''))}" required /></label>
          <label>Portal client id<input name="client_id" value="{escape(values.get('client_id', ''))}" required /></label>
          <label>Environment<input name="environment" value="{escape(values.get('environment', 'dev'))}" required /></label>
          <label>Display name<input name="display_name" value="{escape(values.get('display_name', ''))}" required /></label>
          <label>Reporting hostname<input name="reporting_hostname" value="{escape(values.get('reporting_hostname', ''))}" required /></label>
        </fieldset>
        <fieldset>
          <legend>Connector</legend>
          <label>Source
            <select name="connector_source">
              <option value="dbc" {"selected" if values.get('connector_source', 'dbc') == 'dbc' else ''}>Business Central</option>
              <option value="qbo" {"selected" if values.get('connector_source') == 'qbo' else ''}>QuickBooks Online</option>
              <option value="qbd" {"selected" if values.get('connector_source') == 'qbd' else ''}>QuickBooks Desktop</option>
            </select>
          </label>
          <label>Entity bundle<input name="entity_bundle" value="{escape(values.get('entity_bundle', 'full'))}" /></label>
          <label>Schedule hour<input name="schedule_hour" type="number" min="0" max="23" value="{escape(values.get('schedule_hour', '6'))}" /></label>
          <label>Schedule minute<input name="schedule_minute" type="number" min="0" max="59" value="{escape(values.get('schedule_minute', '0'))}" /></label>
        </fieldset>
        <fieldset>
          <legend>DNA &amp; portal</legend>
          <label><input type="checkbox" name="dna_enabled" value="on" {"checked" if values.get('dna_enabled', 'on') in {'on', 'true', '1'} else ''}/> Enable DNA stack</label>
          <label>DNA source<input name="dna_source" value="{escape(values.get('dna_source', values.get('connector_source', 'dbc')))}" /></label>
          <label>DNA schedule hour<input name="dna_schedule_hour" type="number" min="0" max="23" value="{escape(values.get('dna_schedule_hour', '7'))}" /></label>
          <label>Welcome title<input name="welcome_title" value="{escape(values.get('welcome_title', 'Your operational dashboard'))}" /></label>
          <label>Welcome message<textarea name="welcome_message">{escape(values.get('welcome_message', ''))}</textarea></label>
          <label>Accent color<input name="accent_color" value="{escape(values.get('accent_color', '#14b8a6'))}" /></label>
          <label>Max users<input name="max_users" type="number" min="1" value="{escape(values.get('max_users', '10'))}" /></label>
        </fieldset>
        {preview_html}
        <button type="submit" class="admin-button">Save client config</button>
      </form>
    </div>
    """
    return render_page(title="New client", body=body, active_path="/admin/onboarding")


def render_client_detail(
    *,
    url: UrlFn,
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
    secret_fields = _connector_secret_fields(connector_source)
    secret_form = "".join(
        f'<label>{escape(label)}<input name="{escape(name)}" /></label>'
        for name, label in secret_fields
    )
    body = f"""
    <div class="admin-shell">
      {_nav_html("/admin/onboarding", url=url)}
      <header class="admin-shell-header">
        <div>
          <p class="admin-eyebrow">{escape(company)} / {escape(client_id)}</p>
          <h1>Onboarding status</h1>
        </div>
      </header>
      {_flash(flash)}
      <section>
        <h2>Stack status</h2>
        {_stack_rows(stacks)}
        <form method="post" action="{escape(url(f'/admin/onboarding/{company.lower()}/deploy'))}" class="admin-inline-form">
          <input type="hidden" name="environment" value="{escape(environment)}" />
          <input type="hidden" name="client_id" value="{escape(client_id)}" />
          <button type="submit" class="admin-button">Deploy stacks</button>
        </form>
        {"<p>Build: <code>" + escape(build_id) + "</code></p>" if build_id else ""}
      </section>
      <section>
        <h2>Connector credentials</h2>
        <form method="post" action="{escape(url(f'/admin/onboarding/{company.lower()}/secrets'))}" class="admin-form">
          <input type="hidden" name="environment" value="{escape(environment)}" />
          <input type="hidden" name="client_id" value="{escape(client_id)}" />
          <input type="hidden" name="connector_source" value="{escape(connector_source)}" />
          {secret_form}
          <button type="submit" class="admin-button">Save secret</button>
          <button formaction="{escape(url(f'/admin/onboarding/{company.lower()}/validate'))}" formmethod="post" class="admin-button-secondary">Validate connector</button>
        </form>
        {"<p>After ingest deploy, download the <a href=\"" + escape(url(f'/admin/onboarding/{company.lower()}/qwc')) + "?soap_url=SOAP_URL&username=QBWC_USER\">.qwc file</a> for QuickBooks Web Connector.</p>" if connector_source == 'qbd' else ''}
      </section>
      <section>
        <h2>Post-deploy verification</h2>
        <pre class="admin-preview">{escape(str(verification))}</pre>
      </section>
    </div>
    """
    return render_page(title=f"{company} onboarding", body=body, active_path="/admin/onboarding")


def _connector_secret_fields(source: str) -> list[tuple[str, str]]:
    if source == "qbo":
        return [
            ("QBO_CLIENT_ID", "QBO client id"),
            ("QBO_CLIENT_SECRET", "QBO client secret"),
            ("QBO_ENVIRONMENT", "QBO environment"),
            ("QBO_REDIRECT_URI", "QBO redirect URI"),
        ]
    if source == "qbd":
        return [
            ("QBD_QBWC_USERNAME", "QBWC username"),
            ("QBD_QBWC_PASSWORD", "QBWC password"),
            ("QBWC_SOAP_URL", "SOAP URL (after ingest deploy)"),
            ("QBD_COMPANY_NAME", "Company name"),
        ]
    return [
        ("BC_CLIENT_ID", "Entra client id"),
        ("BC_CLIENT_SECRET", "Entra client secret"),
        ("BC_TENANT_ID", "Entra tenant id"),
        ("BC_ENVIRONMENT_NAME", "BC environment name"),
        ("BC_COMPANY_ID", "BC company id"),
    ]
