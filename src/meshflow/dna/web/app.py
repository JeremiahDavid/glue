"""HiveFlowAI reporting web UI — definition portal and KPI views."""

from __future__ import annotations

import json
import mimetypes
from pathlib import Path
from typing import Any

from werkzeug.routing import Map, Rule
from werkzeug.serving import run_simple
from werkzeug.wrappers import Request, Response

from meshflow.dna.settings import DnaSettings
from meshflow.dna.store import load_pack_from_settings, read_json_artifact, read_production_output
from meshflow.dna.web.theme import (
    BRAND_NAME,
    MIME_TYPES,
    STATIC_DIR,
    TAGLINE,
    badge_row,
    empty_state,
    escape,
    page_header,
    render_page,
)
from meshflow.dna.workflow import load_workflow_state

REVENUE_OUTPUT_ID = "out_fact_revenue_lines"
REVENUE_TABLE_LIMIT = 500
REVENUE_DISPLAY_COLUMNS = (
    ("postingDate", "Posting date", False),
    ("number", "Customer #", False),
    ("displayName", "Customer", False),
    ("documentId", "Document", False),
    ("lineNumber", "Line", True),
    ("quantity", "Qty", True),
    ("unitPrice", "Unit price", True),
    ("amount", "Amount", True),
)


def _json_response(payload: Any, status: int = 200) -> Response:
    return Response(
        json.dumps(payload, indent=2, default=str),
        status=status,
        mimetype="application/json",
    )


def _html_response(title: str, active_path: str, body: str, *, page_title: str | None = None) -> Response:
    return Response(
        render_page(title=title, active_path=active_path, body=body, page_title=page_title),
        mimetype="text/html",
    )


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


def _serve_static(filename: str) -> Response:
    safe_name = Path(filename).name
    asset_path = STATIC_DIR / safe_name
    if not asset_path.is_file():
        return Response("Not found", status=404)

    suffix = asset_path.suffix.lower()
    mime = MIME_TYPES.get(suffix) or mimetypes.guess_type(safe_name)[0] or "application/octet-stream"
    return Response(
        asset_path.read_bytes(),
        mimetype=mime,
        headers={"Cache-Control": "public, max-age=86400"},
    )


