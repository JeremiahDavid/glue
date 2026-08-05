"""Protected client portal reporting views."""

from __future__ import annotations

from datetime import UTC, datetime
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
from meshflow.dna.web.portal.reporting_layout import (
    page_source_output,
    reporting_data_menu,
    reporting_quick_links,
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

# In-page sub-nav under Governance (always visible; pages enforce admin auth).
GOVERNANCE_SECTION_NAV = (
    ("/portal/governance", "Pack Registry"),
    ("/portal/governance/users", "Users"),
    ("/portal/governance/config", "Config Portal"),
)

# Legacy fallbacks when reporting config cannot be loaded (tests / empty seed).
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

def _format_published_date(published_at: Any) -> str:
    text = str(published_at).strip()
    if not text:
        return text
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).strftime("%b %d, %Y")
    except ValueError:
        return text[:10] if len(text) >= 10 else text


def _portal_nav_links(*, is_admin: bool = False) -> tuple[tuple[str, str], ...]:
    del is_admin  # top nav is the same; admin tools live under Governance sub-nav
    return PORTAL_NAV


def _portal_nav_active_path(active_path: str) -> str:
    if active_path == "/portal/semantics":
        return "/portal/governance"
    if active_path.startswith("/portal/governance") or active_path.startswith(
        "/portal/admin/"
    ):
        return "/portal/governance"
    return active_path


def _governance_section_nav_html(
    url: Callable[[str], str],
    *,
    active_path: str,
    is_admin: bool = False,
) -> str:
    """Always show Pack Registry / Users / Config Portal (admin pages enforce auth)."""
    del is_admin
    items = []
    for href, label in GOVERNANCE_SECTION_NAV:
        active = href == active_path or (
            href != "/portal/governance" and active_path.startswith(href)
        )
        cls = "nav-link active" if active else "nav-link"
        aria = ' aria-current="page"' if active else ""
        items.append(
            f'<a class="{cls}" href="{escape(url(href))}"{aria}>{escape(label)}</a>'
        )
    return (
        '<nav class="governance-subnav" aria-label="Governance section" '
        'style="display:flex;gap:0.75rem;flex-wrap:wrap;'
        'margin:0 0 1.25rem;padding:0.5rem 0;border-bottom:1px solid var(--border)">'
        + "".join(items)
        + "</nav>"
    )


def _preview_banner_html(
    url: Callable[[str], str],
    *,
    next_version: str,
    proposal_id: str,
) -> str:
    return f"""
    <div class="form-success" style="margin-bottom:1rem">
      Previewing proposed config <strong>v{escape(next_version)}</strong>
      (proposal <code>{escape(proposal_id)}</code>) — not live.
      <a href="{escape(url('/portal/governance/config'))}">Back to Config Portal</a>
      ·
      <a href="{escape(url('/portal/governance/config/preview/exit'))}">Exit preview</a>
    </div>
    """


def _report_page_links_html(
    url: Callable[[str], str],
    *,
    settings: DnaSettings | None = None,
    reporting_override: dict[str, Any] | None = None,
) -> str:
    if settings is not None:
        pages = reporting_quick_links(settings, override=reporting_override)
    else:
        pages = PORTAL_REPORT_PAGES
    links = []
    for path, title, subtitle in pages:
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


