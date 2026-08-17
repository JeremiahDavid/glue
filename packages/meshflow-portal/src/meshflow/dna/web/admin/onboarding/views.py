"""HTML views for the platform admin onboarding wizard."""

from __future__ import annotations

from html import escape
from typing import Any, Callable

from meshflow.dna.web.admin.views import _ADMIN_NAV, _ADMIN_SHELL_CSS
from meshflow.client_registry import CLIENT_ID_HTML_PATTERN
from meshflow.dna.web.admin.onboarding.guides import render_connector_guide_html
from meshflow.dna.web.admin.onboarding.handlers import (
    ONBOARDING_STEP_LABELS,
    WIZARD_STEP_COUNT,
    _CONNECTOR_DEFAULTS,
    entity_bundles_for_connector,
)
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
      .admin-onboarding-connector-list {
        display: grid;
        gap: 1rem;
      }
      .admin-onboarding-connector-card {
        border: 1px solid var(--border);
        border-radius: var(--radius-sm);
        padding: 0.9rem 1rem;
        background: rgba(255, 255, 255, 0.02);
      }
      .admin-onboarding-connector-toggle {
        display: flex;
        align-items: center;
        gap: 0.55rem;
        margin-bottom: 0.75rem;
        font-size: 0.95rem;
        font-weight: 600;
        color: var(--text);
        cursor: pointer;
      }
      .admin-onboarding-connector-credentials + .admin-onboarding-connector-credentials {
        margin-top: 1.25rem;
        padding-top: 1.25rem;
        border-top: 1px solid var(--border);
      }
      .admin-onboarding-connector-credentials-head {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 0.75rem;
        flex-wrap: wrap;
        margin-bottom: 0.75rem;
      }
      .admin-onboarding-connector-credentials h3 {
        margin: 0;
        font-size: 1rem;
        color: var(--text);
      }
      .admin-connector-guide-dialog {
        width: min(52rem, calc(100vw - 2rem));
        max-height: min(85vh, 48rem);
        margin: auto;
        padding: 0;
        border: 1px solid var(--border-strong);
        border-radius: var(--radius);
        background: #0c1220;
        color: var(--text);
        box-shadow: 0 18px 48px rgba(0, 0, 0, 0.72);
      }
      .admin-connector-guide-dialog::backdrop {
        background: rgba(2, 6, 14, 0.78);
      }
      .admin-connector-guide-dialog-head {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 0.75rem;
        padding: 0.95rem 1.1rem;
        border-bottom: 1px solid var(--border);
        background: #0e1626;
      }
      .admin-connector-guide-dialog-head h3 {
        margin: 0;
        font-size: 0.98rem;
        font-weight: 600;
        color: var(--text);
      }
      .admin-connector-guide-dialog-body {
        padding: 1rem 1.1rem 1.15rem;
        overflow: auto;
        max-height: calc(min(85vh, 48rem) - 3.75rem);
        background: #0c1220;
      }
      .admin-connector-guide-content h1,
      .admin-connector-guide-content h2,
      .admin-connector-guide-content h3 {
        margin: 1.1rem 0 0.55rem;
        color: var(--text);
        line-height: 1.35;
      }
      .admin-connector-guide-content h1:first-child,
      .admin-connector-guide-content h2:first-child,
      .admin-connector-guide-content h3:first-child {
        margin-top: 0;
      }
      .admin-connector-guide-content h1 { font-size: 1.15rem; }
      .admin-connector-guide-content h2 { font-size: 1.02rem; }
      .admin-connector-guide-content h3 { font-size: 0.94rem; }
      .admin-connector-guide-content p,
      .admin-connector-guide-content li {
        font-size: 0.88rem;
        line-height: 1.55;
        color: var(--text-muted);
      }
      .admin-connector-guide-content ul {
        margin: 0.35rem 0 0.75rem;
        padding-left: 1.2rem;
      }
      .admin-connector-guide-content blockquote {
        margin: 0.65rem 0;
        padding: 0.55rem 0.75rem;
        border-left: 3px solid rgba(56, 189, 248, 0.35);
        background: rgba(255, 255, 255, 0.02);
      }
      .admin-connector-guide-content pre {
        margin: 0.65rem 0;
        padding: 0.75rem 0.85rem;
        border-radius: var(--radius-sm);
        border: 1px solid var(--border);
        background: #060912;
        overflow-x: auto;
      }
      .admin-connector-guide-content pre code {
        font-family: var(--font-mono);
        font-size: 0.8rem;
        line-height: 1.5;
        color: #cbd5e1;
        white-space: pre-wrap;
      }
      .admin-connector-guide-content code {
        font-family: var(--font-mono);
        font-size: 0.82em;
        color: #93c5fd;
      }
      .admin-connector-guide-content a {
        color: #7dd3fc;
      }
      .admin-connector-guide-content hr {
        border: none;
        border-top: 1px solid var(--border);
        margin: 1rem 0;
      }
      .admin-connector-guide-content .table-wrap {
        margin: 0.65rem 0 0.85rem;
      }
      .admin-onboarding-steps {
        display: flex;
        align-items: flex-start;
        justify-content: center;
        gap: 0;
        margin: 0 0 1.75rem;
        padding: 0;
        list-style: none;
      }
      .admin-onboarding-step {
        flex: 0 1 auto;
        display: flex;
        flex-direction: column;
        align-items: center;
        text-align: center;
        min-width: 0;
      }
      .admin-onboarding-step-bridge {
        flex: 1 1 5.5rem;
        display: flex;
        align-items: center;
        align-self: center;
        min-width: 3.5rem;
        max-width: 7rem;
        padding: 0 0.85rem;
        margin-top: -1.15rem;
      }
      .admin-onboarding-step-arrow {
        position: relative;
        flex: 1;
        height: 1px;
        background: rgba(255, 255, 255, 0.18);
      }
      .admin-onboarding-step-arrow::after {
        content: "";
        position: absolute;
        top: 50%;
        right: -1px;
        width: 0.38rem;
        height: 0.38rem;
        border-top: 1px solid rgba(255, 255, 255, 0.18);
        border-right: 1px solid rgba(255, 255, 255, 0.18);
        transform: translateY(-50%) rotate(45deg);
      }
      .admin-onboarding-step.is-complete + .admin-onboarding-step-bridge .admin-onboarding-step-arrow {
        background: rgba(20, 184, 166, 0.42);
      }
      .admin-onboarding-step.is-complete + .admin-onboarding-step-bridge .admin-onboarding-step-arrow::after {
        border-top-color: rgba(20, 184, 166, 0.42);
        border-right-color: rgba(20, 184, 166, 0.42);
      }
      .admin-onboarding-step-marker {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        min-width: 5.4rem;
        padding: 0.42rem 1rem;
        border-radius: 999px;
        border: 1px solid rgba(255, 255, 255, 0.14);
        background: rgba(255, 255, 255, 0.03);
        font-size: 0.78rem;
        font-weight: 600;
        letter-spacing: 0.02em;
        color: rgba(203, 213, 225, 0.72);
        white-space: nowrap;
      }
      .admin-onboarding-step.is-active .admin-onboarding-step-marker {
        border-color: rgba(56, 189, 248, 0.38);
        background: rgba(56, 189, 248, 0.07);
        color: #bae6fd;
        box-shadow: 0 0 0 1px rgba(56, 189, 248, 0.08);
      }
      .admin-onboarding-step.is-complete .admin-onboarding-step-marker {
        border-color: rgba(20, 184, 166, 0.32);
        background: rgba(20, 184, 166, 0.06);
        color: #99f6e4;
      }
      .admin-onboarding-step-label {
        margin-top: 0.5rem;
        font-size: 0.72rem;
        color: rgba(148, 163, 184, 0.78);
        line-height: 1.3;
        padding: 0 0.2rem;
      }
      .admin-onboarding-step.is-active .admin-onboarding-step-label {
        color: rgba(226, 232, 240, 0.92);
        font-weight: 600;
      }
      .admin-onboarding-step-btn {
        all: unset;
        cursor: pointer;
        display: flex;
        flex-direction: column;
        align-items: center;
        width: 100%;
        text-decoration: none;
        color: inherit;
      }
      .admin-onboarding-step-btn:hover .admin-onboarding-step-marker {
        border-color: rgba(56, 189, 248, 0.32);
        background: rgba(56, 189, 248, 0.05);
      }
      .admin-onboarding-step.is-upcoming .admin-onboarding-step-marker {
        opacity: 0.72;
      }
