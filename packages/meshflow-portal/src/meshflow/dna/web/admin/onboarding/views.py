"""HTML views for the platform admin onboarding wizard."""

from __future__ import annotations

from functools import lru_cache
from importlib.resources import files
from html import escape
from typing import Any, Callable

from meshflow.dna.web.admin.views import _ADMIN_NAV, _ADMIN_SHELL_CSS
from meshflow.client_registry import CLIENT_ID_HTML_PATTERN
from meshflow.dna.web.admin.onboarding.guides import render_connector_guide_html, render_credential_summary_fields
from meshflow.dna.web.admin.onboarding.handlers import (
    ONBOARDING_STEP_LABELS,
    WIZARD_STEP_COUNT,
    _CONNECTOR_DEFAULTS,
    ConnectorCredentialSnapshot,
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
        max-height: calc(min(85vh, 48rem) - 7.5rem);
        background: #0c1220;
      }
      .admin-connector-guide-dialog-foot {
        display: flex;
        gap: 0.65rem;
        flex-wrap: wrap;
        align-items: center;
        justify-content: flex-end;
        padding: 0.85rem 1.1rem;
        border-top: 1px solid var(--border);
        background: #0e1626;
      }
      .admin-connector-guide-input {
        display: inline-block;
        width: min(11rem, 36vw);
        max-width: 100%;
        margin-left: 0.35rem;
        padding: 0.12rem 0.4rem;
        border-radius: var(--radius-sm);
        border: 1px solid rgba(56, 189, 248, 0.35);
        background: #060912;
        color: var(--text);
        font: inherit;
        font-size: 0.78rem;
        line-height: 1.35;
        vertical-align: middle;
      }
      .admin-connector-guide-input:focus {
        outline: none;
        border-color: rgba(56, 189, 248, 0.55);
        box-shadow: 0 0 0 2px rgba(56, 189, 248, 0.12);
      }
      .admin-connector-guide-input::placeholder {
        color: var(--text-dim);
        font-size: 0.74rem;
      }
      .admin-dbc-company-picker-row {
        display: flex;
        gap: 0.65rem;
        flex-wrap: wrap;
        align-items: center;
      }
      .admin-dbc-company-picker-row select.admin-onboarding-select {
        flex: 1 1 14rem;
        min-width: 12rem;
      }
      .admin-dbc-company-picker-row [data-dbc-load-companies]:disabled {
        opacity: 0.55;
        cursor: not-allowed;
      }
      .admin-connector-validate-status {
        margin: 0.35rem 0 0;
      }
      .admin-connector-validate-status.is-error {
        color: #fca5a5;
      }
      .admin-connector-validate-status.is-ok {
        color: #6ee7b7;
      }
      [data-connector-validate] {
        display: inline-flex;
        align-items: center;
        gap: 0.4rem;
      }
      [data-connector-validate] .admin-connector-validate-check {
        display: none;
        align-items: center;
        justify-content: center;
        width: 1.15rem;
        height: 1.15rem;
        border-radius: 999px;
        background: #34d399;
        color: #042f2e;
        font-size: 0.78rem;
        font-weight: 800;
        line-height: 1;
        flex-shrink: 0;
      }
      [data-connector-validate].is-validated {
        border-color: rgba(52, 211, 153, 0.55);
        background: rgba(52, 211, 153, 0.12);
        color: #6ee7b7;
      }
      [data-connector-validate].is-validated .admin-connector-validate-check {
        display: inline-flex;
      }
      .admin-dbc-company-status {
        margin: 0.35rem 0 0;
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
      .admin-connector-guide-content li {
        margin-bottom: 0.35rem;
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
      .admin-stack-progress {
        margin-top: 0.45rem;
        height: 0.35rem;
        border-radius: 999px;
        background: rgba(255, 255, 255, 0.08);
        overflow: hidden;
        position: relative;
      }
      .admin-stack-progress-bar {
        height: 100%;
        border-radius: inherit;
        background: rgba(56, 189, 248, 0.72);
        transition: width 0.45s ease;
      }
      .admin-stack-progress.is-complete .admin-stack-progress-bar {
        background: rgba(20, 184, 166, 0.82);
      }
      .admin-stack-progress.is-error .admin-stack-progress-bar {
        background: rgba(239, 68, 68, 0.78);
      }
      .admin-stack-progress.is-indeterminate .admin-stack-progress-bar {
        width: 38% !important;
        animation: admin-stack-progress-slide 1.35s ease-in-out infinite;
      }
      @keyframes admin-stack-progress-slide {
        0% { transform: translateX(-120%); }
        100% { transform: translateX(320%); }
      }
      .admin-stack-deploy-status {
        margin: 0.5rem 0 0;
        font-size: 0.86rem;
        color: var(--text-muted);
      }
      .admin-stack-deploy-status.is-active {
        color: #7dd3fc;
      }
      .admin-onboarding-continue-deploy.is-disabled {
        opacity: 0.55;
        pointer-events: none;
        cursor: not-allowed;
      }
      .admin-onboarding-continue-hint {
        margin: 0.35rem 0 0;
        font-size: 0.86rem;
        color: var(--text-muted);
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
    if not stacks:
        return '<p class="pack-card-lead">No stacks configured.</p>'
    rows = []
    for item in stacks:
        status = str(item.get("status", "unknown"))
        stack_name = escape(str(item.get("stack_name", "")))
        rows.append(
            f'<tr data-stack-row data-stack-name="{stack_name}" data-stack-status="{escape(status)}">'
            f"<td><code>{stack_name}</code></td>"
            f"<td>{_stack_status_cell(status)}</td>"
            f'<td data-stack-reason>{escape(str(item.get("status_reason", "")))}</td>'
            "</tr>"
        )
    return (
        '<div class="table-wrap" data-stack-table><table><thead><tr>'
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
    if step_number == 3 and company and environment and client_id:
        return url(
            f"/admin/onboarding/{company.lower()}/deploy"
            f"?environment={environment}&client_id={client_id}"
        )
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
    validate_url_attr = (
        f' data-connector-validate-url="{escape(url(f"/admin/onboarding/{company.lower()}/validate"))}"'
    )
    companies_url_attr = ""
    if source == "dbc":
        companies_url_attr = (
            f' data-dbc-companies-url="{escape(url(f"/admin/onboarding/{company.lower()}/dbc/companies"))}"'
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
      <div class="admin-onboarding-connector-credentials" id="connector-credentials-{escape(source)}">
        <div class="admin-onboarding-connector-credentials-head">
          <h3>{escape(label)}</h3>
          <button type="button" class="btn secondary" data-connector-guide="{escape(dialog_id)}"
                  aria-haspopup="dialog">
            Credential setup guide
          </button>
        </div>
        {credential_status}
        <form id="{escape(form_id)}" method="post" action="{escape(url(f'/admin/onboarding/{company.lower()}/secrets'))}" class="admin-onboarding-form"{validate_url_attr}{companies_url_attr}>
          <input type="hidden" name="environment" value="{escape(environment)}" />
          <input type="hidden" name="client_id" value="{escape(client_id)}" />
          <input type="hidden" name="connector_source" value="{escape(source)}" />
          {_connector_guide_dialog(source=source)}
          <div class="admin-onboarding-form-grid" data-credential-summary>
            {summary_fields}
          </div>
          <div class="admin-onboarding-actions">
            <button type="submit" class="btn">Save secret</button>
            <button type="button" class="btn secondary" data-connector-validate>
              <span class="admin-connector-validate-check" data-connector-validate-check aria-hidden="true">✓</span>
              <span data-connector-validate-label>Validate connector</span>
            </button>
          </div>
          <p class="pack-card-lead admin-connector-validate-status" data-connector-validate-status hidden></p>
        </form>
        <p class="pack-card-lead">Use the setup guide to paste credentials step by step — values apply to the form when you close the guide.</p>
        {qbd_note}
      </div>
    """


def _job_state_styles() -> str:
    return f"""
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
    """


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
      {_ONBOARDING_STYLES}
      {_job_state_styles()}
    </style>
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
        </div>
        <p class="admin-stack-deploy-status" data-stack-deploy-status hidden></p>
        {build_html}
      </section>
      <section class="card pack-card admin-onboarding-section">
        <h2>Post-deploy verification</h2>
        <div class="admin-preview-panel"><pre>{escape(str(verification))}</pre></div>
      </section>
    </div>
    <style>
      {_ADMIN_SHELL_CSS}
      {_ONBOARDING_STYLES}
      {_job_state_styles()}
    </style>
    {_connector_guide_script()}
    """
    return _onboarding_page(title=f"{company} deploy", url=url, body=body)


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

