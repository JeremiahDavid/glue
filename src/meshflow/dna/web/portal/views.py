"""Protected client portal reporting views."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any, Callable

from werkzeug.wrappers import Request, Response

from meshflow.dna.settings import DnaSettings
from meshflow.dna.store import load_pack_from_settings, read_json_artifact, read_production_output
from meshflow.dna.web.portal.config import ClientPortalConfig
from meshflow.dna.web.theme import (
    TAGLINE,
    badge_row,
    empty_state,
    escape,
    page_header,
    render_portal_page,
)
from meshflow.dna.workflow import load_workflow_state

REVENUE_OUTPUT_ID = "out_fact_revenue_lines"
REVENUE_TABLE_LIMIT = 500
REVENUE_TREND_MONTHS = 12
_MONTH_NAMES = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
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

PORTAL_DATA_MENU = (
    ("/portal", "Summary"),
    ("/portal/executive", "Executive KPIs"),
    ("/portal/revenue", "Order-to-cash detail"),
    ("/portal/revenue-trend", "Revenue trend"),
)

PORTAL_REPORT_PAGES = (
    ("/portal/executive", "Executive KPIs", "Full metric cards with definitions and pack provenance"),
    ("/portal/revenue", "Order-to-cash detail", "Posted invoice lines from certified gold output"),
    ("/portal/revenue-trend", "Revenue trend", "Monthly posted revenue from certified invoice lines"),
)

PORTAL_SUB_PATHS = frozenset(path for path, _title, _subtitle in PORTAL_REPORT_PAGES)

REPORTING_PACK_V1 = {
    "pack_id": "portal_hand_authored_v1",
    "version": "1.0.0",
    "status": "production",
    "description": "Hand-authored portal layout bound to certified gold outputs until Reporting Engine codegen ships.",
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


def _posting_month(posting_date: Any) -> str | None:
    if posting_date is None:
        return None
    text = str(posting_date).strip()
    if len(text) >= 7 and text[4] == "-":
        return text[:7]
    return None


def aggregate_revenue_by_month(
    rows: list[dict[str, Any]],
    *,
    limit: int = REVENUE_TREND_MONTHS,
) -> list[tuple[str, float]]:
    totals: dict[str, float] = defaultdict(float)
    for row in rows:
        month = _posting_month(row.get("postingDate"))
        if month is None:
            continue
        amount = row.get("netAmount")
        if amount is None:
            continue
        try:
            totals[month] += float(amount)
        except (TypeError, ValueError):
            continue

    months = sorted(totals)
    if limit and len(months) > limit:
        months = months[-limit:]
    return [(month, totals[month]) for month in months]


def _format_month_label(month_key: str) -> str:
    year, month = month_key.split("-", 1)
    return f"{_MONTH_NAMES[int(month) - 1]} '{year[2:]}"


def _format_currency_compact(value: float) -> str:
    if abs(value) >= 1_000_000:
        return f"${value / 1_000_000:.1f}M"
    if abs(value) >= 1_000:
        return f"${value / 1_000:.0f}k"
    return f"${value:,.0f}"


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

    width = 800
    height = 320
    margin_left = 64
    margin_right = 24
    margin_top = 24
    margin_bottom = 56
    plot_width = width - margin_left - margin_right
    plot_height = height - margin_top - margin_bottom
    max_amount = max(amount for _month, amount in monthly) or 1.0
    bar_count = len(monthly)
    slot_width = plot_width / bar_count
    bar_width = slot_width * 0.62

    y_ticks = 4
    grid_lines = []
    for index in range(y_ticks + 1):
        y = margin_top + plot_height - (plot_height * index / y_ticks)
        amount = max_amount * index / y_ticks
        grid_lines.append(
            f'<line x1="{margin_left}" y1="{y:.1f}" x2="{width - margin_right}" y2="{y:.1f}" '
            f'stroke="rgba(255,255,255,0.08)" stroke-width="1"/>'
            f'<text x="{margin_left - 8}" y="{y + 4:.1f}" text-anchor="end" fill="#94a3b8" '
            f'font-size="11" font-family="system-ui,sans-serif">{escape(_format_currency_compact(amount))}</text>'
        )

    bars = []
    labels = []
    for index, (month, amount) in enumerate(monthly):
        bar_height = (amount / max_amount) * plot_height if max_amount else 0.0
        x = margin_left + index * slot_width + (slot_width - bar_width) / 2
        y = margin_top + plot_height - bar_height
        label_x = margin_left + index * slot_width + slot_width / 2
        bars.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_width:.1f}" height="{bar_height:.1f}" '
            f'rx="4" fill="url(#revenueTrendBar)" opacity="0.92"/>'
            f'<title>{escape(_format_month_label(month))}: {amount:,.2f}</title>'
        )
        labels.append(
            f'<text x="{label_x:.1f}" y="{height - 18}" text-anchor="middle" fill="#cbd5e1" '
            f'font-size="11" font-family="system-ui,sans-serif">{escape(_format_month_label(month))}</text>'
        )

    return f"""
    <div class="revenue-trend-chart card">
      <svg viewBox="0 0 {width} {height}" role="img" aria-label="Monthly revenue trend">
        <defs>
          <linearGradient id="revenueTrendBar" x1="0" y1="1" x2="0" y2="0">
            <stop offset="0%" stop-color="#079be8"/>
            <stop offset="100%" stop-color="#ffb800"/>
          </linearGradient>
        </defs>
        {"".join(grid_lines)}
        <line x1="{margin_left}" y1="{margin_top + plot_height}" x2="{width - margin_right}" y2="{margin_top + plot_height}"
              stroke="rgba(255,255,255,0.18)" stroke-width="1"/>
        {"".join(bars)}
        {"".join(labels)}
      </svg>
    </div>
    """


def _html_response(
    request: Request,
    *,
    client: ClientPortalConfig,
    title: str,
    active_path: str,
    body: str,
    page_title: str | None = None,
) -> Response:
    url = lambda path: f"{request.script_root}{path if path.startswith('/') else f'/{path}'}"
    return Response(
        render_portal_page(
            title=title,
            active_path=_portal_nav_active_path(active_path),
            body=body,
            page_title=page_title,
            client=client,
            nav_links=PORTAL_NAV,
            data_menu=PORTAL_DATA_MENU,
            url=url,
        ),
        mimetype="text/html",
    )


def render_overview(
    request: Request,
    *,
    settings: DnaSettings,
    client: ClientPortalConfig,
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
    return _html_response(request, client=client, title="Data", active_path="/portal", body=body)


def render_executive(
    request: Request,
    *,
    settings: DnaSettings,
    client: ClientPortalConfig,
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
    )


def render_revenue(
    request: Request,
    *,
    settings: DnaSettings,
    client: ClientPortalConfig,
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
    )


def render_revenue_trend(
    request: Request,
    *,
    settings: DnaSettings,
    client: ClientPortalConfig,
) -> Response:
    rows = read_production_output(settings, REVENUE_OUTPUT_ID)
    monthly = aggregate_revenue_by_month(rows)
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
    )


def render_governance(
    request: Request,
    *,
    settings: DnaSettings,
    client: ClientPortalConfig,
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
    )


# Legacy alias until callers migrate
render_semantics = render_governance