"""

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
    return "".join(
        f'<option value="{escape(bundle)}"'
        f'{" selected" if bundle == selected_key else ""}>'
        f"{escape(bundle)}</option>"
        for bundle in bundles
    )


def _connector_wizard_block(source: str, values: dict[str, str]) -> str:
    defaults = _CONNECTOR_DEFAULTS[source]
    prefix = f"connector_{source}"
    enabled = _connector_enabled(values, source, default=(source == "dbc"))
    checked_attr = " checked" if enabled else ""
    selected_bundle = values.get(f"{prefix}_entity_bundle", str(defaults["entity_bundle"]))
    fields = [
        _form_select(
            f"{prefix}_entity_bundle",
            "Entity bundle",
            _entity_bundle_options(source, selected_bundle),
            hint="Named entity set to sync for this connector.",
        ),
    ]
    if source in {"dbc", "qbo"}:
        fields.extend(
            [
                _form_field(
                    f"{prefix}_schedule_hour",
                    "Schedule hour (Eastern)",
                    value=values.get(f"{prefix}_schedule_hour", str(defaults["schedule_hour"])),
                    field_type="number",
                    min_value=0,
                    max_value=23,
                    hint="Hour in US Eastern time (0–23) for the daily bronze ingest schedule.",
                ),
                _form_field(
                    f"{prefix}_schedule_minute",
                    "Schedule minute",
                    value=values.get(f"{prefix}_schedule_minute", str(defaults["schedule_minute"])),
                    field_type="number",
                    min_value=0,
                    max_value=59,
                    hint="Minute (0–59) in US Eastern time, paired with schedule hour.",
                ),
            ]
        )
    if source == "qbo":
        fields.append(
            _form_field(
                f"{prefix}_tier",
                "QBO environment",
                value=values.get(f"{prefix}_tier", str(defaults.get("tier", "sandbox"))),
                hint="Intuit API tier: sandbox for testing or production for live company data.",
            )
        )
    return f"""
      <div class="admin-onboarding-connector-card">
        <label class="admin-onboarding-connector-toggle" for="{escape(prefix)}_enabled">
          <input id="{escape(prefix)}_enabled" type="checkbox" name="{escape(prefix)}_enabled" value="on"{checked_attr}/>
          <span>{escape(_CONNECTOR_LABELS[source])}</span>
        </label>
        <div class="admin-onboarding-form-grid">
          {"".join(fields)}
        </div>
      </div>
    """


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
    return ""


def _step_marker_html(step_number: int) -> str:
    return f"Step {step_number}"


def _step_item_html(
    *,
    step_number: int,
    state: str,
    label: str,
    href: str,
) -> str:
    marker = _step_marker_html(step_number)
    if href:
        return (
            f'<li class="admin-onboarding-step {state}">'
            f'<a class="admin-onboarding-step-btn" href="{escape(href)}">'
            f'<span class="admin-onboarding-step-marker">{marker}</span>'
            f'<span class="admin-onboarding-step-label">{escape(label)}</span>'
            f"</a></li>"
        )
    return (
        f'<li class="admin-onboarding-step {state}">'
        f'<span class="admin-onboarding-step-marker">{marker}</span>'
        f'<span class="admin-onboarding-step-label">{escape(label)}</span>'
        f"</li>"
    )


def _steps_flow_html(
    current_step: int,
    *,
    url: UrlFn,
    company: str = "",
    environment: str = "",
    client_id: str = "",
) -> str:
    items: list[str] = []
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
        items.append(
            _step_item_html(step_number=step_number, state=state, label=label, href=href)
        )
        if step_number < WIZARD_STEP_COUNT:
            items.append(
                '<li class="admin-onboarding-step-bridge" aria-hidden="true">'
                '<span class="admin-onboarding-step-arrow"></span>'
                "</li>"
            )
    return f'<ol class="admin-onboarding-steps">{"".join(items)}</ol>'


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
            f"<td>{escape(_format_connector_sources(client.get('connector_sources', client.get('connector_source', ''))))}</td>"
            f'<td><a class="btn secondary" href="{detail_url}">Manage</a></td>'
            "</tr>"
        )
    table = (
        '<div class="table-wrap"><table><thead><tr>'
        "<th>Company</th><th>Client</th><th>Env</th><th>Connectors</th><th></th>"
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
    form_values: dict[str, str] | None = None,
    error: str = "",
    company: str = "",
    environment: str = "",
    client_id: str = "",
) -> str:
    values = dict(form_values or {})
    company = company or str(values.get("onboarding_company", "")).strip().upper()
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
          heading="Step 1 of {WIZARD_STEP_COUNT}",
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


def _connector_guide_dialog(source: str) -> str:
    label = _CONNECTOR_LABELS.get(source, source)
    dialog_id = f"connector-guide-{source}"
    guide_html = render_connector_guide_html(source)
    return f"""
      <dialog id="{escape(dialog_id)}" class="admin-connector-guide-dialog" aria-labelledby="{escape(dialog_id)}-title">
        <div class="admin-connector-guide-dialog-head">
          <h3 id="{escape(dialog_id)}-title">{escape(label)} credential setup</h3>
          <form method="dialog">
            <button type="submit" class="btn secondary">Close</button>
          </form>
        </div>
        <div class="admin-connector-guide-dialog-body">{guide_html}</div>
      </dialog>
    """


def _connector_guide_script() -> str:
    return """
