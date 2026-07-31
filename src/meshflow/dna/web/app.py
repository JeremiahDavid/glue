"""Minimal DNA web UI — definition portal and KPI views."""

from __future__ import annotations

import json
from typing import Any

from werkzeug.routing import Map, Rule
from werkzeug.serving import run_simple
from werkzeug.wrappers import Request, Response

from meshflow.dna.settings import DnaSettings
from meshflow.dna.store import load_pack_from_settings, read_json_artifact, read_production_output
from meshflow.dna.workflow import load_workflow_state


def _json_response(payload: Any, status: int = 200) -> Response:
    return Response(
        json.dumps(payload, indent=2, default=str),
        status=status,
        mimetype="application/json",
    )


def _html_page(title: str, body: str) -> Response:
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title}</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 2rem; line-height: 1.5; color: #1a1a1a; }}
    h1, h2 {{ margin-bottom: 0.5rem; }}
    .card {{ border: 1px solid #ddd; border-radius: 8px; padding: 1rem; margin-bottom: 1rem; }}
    .muted {{ color: #666; font-size: 0.9rem; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border-bottom: 1px solid #eee; text-align: left; padding: 0.5rem; }}
    nav a {{ margin-right: 1rem; }}
    .kpi-value {{ font-size: 1.8rem; font-weight: 600; }}
  </style>
</head>
<body>
  <nav>
    <a href="/">Home</a>
    <a href="/definitions">Definitions</a>
    <a href="/kpis">KPIs</a>
  </nav>
  {body}
</body>
</html>"""
    return Response(html, mimetype="text/html")


def create_app(settings: DnaSettings):
    url_map = Map(
        [
            Rule("/", endpoint="home"),
            Rule("/definitions", endpoint="definitions"),
            Rule("/kpis", endpoint="kpis"),
            Rule("/api/pack", endpoint="api_pack"),
            Rule("/api/kpis", endpoint="api_kpis"),
            Rule("/api/manifest", endpoint="api_manifest"),
        ]
    )

    def on_home(_request: Request) -> Response:
        workflow = load_workflow_state(settings, settings.pack_id)
        body = """
        <h1>Meshflow DNA</h1>
        <p class="muted">Certified semantic layer — definition portal and KPI views.</p>
        <div class="card">
          <h2>Quick links</h2>
          <p><a href="/definitions">View definition pack</a> — joins, KPIs, approval status</p>
          <p><a href="/kpis">View KPI snapshot</a> — latest published metric values</p>
        </div>
        """
        active = workflow.get("active_version")
        if active:
            body += f'<p class="muted">Active production pack version: <strong>{active}</strong></p>'
        return _html_page("Meshflow DNA", body)

    def on_definitions(_request: Request) -> Response:
        pack = load_pack_from_settings(settings)
        kpi_rows = "".join(
            f"<tr><td>{kpi.id}</td><td>{kpi.name}</td><td>{kpi.definition}</td>"
            f"<td>{kpi.formula_type}</td></tr>"
            for kpi in pack.kpis
        )
        join_rows = "".join(
            f"<tr><td>{join.id}</td><td>{join.left_entity}</td><td>{join.right_entity}</td>"
            f"<td>{join.left_key} → {join.right_key}</td><td>{join.cardinality}</td></tr>"
            for join in pack.joins
        )
        limitations = "".join(f"<li>{item}</li>" for item in pack.limitations)
        body = f"""
        <h1>Definition pack</h1>
        <p><strong>{pack.pack_id}</strong> v{pack.version} · status: {pack.approval.status}</p>
        <p class="muted">{pack.description}</p>
        <div class="card">
          <h2>Approval</h2>
          <p>Approver: {pack.approval.approver or "—"} · Date: {pack.approval.approved_at or "—"}</p>
          <p>{pack.approval.notes}</p>
        </div>
        <div class="card">
          <h2>Joins</h2>
          <table><thead><tr><th>ID</th><th>Left</th><th>Right</th><th>Keys</th><th>Cardinality</th></tr></thead>
          <tbody>{join_rows or "<tr><td colspan='5'>No joins</td></tr>"}</tbody></table>
        </div>
        <div class="card">
          <h2>KPIs</h2>
          <table><thead><tr><th>ID</th><th>Name</th><th>Definition</th><th>Formula</th></tr></thead>
          <tbody>{kpi_rows}</tbody></table>
        </div>
        <div class="card"><h2>Limitations</h2><ul>{limitations or "<li>None documented</li>"}</ul></div>
        """
        return _html_page("Definitions", body)

    def on_kpis(_request: Request) -> Response:
        rows = read_production_output(settings, "out_kpi_snapshot")
        if not rows:
            return _html_page("KPIs", "<h1>KPIs</h1><p>No published KPI snapshot yet. Run <code>meshflow-dna publish</code>.</p>")
        cards = ""
        for row in rows:
            value = row.get("value", 0)
            unit = row.get("unit", "")
            cards += f"""
            <div class="card">
              <h2>{row.get("kpi_name", row.get("kpi_id"))}</h2>
              <div class="kpi-value">{value:,.2f}{f" {unit}" if unit else ""}</div>
              <p class="muted">{row.get("definition", "")}</p>
              <p class="muted">ID: {row.get("kpi_id")} · pack {row.get("pack_id")} v{row.get("pack_version")}</p>
            </div>
            """
        return _html_page("KPIs", f"<h1>KPI snapshot</h1>{cards}")

    def on_api_pack(_request: Request) -> Response:
        return _json_response(load_pack_from_settings(settings).to_dict())

    def on_api_kpis(_request: Request) -> Response:
        return _json_response(read_production_output(settings, "out_kpi_snapshot"))

    def on_api_manifest(_request: Request) -> Response:
        manifest = read_json_artifact(settings, f"{settings.gold_dna_prefix}/manifest.json")
        return _json_response(manifest or {})

    endpoints = {
        "home": on_home,
        "definitions": on_definitions,
        "kpis": on_kpis,
        "api_pack": on_api_pack,
        "api_kpis": on_api_kpis,
        "api_manifest": on_api_manifest,
    }

    def application(environ, start_response):
        request = Request(environ)
        adapter = url_map.bind_to_environ(environ)
        try:
            endpoint, _values = adapter.match()
            response = endpoints[endpoint](request)
        except Exception as exc:  # noqa: BLE001 — surface errors in dev UI
            response = _json_response({"error": str(exc)}, status=500)
        return response(environ, start_response)

    return application


def run_server(settings: DnaSettings, *, host: str = "127.0.0.1", port: int = 8080) -> None:
    app = create_app(settings)
    print(f"DNA web UI at http://{host}:{port}/")
    run_simple(host, port, app, use_reloader=False, use_debugger=False)
