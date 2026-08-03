"""Protected client portal reporting views."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

from werkzeug.wrappers import Request, Response

from meshflow.dna.settings import DnaSettings
from meshflow.dna.store import load_pack_from_settings, read_json_artifact, read_production_output
from meshflow.dna.web.portal.config import ClientPortalConfig
from meshflow.dna.web.charts import ChartSeries, ChartSpec, chart_mount_html, charts_page_assets
from meshflow.dna.web.charts.catalog import CHART_TYPE_CATALOG
from meshflow.dna.web.charts.demo import chart_demo_has_charts, chart_demo_section_html
from meshflow.dna.web.charts.gold import (
    REVENUE_OUTPUT_ID,
    aggregate_revenue_by_month,
    format_month_label,
    posting_month,
)
from meshflow.dna.web.theme import (
    TAGLINE,
    badge_row,
    empty_state,
    escape,
    page_header,
    render_portal_page,
)
from meshflow.dna.workflow import load_workflow_state

REVENUE_OUTPUT_ID = REVENUE_OUTPUT_ID
REVENUE_TABLE_LIMIT = 500
REVENUE_TREND_MONTHS = 12
_format_month_label = format_month_label
_posting_month = posting_month
REVENUE_DISPLAY_COLUMNS = (
    ("postingDate", "Posting date", False),
    ("customerNumber", "Customer #", False),
    ("customerName", "Customer", False),
    ("documentId", "Document", False),
    ("sequence", "Line", True),
    ("quantity", "Qty", True),
    ("unitPrice", "Unit price", True),
    ("netAmount", "Amount", True),
)

PORTAL_NAV = (
    ("/portal/governance", "Governance"),
)

PORTAL_ADMIN_NAV = (
    ("/portal/admin/users", "Team"),
)

PORTAL_DATA_MENU = (
    ("/portal", "Summary"),
    ("/portal/executive", "Executive KPIs"),
    ("/portal/revenue", "Order-to-cash detail"),
    ("/portal/revenue-trend", "Revenue trend"),
    ("/portal/chart-demo", "Chart catalog"),
)

PORTAL_REPORT_PAGES = (
    ("/portal/executive", "Executive KPIs", "Full metric cards with definitions and pack provenance"),
    ("/portal/revenue", "Order-to-cash detail", "Posted invoice lines from certified gold output"),
    ("/portal/revenue-trend", "Revenue trend", "Monthly posted revenue from certified invoice lines"),
    ("/portal/chart-demo", "Chart catalog", "Interactive ECharts gallery for all supported reporting chart types"),
)

PORTAL_SUB_PATHS = frozenset(path for path, _title, _subtitle in PORTAL_REPORT_PAGES)

REPORTING_PACK_V1 = {
    "pack_id": "portal_hand_authored_v1",
    "version": "1.0.0",
    "status": "production",
    "description": "Hand-authored portal layout bound to certified gold outputs. Charts rendered via Apache ECharts with the HiveFlowAI theme.",
    "pages": [label for _path, label in PORTAL_DATA_MENU],
}


def _format_published_date(published_at: Any) -> str:
    text = str(published_at).strip()
    if not text:
        return text
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).strftime("%b %d, %Y")
    except ValueError:
        return text[:10] if len(text) >= 10 else text


def _portal_nav_links(*, is_admin: bool) -> tuple[tuple[str, str], ...]:
    if is_admin:
        return PORTAL_NAV + PORTAL_ADMIN_NAV
    return PORTAL_NAV


def _portal_nav_active_path(active_path: str) -> str:
    if active_path == "/portal/semantics":
        return "/portal/governance"
    return active_path


def _report_page_links_html(url: Callable[[str], str]) -> str:
    links = []
    for path, title, subtitle in PORTAL_REPORT_PAGES:
        links.append(
            f"""
          <a class="quick-link" href="{escape(url(path))}">
            <div><strong>{escape(title)}</strong><br><span>{escape(subtitle)}</span></div>
            <span class="arrow">→</span>
          </a>"""
        )
    return f'<div class="quick-links">{"".join(links)}</div>'


def _format_cell(value: Any, *, numeric: bool = False) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:,.2f}"
    if numeric and isinstance(value, (int, float)):
        return f"{value:,.2f}"
    return str(value)


def _kpi_cards_html(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return empty_state(
            "No metrics published yet",
            "Run DNA publish after silver consolidate to populate certified KPI snapshots.",
        )

    cards = []
    for row in rows:
        value = row.get("value", 0)
        unit = row.get("unit", "")
        unit_html = f'<span class="unit">{escape(unit)}</span>' if unit else ""
        cards.append(
            f"""
            <article class="card kpi-card">
              <div class="kpi-label">{escape(row.get("kpi_name", row.get("kpi_id")))}</div>
              <div class="kpi-value">{value:,.2f}{unit_html}</div>
              <div class="kpi-meta">{escape(row.get("definition", ""))}</div>
              <div class="kpi-id">{escape(row.get("kpi_id"))} · pack {escape(row.get("pack_id"))} v{escape(row.get("pack_version"))}</div>
            </article>
            """
        )
    return f'<div class="grid">{"".join(cards)}</div>'


def _revenue_rows(settings: DnaSettings) -> list[dict[str, Any]]:
    rows = read_production_output(settings, REVENUE_OUTPUT_ID)
    rows.sort(key=lambda row: str(row.get("postingDate", "")), reverse=True)
    return rows[:REVENUE_TABLE_LIMIT]


def _revenue_table_html(rows: list[dict[str, Any]], *, truncated: bool) -> str:
    if not rows:
        return empty_state(
            "No revenue lines yet",
            "Published invoice line detail appears here after DNA publish completes.",
        )

    headers = "".join(
        f'<th class="{"num" if numeric else ""}">{escape(label)}</th>'
        for _key, label, numeric in REVENUE_DISPLAY_COLUMNS
    )
    body_rows = ""
    for row in rows:
        cells = "".join(
            f'<td class="{"num" if numeric else ""}">{escape(_format_cell(row.get(key), numeric=numeric))}</td>'
            for key, _label, numeric in REVENUE_DISPLAY_COLUMNS
        )
        body_rows += f"<tr>{cells}</tr>"

    note = ""
    if truncated:
        note = f'<p class="section-title" style="margin-top:0">Latest {REVENUE_TABLE_LIMIT} lines by posting date</p>'

    return f"""
    {note}
    <div class="table-wrap">
      <table>
        <thead><tr>{headers}</tr></thead>
        <tbody>{body_rows}</tbody>
      </table>
    </div>
    """




def _revenue_trend_summary_html(monthly: list[tuple[str, float]]) -> str:
    total = sum(amount for _month, amount in monthly)
    average = total / len(monthly) if monthly else 0.0
    peak_month, peak_amount = max(monthly, key=lambda item: item[1]) if monthly else ("—", 0.0)
    peak_label = _format_month_label(peak_month) if monthly else "—"

    cards = [
        ("Period total", f"{total:,.2f}", "Sum of posted net amounts"),
        ("Monthly average", f"{average:,.2f}", f"Across {len(monthly)} month{'s' if len(monthly) != 1 else ''}"),
        ("Peak month", f"{peak_amount:,.2f}", peak_label),
    ]
    body = ""
    for label, value, meta in cards:
        body += f"""
        <article class="card kpi-card revenue-trend-stat">
          <div class="kpi-label">{escape(label)}</div>
          <div class="kpi-value">{value}</div>
          <div class="kpi-meta">{escape(meta)}</div>
        </article>
        """
    return f'<div class="grid revenue-trend-summary">{body}</div>'


def _revenue_trend_chart_html(monthly: list[tuple[str, float]]) -> str:
    if not monthly:
        return empty_state(
            "No revenue trend yet",
            "Posted invoice lines with posting dates appear here after DNA publish completes.",
        )

    spec = ChartSpec(
        chart_type="bar",
        title="Monthly posted revenue",
        aria_label="Monthly revenue trend",
        value_format="compact_currency",
        height=320,
        categories=[_format_month_label(month) for month, _amount in monthly],
        series=[
            ChartSeries(
                name="Posted revenue",
                values=[amount for _month, amount in monthly],
            )
        ],
    )
    return chart_mount_html(spec, css_class="hive-chart card revenue-trend-chart")


def _html_response(
    request: Request,
    *,
    client: ClientPortalConfig,
    title: str,
    active_path: str,
    body: str,
    page_title: str | None = None,
    use_charts: bool = False,
    is_admin: bool = False,
) -> Response:
    url = lambda path: f"{request.script_root}{path if path.startswith('/') else f'/{path}'}"
    charts_assets = charts_page_assets(url) if use_charts else ""
    return Response(
        render_portal_page(
            title=title,
            active_path=_portal_nav_active_path(active_path),
            body=body,
            page_title=page_title,
            client=client,
            nav_links=_portal_nav_links(is_admin=is_admin),
            data_menu=PORTAL_DATA_MENU,
            url=url,
            charts_assets=charts_assets,
        ),
        mimetype="text/html",
    )


def render_overview(
    request: Request,
    *,
    settings: DnaSettings,
    client: ClientPortalConfig,
    is_admin: bool = False,
) -> Response:
    workflow = load_workflow_state(settings, settings.pack_id)
    kpi_rows = read_production_output(settings, "out_kpi_snapshot")
    manifest = read_json_artifact(settings, f"{settings.gold_dna_prefix}/manifest.json") or {}
    url: Callable[[str], str] = lambda path: f"{request.script_root}{path if path.startswith('/') else f'/{path}'}"

    badges: list[tuple[str, bool]] = [(f"Pack {settings.pack_id}", False)]
    active = workflow.get("active_version")
    if active:
        badges.append((f"v{active} production", True))
    if manifest.get("published_at"):
        badges.append((f"Updated {_format_published_date(manifest.get('published_at'))}", False))

    body = page_header(client.welcome_title, client.welcome_message, eyebrow=TAGLINE)
    body += badge_row(*badges)
    body += '<section class="section" style="margin-top:1.75rem"><div class="section-title">Executive snapshot</div>'
    body += _kpi_cards_html(kpi_rows)
    body += "</section>"
    body += f"""
    <section class="section">
      <div class="section-title">Reports</div>
      <div class="card">
        {_report_page_links_html(url)}
      </div>
    </section>
    """
    return _html_response(request, client=client, title="Data", active_path="/portal", body=body, is_admin=is_admin)


def render_executive(
    request: Request,
    *,
    settings: DnaSettings,
    client: ClientPortalConfig,
    is_admin: bool = False,
) -> Response:
    rows = read_production_output(settings, "out_kpi_snapshot")
    body = page_header(
        "Executive KPIs",
        "Key performance indicators compiled from your DNA definition pack and published to gold.",
        eyebrow="Metrics",
    )
    body += _kpi_cards_html(rows)
    return _html_response(
        request,
        client=client,
        title="Executive",
        active_path="/portal/executive",
        body=body,
        is_admin=is_admin,
    )


def render_revenue(
    request: Request,
    *,
    settings: DnaSettings,
    client: ClientPortalConfig,
    is_admin: bool = False,
) -> Response:
    all_rows = read_production_output(settings, REVENUE_OUTPUT_ID)
    rows = _revenue_rows(settings)
    body = page_header(
        "Order-to-cash detail",
        f"Posted sales invoice lines from certified output {REVENUE_OUTPUT_ID}.",
        eyebrow="Revenue",
    )
    body += f'<section class="section">{_revenue_table_html(rows, truncated=len(all_rows) > len(rows))}</section>'
    return _html_response(
        request,
        client=client,
        title="Revenue",
        active_path="/portal/revenue",
        body=body,
        is_admin=is_admin,
    )


def render_revenue_trend(
    request: Request,
    *,
    settings: DnaSettings,
    client: ClientPortalConfig,
    is_admin: bool = False,
) -> Response:
    rows = read_production_output(settings, REVENUE_OUTPUT_ID)
    monthly = aggregate_revenue_by_month(rows, limit=REVENUE_TREND_MONTHS)
    month_keys = {_posting_month(row.get("postingDate")) for row in rows}
    month_keys.discard(None)
    window_note = ""
    if len(month_keys) > REVENUE_TREND_MONTHS:
        window_note = f" Showing the latest {REVENUE_TREND_MONTHS} months with posted revenue."

    body = page_header(
        "Revenue trend",
        f"Monthly sum of posted net amounts from {REVENUE_OUTPUT_ID}.{window_note}",
        eyebrow="Revenue",
    )
    body += f'<section class="section">{_revenue_trend_summary_html(monthly)}</section>'
    body += f'<section class="section">{_revenue_trend_chart_html(monthly)}</section>'
    return _html_response(
        request,
        client=client,
        title="Revenue trend",
        active_path="/portal/revenue-trend",
        body=body,
        use_charts=bool(monthly),
        is_admin=is_admin,
    )


def render_chart_demo(
    request: Request,
    *,
    settings: DnaSettings,
    client: ClientPortalConfig,
    is_admin: bool = False,
) -> Response:
    body = page_header(
        "Chart catalog",
        f"Interactive gallery of reporting chart types sourced from certified gold outputs ({REVENUE_OUTPUT_ID}, out_dim_items).",
        eyebrow="ECharts",
    )
    body += badge_row((f"{len(CHART_TYPE_CATALOG)} chart types", True), ("Gold-backed demo", False))
    body += f"""
    <section class="section">
      <div class="section-title">Catalog</div>
      {chart_demo_section_html(settings)}
    </section>
    """
    return _html_response(
        request,
        client=client,
        title="Chart catalog",
        active_path="/portal/chart-demo",
        body=body,
        use_charts=chart_demo_has_charts(settings),
        is_admin=is_admin,
    )


def render_governance(
    request: Request,
    *,
    settings: DnaSettings,
    client: ClientPortalConfig,
    is_admin: bool = False,
) -> Response:
    pack = load_pack_from_settings(settings)
    workflow = load_workflow_state(settings, settings.pack_id)
    manifest = read_json_artifact(settings, f"{settings.gold_dna_prefix}/manifest.json") or {}
    active_version = workflow.get("active_version") or pack.version
    history = workflow.get("history", [])
    if not isinstance(history, list):
        history = []

    history_rows = ""
    for entry in reversed(history):
        if not isinstance(entry, dict):
            continue
        history_rows += (
            f"<tr><td>v{escape(entry.get('version', '—'))}</td>"
            f"<td>{escape(str(entry.get('status', '—')))}</td>"
            f"<td>{escape(entry.get('approver') or '—')}</td>"
            f"<td>{escape(_format_published_date(entry.get('at')) if entry.get('at') else '—')}</td>"
            f"<td>{escape(entry.get('notes') or '—')}</td></tr>"
        )

    reporting = REPORTING_PACK_V1
    reporting_pages = "".join(f"<li>{escape(page)}</li>" for page in reporting["pages"])
    manifest_outputs = manifest.get("outputs", [])
    output_count = len(manifest_outputs) if isinstance(manifest_outputs, list) else 0
    published_at = _format_published_date(manifest.get("published_at")) if manifest.get("published_at") else "—"

    body = page_header(
        "Governance",
        "Version-controlled DNA and reporting packs — what powers this portal and when it last refreshed.",
        eyebrow="Pack registry",
    )
    body += badge_row((f"DNA v{active_version} production", True), (f"Reporting v{reporting['version']}", False))
    body += f"""
    <section class="section">
      <div class="section-title">DNA definition pack</div>
      <div class="card pack-card">
        <p class="pack-card-lead">{escape(pack.description)}</p>
        <dl class="pack-meta">
          <div><dt>Pack</dt><dd><code>{escape(pack.pack_id)}</code></dd></div>
          <div><dt>Version</dt><dd>v{escape(pack.version)}</dd></div>
          <div><dt>Status</dt><dd>{escape(pack.approval.status)}</dd></div>
          <div><dt>Production pin</dt><dd>v{escape(str(active_version))}</dd></div>
          <div><dt>Approver</dt><dd>{escape(pack.approval.approver or "—")}</dd></div>
          <div><dt>Approved</dt><dd>{escape(pack.approval.approved_at or "—")}</dd></div>
          <div><dt>Gold refresh</dt><dd>{escape(published_at)}</dd></div>
          <div><dt>Published outputs</dt><dd>{output_count}</dd></div>
        </dl>
      </div>
    </section>
    <section class="section">
      <div class="section-title">DNA version history</div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Version</th><th>Status</th><th>Approver</th><th>Date</th><th>Notes</th></tr></thead>
          <tbody>{history_rows or "<tr><td colspan='5'>No promotion history recorded yet</td></tr>"}</tbody>
        </table>
      </div>
    </section>
    <section class="section">
      <div class="section-title">Reporting layout pack</div>
      <div class="card pack-card">
        <p class="pack-card-lead">{escape(reporting["description"])}</p>
        <dl class="pack-meta">
          <div><dt>Pack</dt><dd><code>{escape(reporting["pack_id"])}</code></dd></div>
          <div><dt>Version</dt><dd>v{escape(reporting["version"])}</dd></div>
          <div><dt>Status</dt><dd>{escape(reporting["status"])}</dd></div>
          <div><dt>Delivery</dt><dd>Hand-authored portal pages (Reporting Engine TBD)</dd></div>
        </dl>
        <div class="section-title" style="margin-top:1rem;margin-bottom:0.5rem">Included pages</div>
        <ul class="plain">{reporting_pages}</ul>
      </div>
    </section>
    """
    if pack.limitations:
        limitations = "".join(f"<li>{escape(item)}</li>" for item in pack.limitations)
        body += f"""
    <section class="section">
      <div class="section-title">Known DNA limitations</div>
      <div class="card"><ul class="plain">{limitations}</ul></div>
    </section>
    """
    return _html_response(
        request,
        client=client,
        title="Governance",
        active_path="/portal/governance",
        body=body,
        is_admin=is_admin,
    )


def _user_status_label(status: str) -> str:
    labels = {
        "CONFIRMED": "Active",
        "FORCE_CHANGE_PASSWORD": "Invite pending",
        "RESET_REQUIRED": "Password reset",
        "UNCONFIRMED": "Unconfirmed",
    }
    return labels.get(status, status.replace("_", " ").title())


def _legacy_portal_users(client_id: str, *, company: str, environment: str) -> list[Any]:
    from meshflow.dna.web.portal.auth import load_portal_users
    from meshflow.dna.web.portal.cognito import PORTAL_ROLE_ADMIN, PortalUserRecord

    normalized = client_id.strip().lower()
    records: list[PortalUserRecord] = []
    for user in load_portal_users(company=company, environment=environment).values():
        if user.client_id != normalized:
            continue
        records.append(
            PortalUserRecord(
                username=user.username,
                email="",
                client_id=user.client_id,
                role=PORTAL_ROLE_ADMIN,
                status="CONFIRMED",
                enabled=True,
            )
        )
    records.sort(key=lambda item: item.username)
    return records


def render_admin_users(
    request: Request,
    *,
    client: ClientPortalConfig,
    users: list[Any],
    current_username: str,
    message: str = "",
    error: str = "",
    invites_enabled: bool = True,
    is_admin: bool = True,
) -> Response:
    url: Callable[[str], str] = lambda path: f"{request.script_root}{path if path.startswith('/') else f'/{path}'}"
    seat_count = len(users)
    seats_remaining = max(client.max_users - seat_count, 0)
    at_capacity = seat_count >= client.max_users

    message_html = f'<div class="form-success">{escape(message)}</div>' if message else ""
    error_html = f'<div class="form-error">{escape(error)}</div>' if error else ""

    user_rows = ""
    for user in users:
        you_marker = " (you)" if user.username == current_username.strip().lower() else ""
        enabled_label = "Active" if user.enabled else "Disabled"
        if user.status == "FORCE_CHANGE_PASSWORD":
            enabled_label = "Invite pending"
        user_rows += (
            f"<tr>"
            f"<td>{escape(user.username)}{escape(you_marker)}</td>"
            f"<td>{escape(user.email or '—')}</td>"
            f"<td>{escape(user.role.title())}</td>"
            f"<td>{escape(_user_status_label(user.status))}</td>"
            f"<td>{escape(enabled_label)}</td>"
            f"</tr>"
        )

    invite_disabled = at_capacity or not invites_enabled
    invite_note = ""
    if not invites_enabled:
        invite_note = (
            '<p class="hero-subtitle" style="margin-top:0">Team invites require Cognito in deployed environments.</p>'
        )
    elif at_capacity:
        invite_note = (
            f'<p class="hero-subtitle" style="margin-top:0">All {client.max_users} seats are in use. '
            "Remove a user or contact HiveFlowAI to increase your limit.</p>"
        )

    invite_fields = ""
    if invite_disabled:
        invite_fields = (
            f'<div class="form-field"><label>Username</label><input disabled placeholder="At seat limit" /></div>'
            f'<div class="form-field"><label>Email</label><input disabled placeholder="At seat limit" /></div>'
            f'<button class="button primary" type="submit" disabled>Send invite</button>'
        )
    else:
        invite_fields = """
          <div class="form-field">
            <label for="invite_username">Username</label>
            <input id="invite_username" name="username" autocomplete="off" required />
          </div>
          <div class="form-field">
            <label for="invite_email">Email</label>
            <input id="invite_email" name="email" type="email" autocomplete="off" required />
          </div>
          <button class="button primary" type="submit">Send invite</button>
        """

    body = page_header(
        "Team members",
        "Invite colleagues to your portal. Invited users receive an email with a temporary password.",
        eyebrow="Administration",
    )
    body += badge_row(
        (f"{seat_count} of {client.max_users} seats used", at_capacity),
        (f"{seats_remaining} remaining", not at_capacity),
    )
    body += message_html
    body += error_html
    body += f"""
    <section class="section">
      <div class="section-title">Current users</div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr><th>Username</th><th>Email</th><th>Role</th><th>Status</th><th>Access</th></tr>
          </thead>
          <tbody>{user_rows or "<tr><td colspan='5'>No users found for this client.</td></tr>"}</tbody>
        </table>
      </div>
    </section>
    <section class="section">
      <div class="section-title">Invite user</div>
      <div class="card login-card" style="max-width:none">
        {invite_note}
        <form method="post" action="{escape(url("/portal/admin/users"))}">
          <input type="hidden" name="action" value="invite" />
          {invite_fields}
        </form>
      </div>
    </section>
    """
    return _html_response(
        request,
        client=client,
        title="Team",
        active_path="/portal/admin/users",
        body=body,
        is_admin=is_admin,
    )


# Legacy alias until callers migrate
render_semantics = render_governance