<script>
(function () {
  document.addEventListener("click", function (event) {
    var btn = event.target && event.target.closest
      ? event.target.closest("[data-connector-guide]")
      : null;
    if (!btn) return;
    var id = btn.getAttribute("data-connector-guide");
    if (!id) return;
    var dialog = document.getElementById(id);
    if (dialog && typeof dialog.showModal === "function") {
      dialog.showModal();
    }
  });
})();
</script>
"""


def _connector_credentials_section(
    *,
    url: UrlFn,
    company: str,
    environment: str,
    client_id: str,
    source: str,
) -> str:
    secret_form = "".join(
        _form_field(name, label, hint=hint) for name, label, hint in _connector_secret_fields(source)
    )
    qbd_note = ""
    if source == "qbd":
        qwc_url = escape(url(f"/admin/onboarding/{company.lower()}/qwc")) + "?soap_url=SOAP_URL&username=QBWC_USER"
        qbd_note = (
            f'<p class="pack-card-lead">After ingest deploy, download the '
            f'<a href="{qwc_url}">.qwc file</a> for QuickBooks Web Connector.</p>'
        )
    dialog_id = f"connector-guide-{source}"
    label = _CONNECTOR_LABELS.get(source, source)
    return f"""
      <div class="admin-onboarding-connector-credentials">
        <div class="admin-onboarding-connector-credentials-head">
          <h3>{escape(label)}</h3>
          <button type="button" class="btn secondary" data-connector-guide="{escape(dialog_id)}"
                  aria-haspopup="dialog">
            Credential setup guide
          </button>
        </div>
        {_connector_guide_dialog(source)}
        <form method="post" action="{escape(url(f'/admin/onboarding/{company.lower()}/secrets'))}" class="admin-onboarding-form">
          <input type="hidden" name="environment" value="{escape(environment)}" />
          <input type="hidden" name="client_id" value="{escape(client_id)}" />
          <input type="hidden" name="connector_source" value="{escape(source)}" />
          <div class="admin-onboarding-form-grid">
            {secret_form}
          </div>
          <div class="admin-onboarding-actions">
            <button type="submit" class="btn">Save secret</button>
            <button formaction="{escape(url(f'/admin/onboarding/{company.lower()}/validate'))}" formmethod="post" class="btn secondary">Validate connector</button>
          </div>
        </form>
        {qbd_note}
      </div>
    """


def render_client_detail(
    *,
    url: UrlFn,
    username: str,
    company: str,
    client_id: str,
    environment: str,
    connector_sources: list[str] | tuple[str, ...],
    status_payload: dict[str, Any] | None = None,
    flash: str = "",
    build_id: str = "",
) -> str:
    deploy = (status_payload or {}).get("deploy", {})
    verification = (status_payload or {}).get("verification", {})
    stacks = deploy.get("stacks", [])
    sources = [str(item).strip().lower() for item in connector_sources if str(item).strip()]
    if not sources:
        sources = ["dbc"]
    credentials_html = "".join(
        _connector_credentials_section(
            url=url,
            company=company,
            environment=environment,
            client_id=client_id,
            source=source,
        )
        for source in sources
    )
    build_html = f'<p class="pack-card-lead">Build: <code>{escape(build_id)}</code></p>' if build_id else ""
    body = f"""
    <div class="admin-shell">
      {_shell_header(
          url=url,
          username=username,
          eyebrow=f"{company} / {client_id}",
          heading=f"Step 2 of {WIZARD_STEP_COUNT}",
          lead="Deploy stacks, store connector credentials, and verify the client environment.",
      )}
      {_flash(flash)}
      {_steps_flow_html(2, url=url, company=company, environment=environment, client_id=client_id)}
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
        {credentials_html}
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
    {_connector_guide_script()}
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