def create_app(settings: DnaSettings):
    url_map = Map(
        [
            Rule("/", endpoint="home"),
            Rule("/executive", endpoint="executive"),
            Rule("/kpis", endpoint="executive"),
            Rule("/revenue", endpoint="revenue"),
            Rule("/definitions", endpoint="definitions"),
            Rule("/static/<path:filename>", endpoint="static"),
            Rule("/api/pack", endpoint="api_pack"),
            Rule("/api/kpis", endpoint="api_kpis"),
            Rule("/api/revenue", endpoint="api_revenue"),
            Rule("/api/manifest", endpoint="api_manifest"),
        ]
    )

    def on_home(_request: Request) -> Response:
        workflow = load_workflow_state(settings, settings.pack_id)
        kpi_rows = read_production_output(settings, "out_kpi_snapshot")
        manifest = read_json_artifact(settings, f"{settings.gold_dna_prefix}/manifest.json") or {}

        badges: list[tuple[str, bool]] = [(f"Pack {settings.pack_id}", False)]
        active = workflow.get("active_version")
        if active:
            badges.append((f"v{active} production", True))
        if manifest.get("published_at"):
            badges.append((f"Updated {manifest.get('published_at')}", False))

        body = page_header(
            "Overview",
            "Certified metrics from your governed semantic layer — every number traceable to an approved definition.",
            eyebrow=TAGLINE,
        )
        body += badge_row(*badges)
        body += '<section class="section" style="margin-top:1.75rem"><div class="section-title">Executive snapshot</div>'
        body += _kpi_cards_html(kpi_rows)
        body += "</section>"
        body += """
        <section class="section">
          <div class="section-title">Explore</div>
          <div class="card">
            <div class="quick-links">
              <a class="quick-link" href="/executive">
                <div><strong>Executive KPIs</strong><br><span>Full metric cards with definitions and pack provenance</span></div>
                <span class="arrow">→</span>
              </a>
              <a class="quick-link" href="/revenue">
                <div><strong>Order-to-cash detail</strong><br><span>Posted invoice lines from certified gold output</span></div>
                <span class="arrow">→</span>
              </a>
              <a class="quick-link" href="/definitions">
                <div><strong>Semantic definitions</strong><br><span>Joins, KPI formulas, limitations, and approval record</span></div>
                <span class="arrow">→</span>
              </a>
            </div>
          </div>
        </section>
        """
        return _html_response("Overview", "/", body)

    def on_executive(_request: Request) -> Response:
        rows = read_production_output(settings, "out_kpi_snapshot")
        body = page_header(
            "Executive KPIs",
            "Key performance indicators compiled from your DNA definition pack and published to gold.",
            eyebrow="Metrics",
        )
        body += _kpi_cards_html(rows)
        return _html_response("Executive", "/executive", body)

    def on_revenue(_request: Request) -> Response:
        all_rows = read_production_output(settings, REVENUE_OUTPUT_ID)
        rows = _revenue_rows(settings)
        body = page_header(
            "Order-to-cash detail",
            f"Posted sales invoice lines from certified output {REVENUE_OUTPUT_ID}.",
            eyebrow="Revenue",
        )
        body += f'<section class="section">{_revenue_table_html(rows, truncated=len(all_rows) > len(rows))}</section>'
        return _html_response("Revenue", "/revenue", body)

    def on_definitions(_request: Request) -> Response:
        pack = load_pack_from_settings(settings)
        kpi_rows = "".join(
            f"<tr><td><code>{escape(kpi.id)}</code></td><td>{escape(kpi.name)}</td>"
            f"<td>{escape(kpi.definition)}</td><td>{escape(kpi.formula_type)}</td></tr>"
            for kpi in pack.kpis
        )
        join_rows = "".join(
            f"<tr><td><code>{escape(join.id)}</code></td><td>{escape(join.left_entity)}</td>"
            f"<td>{escape(join.right_entity)}</td>"
            f"<td>{escape(join.left_key)} → {escape(join.right_key)}</td>"
            f"<td>{escape(join.cardinality)}</td></tr>"
            for join in pack.joins
        )
        limitations = "".join(f"<li>{escape(item)}</li>" for item in pack.limitations)

        body = page_header(
            "Semantic definitions",
            pack.description,
            eyebrow="DNA pack",
        )
        body += badge_row(
            (f"{pack.pack_id} v{pack.version}", True),
            (pack.approval.status, False),
        )
        body += f"""
        <section class="section">
          <div class="card">
            <div class="section-title">Approval</div>
            <p style="color:var(--text-muted);font-size:0.9rem">
              Approver: {escape(pack.approval.approver or "—")} ·
              Date: {escape(pack.approval.approved_at or "—")}
            </p>
            <p style="color:var(--text-muted);font-size:0.9rem;margin-top:0.5rem">{escape(pack.approval.notes)}</p>
          </div>
        </section>
        <section class="section">
          <div class="section-title">Joins</div>
          <div class="table-wrap">
            <table>
              <thead><tr><th>ID</th><th>Left</th><th>Right</th><th>Keys</th><th>Cardinality</th></tr></thead>
              <tbody>{join_rows or "<tr><td colspan='5'>No joins defined</td></tr>"}</tbody>
            </table>
          </div>
        </section>
        <section class="section">
          <div class="section-title">KPI definitions</div>
          <div class="table-wrap">
            <table>
              <thead><tr><th>ID</th><th>Name</th><th>Definition</th><th>Formula</th></tr></thead>
              <tbody>{kpi_rows}</tbody>
            </table>
          </div>
        </section>
        <section class="section">
          <div class="section-title">Known limitations</div>
          <div class="card"><ul class="plain">{limitations or "<li>None documented</li>"}</ul></div>
        </section>
        """
        return _html_response("Semantics", "/definitions", body)

    def on_static(_request: Request, filename: str) -> Response:
        return _serve_static(filename)

    def on_api_pack(_request: Request) -> Response:
        return _json_response(load_pack_from_settings(settings).to_dict())

    def on_api_kpis(_request: Request) -> Response:
        return _json_response(read_production_output(settings, "out_kpi_snapshot"))

    def on_api_revenue(_request: Request) -> Response:
        all_rows = read_production_output(settings, REVENUE_OUTPUT_ID)
        rows = _revenue_rows(settings)
        return _json_response(
            {
                "output_id": REVENUE_OUTPUT_ID,
                "row_count": len(all_rows),
                "truncated": len(all_rows) > len(rows),
                "rows": rows,
            }
        )

    def on_api_manifest(_request: Request) -> Response:
        manifest = read_json_artifact(settings, f"{settings.gold_dna_prefix}/manifest.json")
        return _json_response(manifest or {})

    endpoints = {
        "home": on_home,
        "executive": on_executive,
        "revenue": on_revenue,
        "definitions": on_definitions,
        "static": on_static,
        "api_pack": on_api_pack,
        "api_kpis": on_api_kpis,
        "api_revenue": on_api_revenue,
        "api_manifest": on_api_manifest,
    }

    def application(environ, start_response):
        request = Request(environ)
        adapter = url_map.bind_to_environ(environ)
        try:
            endpoint, values = adapter.match()
            response = endpoints[endpoint](request, **values)
        except Exception as exc:  # noqa: BLE001 — surface errors in dev UI
            response = _json_response({"error": str(exc)}, status=500)
        return response(environ, start_response)

    return application


def run_server(settings: DnaSettings, *, host: str = "127.0.0.1", port: int = 8080) -> None:
    app = create_app(settings)
    print(f"{BRAND_NAME} at http://{host}:{port}/")
    run_simple(host, port, app, use_reloader=False, use_debugger=False)