def _revenue_rows(
    settings: DnaSettings,
    *,
    output_id: str = REVENUE_OUTPUT_ID,
) -> list[dict[str, Any]]:
    rows = read_production_output(settings, output_id)
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
    settings: DnaSettings | None = None,
    reporting_override: dict[str, Any] | None = None,
    preview_meta: dict[str, Any] | None = None,
) -> Response:
    url = lambda path: f"{request.script_root}{path if path.startswith('/') else f'/{path}'}"
    charts_assets = charts_page_assets(url) if use_charts else ""
    data_menu = (
        reporting_data_menu(settings, override=reporting_override)
        if settings is not None
        else PORTAL_DATA_MENU
    )
    if not data_menu:
        data_menu = PORTAL_DATA_MENU
    if preview_meta:
        body = (
            _preview_banner_html(
                url,
                next_version=str(preview_meta.get("next_version") or ""),
                proposal_id=str(preview_meta.get("proposal_id") or ""),
            )
            + body
        )
    return Response(
        render_portal_page(
            title=title,
            active_path=_portal_nav_active_path(active_path),
            body=body,
            page_title=page_title,
            client=client,
            nav_links=_portal_nav_links(is_admin=is_admin),
            data_menu=data_menu,
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
    page: dict[str, Any] | None = None,
    reporting_override: dict[str, Any] | None = None,
    preview_meta: dict[str, Any] | None = None,
) -> Response:
    workflow = load_workflow_state(settings, settings.dna_config_id)
    kpi_rows = read_production_output(settings, "out_kpi_snapshot")
    manifest = read_json_artifact(settings, f"{settings.gold_dna_prefix}/manifest.json") or {}
    url: Callable[[str], str] = lambda path: f"{request.script_root}{path if path.startswith('/') else f'/{path}'}"
    active_path = str((page or {}).get("path") or "/portal")
    title = str((page or {}).get("title") or "Data")

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
        {_report_page_links_html(url, settings=settings, reporting_override=reporting_override)}
      </div>
    </section>
    """
    return _html_response(
        request,
        client=client,
        title=title,
        active_path=active_path,
        body=body,
        is_admin=is_admin,
        settings=settings,
        reporting_override=reporting_override,
        preview_meta=preview_meta,
    )


def render_executive(
    request: Request,
    *,
    settings: DnaSettings,
    client: ClientPortalConfig,
    is_admin: bool = False,
    page: dict[str, Any] | None = None,
    reporting_override: dict[str, Any] | None = None,
    preview_meta: dict[str, Any] | None = None,
) -> Response:
    title = str((page or {}).get("title") or "Executive KPIs")
    description = str(
        (page or {}).get("description")
        or "Key performance indicators compiled from your DNA definition pack and published to gold."
    )
    active_path = str((page or {}).get("path") or "/portal/executive")
    rows = read_production_output(settings, "out_kpi_snapshot")
    body = page_header(title, description, eyebrow="Metrics")
    body += _kpi_cards_html(rows)
    return _html_response(
        request,
        client=client,
        title=title,
        active_path=active_path,
        body=body,
        is_admin=is_admin,
        settings=settings,
        reporting_override=reporting_override,
        preview_meta=preview_meta,
    )


def render_revenue(
    request: Request,
    *,
    settings: DnaSettings,
    client: ClientPortalConfig,
    is_admin: bool = False,
    page: dict[str, Any] | None = None,
    reporting_override: dict[str, Any] | None = None,
    preview_meta: dict[str, Any] | None = None,
) -> Response:
    output_id = page_source_output(page, kind="table", default=REVENUE_OUTPUT_ID)
    title = str((page or {}).get("title") or "Order-to-cash detail")
    description = str(
        (page or {}).get("description")
        or f"Posted sales invoice lines from certified output {output_id}."
    )
    active_path = str((page or {}).get("path") or "/portal/revenue")
    all_rows = read_production_output(settings, output_id)
    rows = _revenue_rows(settings, output_id=output_id)
    body = page_header(title, description, eyebrow="Revenue")
    body += f'<section class="section">{_revenue_table_html(rows, truncated=len(all_rows) > len(rows))}</section>'
    return _html_response(
        request,
        client=client,
        title=title,
        active_path=active_path,
        body=body,
        is_admin=is_admin,
        settings=settings,
        reporting_override=reporting_override,
        preview_meta=preview_meta,
    )


def render_revenue_trend(
    request: Request,
    *,
    settings: DnaSettings,
    client: ClientPortalConfig,
    is_admin: bool = False,
    page: dict[str, Any] | None = None,
    reporting_override: dict[str, Any] | None = None,
    preview_meta: dict[str, Any] | None = None,
) -> Response:
    output_id = page_source_output(page, kind="chart", default=REVENUE_OUTPUT_ID)
    title = str((page or {}).get("title") or "Revenue trend")
    active_path = str((page or {}).get("path") or "/portal/revenue-trend")
    rows = read_production_output(settings, output_id)
    monthly = aggregate_revenue_by_month(rows, limit=REVENUE_TREND_MONTHS)
    month_keys = {_posting_month(row.get("postingDate")) for row in rows}
    month_keys.discard(None)
    window_note = ""
    if len(month_keys) > REVENUE_TREND_MONTHS:
        window_note = f" Showing the latest {REVENUE_TREND_MONTHS} months with posted revenue."
    description = str(
        (page or {}).get("description")
        or f"Monthly sum of posted net amounts from {output_id}.{window_note}"
    )

    body = page_header(title, description, eyebrow="Revenue")
    body += f'<section class="section">{_revenue_trend_summary_html(monthly)}</section>'
    body += f'<section class="section">{_revenue_trend_chart_html(monthly)}</section>'
    return _html_response(
        request,
        client=client,
        title=title,
        active_path=active_path,
        body=body,
        use_charts=bool(monthly),
        is_admin=is_admin,
        settings=settings,
        reporting_override=reporting_override,
        preview_meta=preview_meta,
    )


def render_chart_demo(
    request: Request,
    *,
    settings: DnaSettings,
    client: ClientPortalConfig,
    is_admin: bool = False,
    page: dict[str, Any] | None = None,
    reporting_override: dict[str, Any] | None = None,
    preview_meta: dict[str, Any] | None = None,
) -> Response:
    title = str((page or {}).get("title") or "Chart catalog")
    description = str(
        (page or {}).get("description")
        or f"Interactive gallery of reporting chart types sourced from certified gold outputs ({REVENUE_OUTPUT_ID}, out_dim_items)."
    )
    active_path = str((page or {}).get("path") or "/portal/chart-demo")
    body = page_header(title, description, eyebrow="ECharts")
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
        title=title,
        active_path=active_path,
        body=body,
        use_charts=chart_demo_has_charts(settings),
        is_admin=is_admin,
        settings=settings,
        reporting_override=reporting_override,
        preview_meta=preview_meta,
    )


def render_configured_page(
    request: Request,
    *,
    settings: DnaSettings,
    client: ClientPortalConfig,
    page: dict[str, Any],
    is_admin: bool = False,
    reporting_override: dict[str, Any] | None = None,
    preview_meta: dict[str, Any] | None = None,
) -> Response:
    """Dispatch a reporting-config page to the matching renderer."""
    page_id = str(page.get("id") or "")
    path = str(page.get("path") or "")
    tables = page.get("tables") if isinstance(page.get("tables"), list) else []
    charts = page.get("charts") if isinstance(page.get("charts"), list) else []
    common = dict(
        settings=settings,
        client=client,
        is_admin=is_admin,
        page=page,
        reporting_override=reporting_override,
        preview_meta=preview_meta,
    )

    if page_id == "page_summary" or path in {"/portal", "/portal/"}:
        return render_overview(request, **common)
    if page_id == "page_executive" or (not tables and not charts and "executive" in path):
        return render_executive(request, **common)
    if page_id == "page_chart_demo" or path.endswith("/chart-demo"):
        return render_chart_demo(request, **common)
    if charts and not tables:
        return render_revenue_trend(request, **common)
    if tables:
        return render_revenue(request, **common)
    # Unknown page shape — still show title/description from config.
    title = str(page.get("title") or "Report")
    description = str(page.get("description") or "Configured in the company reporting pack.")
    body = page_header(title, description, eyebrow="Report")
    body += empty_state(
        "No charts or tables configured",
        "Add charts or tables with source_output bindings in the reporting config.",
    )
    return _html_response(
        request,
        client=client,
        title=title,
        active_path=path or "/portal",
        body=body,
        is_admin=is_admin,
        settings=settings,
        reporting_override=reporting_override,
        preview_meta=preview_meta,
    )


def _pack_to_yaml(payload: dict[str, Any]) -> str:
    import yaml

    return yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)


def save_governance_packs_from_portal(
    settings: DnaSettings,
    *,
    dna_yaml: str,
    reporting_yaml: str,
    version: str,
    pin_production: bool,
    approver: str,
) -> dict[str, Any]:
    """Parse portal YAML editors and persist a governance version."""
    from meshflow.dna.governance import save_governance_version
    from meshflow.dna.schema import load_definition_pack_yaml
    from meshflow.dna.web.reporting import load_reporting_pack_yaml, normalize_reporting_identity
    from meshflow.dna.workflow import load_workflow_state, save_workflow_state

    pack = load_definition_pack_yaml(dna_yaml)
    pack.pack_id = settings.dna_config_id
    pack.version = version.strip() or pack.version
    reporting = load_reporting_pack_yaml(reporting_yaml)

    if pin_production:
        pack.status = "production"
        pack.approval.status = "production"
        pack.approval.approver = approver or pack.approval.approver or "Portal admin"
        pack.approval.approved_at = datetime.now(UTC).date().isoformat()
        reporting_status = "production"
    else:
        pack.status = "draft"
        pack.approval.status = "draft"
        reporting_status = "draft"

    reporting = normalize_reporting_identity(
        settings,
        reporting,
        version=pack.version,
        status=reporting_status,
    )

    saved = save_governance_version(settings, pack=pack, reporting=reporting)
    state = load_workflow_state(settings, settings.dna_config_id)
    state["pack_id"] = settings.dna_config_id
    history = state.get("history", [])
    if not isinstance(history, list):
        history = []
    history.append(
        {
            "version": pack.version,
            "status": pack.approval.status,
            "approver": approver or "Portal admin",
            "at": datetime.now(UTC).isoformat(),
            "notes": "Updated via client portal",
        }
    )
    state["history"] = history
    if pin_production:
        state["active_version"] = pack.version
    save_workflow_state(settings, state)
    return {
        "status": "saved",
        "version": pack.version,
        "approval_status": pack.approval.status,
        **{k: saved[k] for k in ("dna_path", "reporting_path", "manifest_path") if k in saved},
    }


def render_governance(
    request: Request,
    *,
    settings: DnaSettings,
    client: ClientPortalConfig,
    is_admin: bool = False,
    message: str = "",
    error: str = "",
    dna_yaml_override: str | None = None,
    reporting_yaml_override: str | None = None,
) -> Response:
    from meshflow.dna.web.reporting import (
        default_reporting_pack,
        load_production_reporting,
    )
    from meshflow.dna.workflow import load_production_pack

    try:
        pack = load_production_pack(settings)
    except Exception:  # noqa: BLE001
        pack = load_pack_from_settings(settings)

    workflow = load_workflow_state(settings, settings.dna_config_id)
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

    try:
        reporting = load_production_reporting(settings)
    except FileNotFoundError:
        reporting = default_reporting_pack(
            pack_id=settings.reporting_config_id,
            version=str(active_version),
            status="draft",
            description="Reporting config not seeded yet.",
        )
    reporting_pages = "".join(
        f"<li>{escape(str(page.get('title') or page.get('id') or page))}</li>"
        for page in reporting.get("pages", [])
        if isinstance(page, dict) or isinstance(page, str)
    )
    manifest_outputs = manifest.get("outputs", [])
    output_count = len(manifest_outputs) if isinstance(manifest_outputs, list) else 0
    published_at = _format_published_date(manifest.get("published_at")) if manifest.get("published_at") else "—"

    dna_yaml = dna_yaml_override if dna_yaml_override is not None else _pack_to_yaml(pack.to_dict())
    reporting_yaml = (
        reporting_yaml_override
        if reporting_yaml_override is not None
        else _pack_to_yaml(reporting)
    )

    url: Callable[[str], str] = lambda path: f"{request.script_root}{path if path.startswith('/') else f'/{path}'}"
    body = _governance_section_nav_html(url, active_path="/portal/governance", is_admin=is_admin)
    body += page_header(
        "Pack Registry",
        "Version-controlled DNA and reporting packs — view and update the contracts that power this portal.",
        eyebrow="Governance",
    )
    if message:
        body += f'<div class="form-success">{escape(message)}</div>'
    if error:
        body += f'<div class="form-error">{escape(error)}</div>'
    body += badge_row(
        (f"DNA v{active_version}", True),
        (f"Reporting v{reporting.get('version', '—')}", False),
    )
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
      <div class="section-title">Version history</div>
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
        <p class="pack-card-lead">{escape(str(reporting.get("description") or ""))}</p>
        <dl class="pack-meta">
          <div><dt>Pack</dt><dd><code>{escape(str(reporting.get("pack_id") or settings.reporting_config_id))}</code></dd></div>
          <div><dt>Version</dt><dd>v{escape(str(reporting.get("version") or "—"))}</dd></div>
          <div><dt>Status</dt><dd>{escape(str(reporting.get("status") or "—"))}</dd></div>
        </dl>
        <div class="section-title" style="margin-top:1rem;margin-bottom:0.5rem">Included pages</div>
        <ul class="plain">{reporting_pages or "<li>No pages defined</li>"}</ul>
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
    if is_admin:
        body += f"""
    <section class="section">
      <div class="section-title">Update governance packs</div>
      <div class="card pack-card">
        <p class="pack-card-lead">Edit the DNA semantic pack and reporting layout pack. Saving writes a new version under <code>governance/</code>.</p>
        <form method="post" action="{escape(request.url)}" class="governance-edit-form">
          <div class="form-field">
            <label for="version">Version</label>
            <input id="version" name="version" value="{escape(pack.version)}" required />
          </div>
          <div class="form-field">
            <label for="dna_yaml">DNA pack (YAML)</label>
            <textarea id="dna_yaml" name="dna_yaml" rows="18" style="width:100%;font-family:ui-monospace,monospace;font-size:0.85rem">{escape(dna_yaml)}</textarea>
          </div>
          <div class="form-field">
            <label for="reporting_yaml">Reporting pack (YAML)</label>
            <textarea id="reporting_yaml" name="reporting_yaml" rows="14" style="width:100%;font-family:ui-monospace,monospace;font-size:0.85rem">{escape(reporting_yaml)}</textarea>
          </div>
          <div style="display:flex;gap:0.75rem;flex-wrap:wrap">
            <button type="submit" name="action" value="save_draft" class="btn">Save draft</button>
            <button type="submit" name="action" value="save_production" class="btn btn-primary">Save &amp; pin production</button>
          </div>
        </form>
      </div>
    </section>
    """
    return _html_response(
        request,
        client=client,
        title="Pack Registry",
        active_path="/portal/governance",
        body=body,
        is_admin=is_admin,
        settings=settings,
    )


def render_config_assistant(
    request: Request,
    *,
    settings: DnaSettings,
    client: ClientPortalConfig,
    proposal_view_data: dict[str, Any] | None = None,
    base_version: str = "",
    message: str = "",
    error: str = "",
) -> Response:
    """Config Portal — AI chat + proposal diff + preview/approve/deny."""
    url: Callable[[str], str] = lambda path: f"{request.script_root}{path if path.startswith('/') else f'/{path}'}"
    body = _governance_section_nav_html(
        url, active_path="/portal/governance/config", is_admin=True
    )
    body += page_header(
        "Config Portal",
        "Chat to propose DNA and reporting config changes. Preview the portal layout, then approve each changed file independently.",
        eyebrow="Governance",
    )
    if message:
        body += f'<div class="form-success">{escape(message)}</div>'
    if error:
        body += f'<div class="form-error">{escape(error)}</div>'

    running = bool(
        proposal_view_data and proposal_view_data.get("meta", {}).get("status") == "running"
    )
    if running:
        body += (
            '<script>setTimeout(function(){ window.location.reload(); }, 3000);</script>'
            '<div class="form-success">Assistant is working on your request… '
            "this page refreshes every few seconds.</div>"
        )

    meta = (proposal_view_data or {}).get("meta") or {}
    dna_version = escape(str(meta.get("dna_base_version") or base_version or "—"))
    reporting_version = escape(
        str(meta.get("reporting_base_version") or base_version or "—")
    )

    body += f"""
    <section class="section">
      <div class="section-title">Chat</div>
      <div class="card pack-card assistant-chat-card">
        <p class="pack-card-lead">
          DNA <code>v{dna_version}</code>
          · reporting <code>v{reporting_version}</code>
          · bucket <code>{escape(settings.s3_bucket or "local")}</code>
          · DNA <code>{escape(settings.dna_config_id)}</code>
          · reporting <code>{escape(settings.reporting_config_id)}</code>
        </p>
    """

    messages = []
    if proposal_view_data:
        conversation = proposal_view_data.get("conversation") or {}
        raw_messages = conversation.get("messages") or []
        if isinstance(raw_messages, list):
            messages = [m for m in raw_messages if isinstance(m, dict)]

    body += '<div class="assistant-chat">'
    if messages:
        for entry in messages:
            role = str(entry.get("role") or "")
            content = str(entry.get("content") or "")
            bubble_class = "assistant-bubble user" if role == "user" else "assistant-bubble"
            label = "You" if role == "user" else "Assistant"
            body += (
                f'<div class="{bubble_class}">'
                f'<div class="assistant-bubble-label">{escape(label)}</div>'
                f'<div class="assistant-bubble-text">{escape(content)}</div>'
                f"</div>"
            )
        if running:
            body += (
                '<div class="assistant-bubble thinking">'
                '<div class="assistant-bubble-label">Assistant</div>'
                '<div class="assistant-bubble-text">Thinking…</div>'
                "</div>"
            )
    else:
        body += '<p class="pack-card-lead">Describe the reporting or DNA config change you want.</p>'
    body += "</div>"

    if running:
        proposal_id = escape(str(proposal_view_data.get("proposal_id") or ""))
        body += '<p class="pack-card-lead">Send is disabled while the assistant is working.</p>'
        body += f"""
        <form method="post" action="{escape(url('/portal/governance/config'))}" style="margin-top:0.75rem">
          <input type="hidden" name="action" value="cancel_running" />
          <input type="hidden" name="proposal_id" value="{proposal_id}" />
          <button type="submit" class="btn">Cancel and unlock</button>
        </form>
        """
    else:
        body += f"""
        <form method="post" action="{escape(url('/portal/governance/config'))}" class="assistant-compose">
          <input type="hidden" name="action" value="chat" />
          <div class="form-field assistant-compose-field">
            <label for="message">Message</label>
            <textarea id="message" name="message" rows="3" required
              class="assistant-compose-input"
              placeholder="e.g. Rename Order-to-cash detail to Invoice lines and hide the chart catalog"></textarea>
          </div>
          <button type="submit" class="btn btn-primary">Send</button>
        </form>
        <script>
        (function () {{
          var form = document.querySelector("form.assistant-compose");
          var box = document.getElementById("message");
          if (!form || !box) return;
          box.addEventListener("keydown", function (event) {{
            if (event.key === "Enter" && !event.shiftKey) {{
              event.preventDefault();
              if (typeof form.requestSubmit === "function") form.requestSubmit();
              else form.submit();
            }}
          }});
        }})();
        </script>
        """
    body += """
      </div>
    </section>
    """

    if proposal_view_data and proposal_view_data.get("meta", {}).get("status") == "open":
        proposal_id = escape(str(proposal_view_data.get("proposal_id") or ""))
        summary = escape(str(meta.get("summary") or ""))
        dna_diff = str(proposal_view_data.get("diffs", {}).get("dna") or "").strip()
        reporting_diff = str(proposal_view_data.get("diffs", {}).get("reporting") or "").strip()
        dna_pending = bool(proposal_view_data.get("dna_pending"))
        reporting_pending = bool(proposal_view_data.get("reporting_pending"))
        dna_status = escape(str(meta.get("dna_status") or "skipped"))
        reporting_status = escape(str(meta.get("reporting_status") or "skipped"))
        next_dna = escape(str(meta.get("next_dna_version") or ""))
        next_reporting = escape(str(meta.get("next_reporting_version") or ""))

        body += f"""
    <section class="section">
      <div class="section-title">Proposal</div>
      <div class="card pack-card">
        <p class="pack-card-lead">{summary or "Open proposal ready for review."}</p>
        <form method="post" action="{escape(url('/portal/governance/config'))}" class="assistant-actions">
          <input type="hidden" name="proposal_id" value="{proposal_id}" />
          <button type="submit" name="action" value="preview" class="btn">Preview portal</button>
          <button type="submit" name="action" value="deny" class="btn">Deny all</button>
        </form>
    """
        body += f"""
        <div class="assistant-pack-block">
          <div class="section-title">DNA <span class="assistant-status-pill">{dna_status}</span></div>
          <pre class="assistant-diff">{escape(dna_diff) if dna_diff else "(no DNA changes)"}</pre>
        """
        if dna_pending:
            body += f"""
          <form method="post" action="{escape(url('/portal/governance/config'))}" class="assistant-approve-form">
            <input type="hidden" name="proposal_id" value="{proposal_id}" />
            <div class="form-field" style="margin:0">
              <label for="next_dna_version">DNA version to pin</label>
              <input id="next_dna_version" name="next_dna_version" value="{next_dna}" required />
            </div>
            <button type="submit" name="action" value="approve_dna" class="btn btn-primary">Approve DNA</button>
          </form>
            """
        body += "</div>"

        body += f"""
        <div class="assistant-pack-block">
          <div class="section-title">Reporting <span class="assistant-status-pill">{reporting_status}</span></div>
          <pre class="assistant-diff">{escape(reporting_diff) if reporting_diff else "(no reporting changes)"}</pre>
        """
        if reporting_pending:
            body += f"""
          <form method="post" action="{escape(url('/portal/governance/config'))}" class="assistant-approve-form">
            <input type="hidden" name="proposal_id" value="{proposal_id}" />
            <div class="form-field" style="margin:0">
              <label for="next_reporting_version">Reporting version to pin</label>
              <input id="next_reporting_version" name="next_reporting_version" value="{next_reporting}" required />
            </div>
            <button type="submit" name="action" value="approve_reporting" class="btn btn-primary">Approve reporting</button>
          </form>
            """
        body += """
        </div>
      </div>
    </section>
    """

    return _html_response(
        request,
        client=client,
        title="Config Portal",
        active_path="/portal/governance/config",
        body=body,
        is_admin=True,
        settings=settings,
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
    settings: DnaSettings | None = None,
) -> Response:
    from meshflow.dna.web.portal.cognito import PORTAL_ROLE_ADMIN, PORTAL_ROLE_MEMBER

    url: Callable[[str], str] = lambda path: f"{request.script_root}{path if path.startswith('/') else f'/{path}'}"
    seat_count = len(users)
    seats_remaining = max(client.max_users - seat_count, 0)
    at_capacity = seat_count >= client.max_users
    users_path = "/portal/governance/users"

    message_html = f'<div class="form-success">{escape(message)}</div>' if message else ""
    error_html = f'<div class="form-error">{escape(error)}</div>' if error else ""

    user_rows = ""
    for user in users:
        you = user.username.casefold() == current_username.strip().casefold()
        you_marker = " (you)" if you else ""
        enabled_label = "Active" if user.enabled else "Disabled"
        if user.status == "FORCE_CHANGE_PASSWORD":
            enabled_label = "Invite pending"
        current_role = str(getattr(user, "role", PORTAL_ROLE_MEMBER) or PORTAL_ROLE_MEMBER).lower()
        if is_admin and not you:
            role_cell = f"""
            <form method="post" action="{escape(url(users_path))}" style="display:flex;gap:0.5rem;align-items:center;margin:0">
              <input type="hidden" name="action" value="set_role" />
              <input type="hidden" name="username" value="{escape(user.username)}" />
              <select name="role" aria-label="Role for {escape(user.username)}">
                <option value="{PORTAL_ROLE_MEMBER}" {"selected" if current_role == PORTAL_ROLE_MEMBER else ""}>Member</option>
                <option value="{PORTAL_ROLE_ADMIN}" {"selected" if current_role == PORTAL_ROLE_ADMIN else ""}>Admin</option>
              </select>
              <button type="submit" class="btn" style="padding:0.35rem 0.75rem">Update</button>
            </form>
            """
        else:
            role_cell = escape(current_role.title())
        user_rows += (
            f"<tr>"
            f"<td>{escape(user.username)}{escape(you_marker)}</td>"
            f"<td>{escape(user.email or '—')}</td>"
            f"<td>{role_cell}</td>"
            f"<td>{escape(_user_status_label(user.status))}</td>"
            f"<td>{escape(enabled_label)}</td>"
            f"</tr>"
        )

    invite_disabled = at_capacity or not invites_enabled or not is_admin
    invite_note = ""
    if not is_admin:
        invite_note = (
            '<p class="hero-subtitle" style="margin-top:0">Only admins can invite users or change roles.</p>'
        )
    elif not invites_enabled:
        invite_note = (
            '<p class="hero-subtitle" style="margin-top:0">User invites require Cognito in deployed environments.</p>'
        )
    elif at_capacity:
        invite_note = (
            f'<p class="hero-subtitle" style="margin-top:0">All {client.max_users} seats are in use. '
            "Remove a user or contact HiveFlowAI to increase your limit.</p>"
        )

    if invite_disabled:
        invite_fields = (
            '<div class="form-field"><label>Username</label><input disabled /></div>'
            '<div class="form-field"><label>Email</label><input disabled /></div>'
            '<button class="btn btn-primary" type="submit" disabled>Send invite</button>'
        )
    else:
        invite_fields = f"""
          <div class="form-field">
            <label for="invite_username">Username</label>
            <input id="invite_username" name="username" autocomplete="off" required />
          </div>
          <div class="form-field">
            <label for="invite_email">Email</label>
            <input id="invite_email" name="email" type="email" autocomplete="off" required />
          </div>
          <div class="form-field">
            <label for="invite_role">Role</label>
            <select id="invite_role" name="role">
              <option value="{PORTAL_ROLE_MEMBER}" selected>Member</option>
              <option value="{PORTAL_ROLE_ADMIN}">Admin</option>
            </select>
          </div>
          <button class="btn btn-primary" type="submit">Send invite</button>
        """

    body = _governance_section_nav_html(url, active_path=users_path, is_admin=is_admin)
    body += page_header(
        "Users",
        "Portal users for this client — invite colleagues and manage admin vs member roles.",
        eyebrow="Governance",
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
      <div class="card pack-card">
        {invite_note}
        <form method="post" action="{escape(url(users_path))}">
          <input type="hidden" name="action" value="invite" />
          {invite_fields}
        </form>
      </div>
    </section>
    """
    return _html_response(
        request,
        client=client,
        title="Users",
        active_path=users_path,
        body=body,
        is_admin=is_admin,
        settings=settings,
    )


# Legacy alias until callers migrate
render_semantics = render_governance
