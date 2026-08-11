"""Gold source-docs inspector — parallel to Semantic Builder, read-only inspection."""

from __future__ import annotations

import json
from html import escape
from typing import Any, Callable

from werkzeug.wrappers import Request, Response

from meshflow.dna.settings import DnaSettings
from meshflow.dna.source_docs_reference import load_source_docs_gold
from meshflow.dna.web.portal.dna_nav import SOURCE_DOCS_INSPECTOR_ROOT
from meshflow.dna.web.theme import page_header


def _url(request: Request) -> Callable[[str], str]:
    return lambda path: f"{request.script_root}{path if path.startswith('/') else f'/{path}'}"


def _admin_nav(*, available: bool, is_admin: bool) -> str:
    # Empty state already has a primary Build button in the card — only show
    # the top nav action once gold exists (rebuild).
    if not is_admin or not available:
        return ""
    return (
        '<nav class="semantic-builder-sub-nav" id="source-docs-admin-nav" '
        'aria-label="Source docs actions">'
        '<button type="button" class="semantic-builder-sub-nav-item '
        'semantic-builder-sub-nav-button semantic-builder-sub-nav-primary" '
        'id="source-docs-rebuild-btn">Rebuild Gold Reference</button>'
        "</nav>"
    )


def _summary_cards(summary: dict[str, Any], *, available: bool, complete: bool) -> str:
    if not available:
        return ""
    status = "Complete" if complete else "Partial"
    items = [
        ("Entities", summary.get("entity_count") or 0),
        ("Properties", summary.get("property_count") or 0),
        ("Relationships", summary.get("relationship_count") or 0),
        ("Tagged properties", summary.get("tagged_property_count") or 0),
        ("Status", status),
    ]
    generated = str(summary.get("generated_at") or "").strip()
    gen_html = (
        f'<p class="pack-card-lead">Generated at {escape(generated)}</p>' if generated else ""
    )
    cards = "".join(
        f'<div class="source-docs-stat"><span class="source-docs-stat-label">{escape(label)}</span>'
        f'<strong class="source-docs-stat-value">{escape(str(value))}</strong></div>'
        for label, value in items
    )
    return f"""
    <div class="source-docs-summary">
      {cards}
    </div>
    {gen_html}
    """


def _empty_state(*, is_admin: bool) -> str:
    action = ""
    if is_admin:
        action = (
            '<p class="semantic-builder-landing-action">'
            '<button type="button" class="btn semantic-builder-start-btn" '
            'id="source-docs-build-empty-btn">Build Gold Reference</button></p>'
        )
    return f"""
    <section class="section semantic-builder-landing">
      <div class="card pack-card">
        <p class="pack-card-lead">
          No gold source documentation is available yet for this client.
          Gold catalogs are created by merging the global MS Learn reference with
          any client exclude/addition overlays.
        </p>
        {action}
        <p class="pack-card-lead semantic-builder-landing-hint">
          After the build finishes, this page shows properties, relationships, and
          conceptual tags for inspection (no approval gates).
        </p>
      </div>
    </section>
    """


def _properties_panel(catalog: dict[str, Any] | None) -> str:
    if not catalog:
        return '<p class="semantic-builder-empty-state">entity_properties.yaml is not in gold yet.</p>'
    entities = [e for e in (catalog.get("entities") or []) if isinstance(e, dict)]
    if not entities:
        return '<p class="semantic-builder-empty-state">No entities in gold properties catalog.</p>'

    options = []
    sections: list[str] = []
    for entity in entities:
        silver = str(entity.get("silver_entity") or "").strip()
        if not silver:
            continue
        options.append(f'<option value="{escape(silver)}">{escape(silver)}</option>')
        props = [p for p in (entity.get("properties") or []) if isinstance(p, dict)]
        rows = []
        for prop in props:
            name = str(prop.get("name") or "")
            ptype = str(prop.get("type") or "")
            desc = str(prop.get("description") or "")
            rows.append(
                "<tr>"
                f"<td><code>{escape(name)}</code></td>"
                f"<td>{escape(ptype)}</td>"
                f"<td>{escape(desc)}</td>"
                "</tr>"
            )
        slug = str(entity.get("bc_resource_slug") or "")
        url = str(entity.get("ms_learn_url") or "")
        meta = []
        if slug:
            meta.append(f"slug <code>{escape(slug)}</code>")
        if url:
            meta.append(
                f'<a href="{escape(url)}" target="_blank" rel="noopener noreferrer">MS Learn</a>'
            )
        meta_html = f'<p class="pack-card-lead">{" · ".join(meta)}</p>' if meta else ""
        desc = str(entity.get("description") or "")
        desc_html = f'<p class="pack-card-lead">{escape(desc)}</p>' if desc else ""
        sections.append(
            f"""
            <div class="source-docs-entity" data-entity="{escape(silver)}">
              <div class="source-docs-entity-title">{escape(silver)}
                <span class="source-docs-count">{len(props)} properties</span>
              </div>
              {meta_html}{desc_html}
              <div class="table-wrap semantic-builder-scroll">
                <table class="semantic-builder-table semantic-builder-compact-table">
                  <thead><tr><th>Property</th><th>Type</th><th>Description</th></tr></thead>
                  <tbody>{''.join(rows) or '<tr><td colspan="3">No properties</td></tr>'}</tbody>
                </table>
              </div>
            </div>
            """
        )

    return f"""
    <div class="source-docs-filter-bar">
      <label for="source-docs-entity-filter">Entity</label>
      <select id="source-docs-entity-filter" class="governance-role-select semantic-builder-select">
        <option value="">All entities ({len(entities)})</option>
        {''.join(options)}
      </select>
    </div>
    <div id="source-docs-properties-list">
      {''.join(sections)}
    </div>
    """


def _relationships_panel(catalog: dict[str, Any] | None) -> str:
    if not catalog:
        return (
            '<p class="semantic-builder-empty-state">'
            "entity_relationships.yaml is not in gold yet.</p>"
        )
    tables = catalog.get("tables") or {}
    if not isinstance(tables, dict) or not tables:
        return '<p class="semantic-builder-empty-state">No tables in gold relationships catalog.</p>'

    rows: list[str] = []
    for table_name in sorted(tables.keys()):
        table = tables[table_name]
        if not isinstance(table, dict):
            continue
        pk = str(table.get("PK") or "")
        rels = [r for r in (table.get("relationships") or []) if isinstance(r, dict)]
        if not rels:
            rows.append(
                "<tr>"
                f"<td><code>{escape(str(table_name))}</code></td>"
                f"<td><code>{escape(pk)}</code></td>"
                "<td colspan=\"2\" class=\"semantic-builder-empty-state\">No foreign keys</td>"
                "</tr>"
            )
            continue
        for rel in rels:
            rows.append(
                "<tr>"
                f"<td><code>{escape(str(table_name))}</code></td>"
                f"<td><code>{escape(pk)}</code></td>"
                f"<td><code>{escape(str(rel.get('FK') or ''))}</code></td>"
                f"<td><code>{escape(str(rel.get('target') or ''))}</code></td>"
                "</tr>"
            )

    return f"""
    <p class="pack-card-lead">
      {int(catalog.get('table_count') or len(tables))} tables ·
      {int(catalog.get('relationship_count') or 0)} relationships
    </p>
    <div class="table-wrap semantic-builder-scroll">
      <table class="semantic-builder-table semantic-builder-compact-table">
        <thead>
          <tr><th>Table</th><th>PK</th><th>FK</th><th>Target</th></tr>
        </thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
    </div>
    """


def _tags_panel(catalog: dict[str, Any] | None) -> str:
    if not catalog:
        return (
            '<p class="semantic-builder-empty-state">'
            "entity_property_tags.yaml is not in gold yet.</p>"
        )
    entities = [e for e in (catalog.get("entities") or []) if isinstance(e, dict)]
    if not entities:
        return '<p class="semantic-builder-empty-state">No entities in gold tags catalog.</p>'

    rows: list[str] = []
    for entity in entities:
        silver = str(entity.get("silver_entity") or "").strip()
        for prop in entity.get("properties") or []:
            if not isinstance(prop, dict):
                continue
            name = str(prop.get("name") or "")
            tags = [str(t) for t in (prop.get("tags") or []) if str(t).strip()]
            tag_html = (
                "".join(f'<span class="source-docs-tag">{escape(tag)}</span>' for tag in tags)
                if tags
                else '<span class="semantic-builder-empty-state">—</span>'
            )
            rows.append(
                "<tr>"
                f"<td><code>{escape(silver)}</code></td>"
                f"<td><code>{escape(name)}</code></td>"
                f"<td class=\"source-docs-tag-cell\">{tag_html}</td>"
                "</tr>"
            )

    return f"""
    <p class="pack-card-lead">
      {int(catalog.get('entity_count') or len(entities))} entities ·
      {int(catalog.get('tagged_property_count') or 0)} tagged properties
    </p>
    <div class="table-wrap semantic-builder-scroll">
      <table class="semantic-builder-table semantic-builder-compact-table">
        <thead>
          <tr><th>Entity</th><th>Property</th><th>Tags</th></tr>
        </thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
    </div>
    """


def _workspace(payload: dict[str, Any]) -> str:
    return f"""
    <section class="section">
      <div class="semantic-builder-keys-tabs-section" id="source-docs-tabs" data-default-tab="properties">
        <div class="semantic-builder-keys-tabs" role="tablist" aria-label="Gold source docs">
          <button type="button" class="semantic-builder-keys-tab active" role="tab"
                  data-source-docs-tab="properties" aria-selected="true"
                  aria-controls="source-docs-panel-properties">Properties</button>
          <button type="button" class="semantic-builder-keys-tab" role="tab"
                  data-source-docs-tab="relationships" aria-selected="false"
                  aria-controls="source-docs-panel-relationships">Relationships</button>
          <button type="button" class="semantic-builder-keys-tab" role="tab"
                  data-source-docs-tab="tags" aria-selected="false"
                  aria-controls="source-docs-panel-tags">Tags</button>
        </div>
        <div class="semantic-builder-keys-panel" id="source-docs-panel-properties"
             data-source-docs-panel="properties" role="tabpanel">
          {_properties_panel(payload.get("entity_properties"))}
        </div>
        <div class="semantic-builder-keys-panel" id="source-docs-panel-relationships"
             data-source-docs-panel="relationships" role="tabpanel" hidden>
          {_relationships_panel(payload.get("entity_relationships"))}
        </div>
        <div class="semantic-builder-keys-panel" id="source-docs-panel-tags"
             data-source-docs-panel="tags" role="tabpanel" hidden>
          {_tags_panel(payload.get("entity_property_tags"))}
        </div>
      </div>
    </section>
    """


def render_source_docs_inspector_content_html(
    settings: DnaSettings,
    *,
    is_admin: bool,
) -> str:
    payload = load_source_docs_gold(settings)
    if not payload.get("available"):
        return _empty_state(is_admin=is_admin)
    return (
        _summary_cards(
            payload.get("summary") or {},
            available=True,
            complete=bool(payload.get("complete")),
        )
        + _workspace(payload)
    )


def _styles() -> str:
    return """
<style>
.source-docs-page { display: flex; flex-direction: column; gap: 1.25rem; }
.source-docs-page .page-header { margin-bottom: 0; }
.source-docs-page .page-header h1 {
  font-size: clamp(1.25rem, 2.5vw, 1.6rem);
  margin-bottom: 0;
}
.semantic-builder-sub-nav {
  display: flex; flex-wrap: wrap; gap: 0.5rem; align-items: center;
}
.semantic-builder-sub-nav-item {
  display: inline-flex; align-items: center; gap: 0.35rem;
  padding: 0.45rem 0.85rem; border: 1px solid var(--border);
  border-radius: var(--radius); background: rgba(8, 18, 40, 0.35);
  color: var(--text); text-decoration: none; font: inherit; font-size: 0.84rem;
}
.semantic-builder-sub-nav-button { cursor: pointer; }
.semantic-builder-sub-nav-button:disabled { opacity: 0.55; cursor: not-allowed; }
.semantic-builder-sub-nav-primary {
  background: #059669; border-color: #10b981; color: #ecfdf5; font-weight: 600;
}
.semantic-builder-sub-nav-primary:hover:not(:disabled) {
  background: #10b981; border-color: #34d399; color: #fff;
}
.semantic-builder-start-btn {
  background: #059669; border: 1px solid #10b981; color: #ecfdf5;
  font-size: 1.05rem; padding: 0.75rem 1.5rem; border-radius: var(--radius);
  font-weight: 600; cursor: pointer;
}
.semantic-builder-start-btn:hover { background: #10b981; border-color: #34d399; color: #fff; }
.semantic-builder-landing-action { margin: 1.25rem 0 0.75rem; }
.semantic-builder-landing-hint { margin-top: 1rem; }
.semantic-builder-empty-state { color: var(--text-muted); font-size: 0.9rem; }
.semantic-builder-scroll { max-height: 32rem; overflow: auto; }
.semantic-builder-table { width: 100%; border-collapse: collapse; font-size: 0.86rem; }
.semantic-builder-table th, .semantic-builder-table td {
  padding: 0.45rem 0.55rem; border-bottom: 1px solid var(--border);
  text-align: left; vertical-align: top;
}
.semantic-builder-table th { color: var(--text-muted); font-weight: 600; font-size: 0.78rem; }
.semantic-builder-table code { font-size: 0.8rem; word-break: break-all; }
.semantic-builder-keys-tabs {
  display: flex; gap: 0; border-bottom: 1px solid var(--border); margin-bottom: 0;
}
.semantic-builder-keys-tab {
  padding: 0.65rem 1rem; border: none; border-bottom: 2px solid transparent;
  margin-bottom: -1px; background: transparent; color: var(--text-muted);
  cursor: pointer; font: inherit; font-size: 0.84rem; font-weight: 500;
}
.semantic-builder-keys-tab:hover { color: var(--text); }
.semantic-builder-keys-tab.active {
  color: var(--text); border-bottom-color: var(--accent-mid, #38bdf8);
}
.semantic-builder-keys-panel { padding-top: 1rem; }
.source-docs-summary {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(7.5rem, 1fr));
  gap: 0.65rem;
}
.source-docs-stat {
  padding: 0.65rem 0.75rem; border: 1px solid var(--border);
  border-radius: var(--radius); background: rgba(8, 18, 40, 0.35);
}
.source-docs-stat-label {
  display: block; font-size: 0.72rem; color: var(--text-muted); margin-bottom: 0.2rem;
}
.source-docs-stat-value { font-size: 1.05rem; }
.source-docs-filter-bar {
  display: flex; flex-wrap: wrap; gap: 0.65rem; align-items: center; margin-bottom: 0.85rem;
}
.source-docs-filter-bar label { font-size: 0.84rem; color: var(--text-muted); }
.source-docs-entity {
  margin-bottom: 1.25rem; padding-bottom: 1rem; border-bottom: 1px solid var(--border);
}
.source-docs-entity-title {
  font-weight: 600; margin-bottom: 0.35rem; display: flex; gap: 0.5rem; align-items: baseline;
}
.source-docs-count { font-size: 0.78rem; color: var(--text-muted); font-weight: 500; }
.source-docs-tag {
  display: inline-block; margin: 0.1rem 0.25rem 0.1rem 0;
  padding: 0.15rem 0.45rem; border-radius: 999px;
  border: 1px solid rgba(56, 189, 248, 0.35);
  background: rgba(56, 189, 248, 0.1); font-size: 0.75rem;
}
.source-docs-status {
  padding: 0.65rem 0.85rem; border-radius: var(--radius);
  border: 1px solid rgba(56, 189, 248, 0.35);
  background: rgba(56, 189, 248, 0.08); font-size: 0.9rem;
}
.source-docs-status[hidden] { display: none !important; }
.source-docs-status.is-error {
  border-color: rgba(248, 113, 113, 0.45); background: rgba(248, 113, 113, 0.1);
}
</style>
"""


def _script(api_root: str) -> str:
    api = json.dumps(api_root)
    return f"""
<script>
(function () {{
  var apiRoot = {api};
  var statusEl = document.getElementById("source-docs-status");
  var pollTimer = null;

  function setStatus(message, isError) {{
    if (!statusEl) return;
    if (!message) {{
      statusEl.hidden = true;
      statusEl.textContent = "";
      statusEl.classList.remove("is-error");
      return;
    }}
    statusEl.hidden = false;
    statusEl.textContent = message;
    statusEl.classList.toggle("is-error", !!isError);
  }}

  function activateTab(name) {{
    var section = document.getElementById("source-docs-tabs");
    if (!section) return;
    section.querySelectorAll("[data-source-docs-tab]").forEach(function (btn) {{
      var on = btn.getAttribute("data-source-docs-tab") === name;
      btn.classList.toggle("active", on);
      btn.setAttribute("aria-selected", on ? "true" : "false");
    }});
    section.querySelectorAll("[data-source-docs-panel]").forEach(function (panel) {{
      panel.hidden = panel.getAttribute("data-source-docs-panel") !== name;
    }});
  }}

  function filterEntities() {{
    var select = document.getElementById("source-docs-entity-filter");
    var list = document.getElementById("source-docs-properties-list");
    if (!select || !list) return;
    var value = select.value || "";
    list.querySelectorAll(".source-docs-entity").forEach(function (el) {{
      var entity = el.getAttribute("data-entity") || "";
      el.hidden = !!(value && entity !== value);
    }});
  }}

  function bindTabs() {{
    var section = document.getElementById("source-docs-tabs");
    if (!section) return;
    section.querySelectorAll("[data-source-docs-tab]").forEach(function (btn) {{
      btn.addEventListener("click", function () {{
        activateTab(btn.getAttribute("data-source-docs-tab") || "properties");
      }});
    }});
    activateTab(section.getAttribute("data-default-tab") || "properties");
  }}

  function bindEntityFilter() {{
    var select = document.getElementById("source-docs-entity-filter");
    if (!select) return;
    select.addEventListener("change", filterEntities);
    // Show all by default: unhide every entity when filter is empty.
    filterEntities();
    if (!select.value) {{
      document.querySelectorAll(".source-docs-entity").forEach(function (el) {{
        el.hidden = false;
      }});
    }}
  }}

  async function fetchStatus() {{
    var response = await fetch(apiRoot, {{ credentials: "same-origin" }});
    if (!response.ok) throw new Error("Status request failed (" + response.status + ")");
    return response.json();
  }}

  async function startBuild() {{
    setStatus("Building gold source reference…");
    ["source-docs-build-btn", "source-docs-rebuild-btn", "source-docs-build-empty-btn"].forEach(function (id) {{
      var btn = document.getElementById(id);
      if (btn) btn.disabled = true;
    }});
    try {{
      var response = await fetch(apiRoot + "/build", {{
        method: "POST",
        credentials: "same-origin",
        headers: {{ "Content-Type": "application/json" }},
        body: JSON.stringify({{ seed_missing_overlays: true, publish_schemas: true }})
      }});
      var payload = await response.json().catch(function () {{ return {{}}; }});
      if (!response.ok) {{
        throw new Error(payload.error || payload.message || ("Build failed (" + response.status + ")"));
      }}
      if (payload.status === "published") {{
        setStatus("Gold reference ready. Reloading…");
        window.location.reload();
        return;
      }}
      setStatus("Gold build queued. Waiting for catalogs…");
      startPolling();
    }} catch (err) {{
      setStatus(String(err && err.message ? err.message : err), true);
      ["source-docs-build-btn", "source-docs-rebuild-btn", "source-docs-build-empty-btn"].forEach(function (id) {{
        var btn = document.getElementById(id);
        if (btn) btn.disabled = false;
      }});
    }}
  }}

  function startPolling() {{
    if (pollTimer) clearInterval(pollTimer);
    var attempts = 0;
    pollTimer = setInterval(async function () {{
      attempts += 1;
      try {{
        var status = await fetchStatus();
        if (status.available) {{
          clearInterval(pollTimer);
          setStatus("Gold reference ready. Reloading…");
          window.location.reload();
          return;
        }}
        if (attempts >= 40) {{
          clearInterval(pollTimer);
          setStatus("Build is still running. Refresh this page in a minute.", true);
        }}
      }} catch (err) {{
        if (attempts >= 5) {{
          clearInterval(pollTimer);
          setStatus(String(err && err.message ? err.message : err), true);
        }}
      }}
    }}, 3000);
  }}

  document.addEventListener("click", function (event) {{
    var target = event.target;
    if (!target || !target.id) return;
    if (target.id === "source-docs-build-btn"
        || target.id === "source-docs-rebuild-btn"
        || target.id === "source-docs-build-empty-btn") {{
      startBuild();
    }}
  }});

  bindTabs();
  bindEntityFilter();
}})();
</script>
"""


def render_source_docs_inspector_page(
    request: Request,
    *,
    settings: DnaSettings,
    client: Any,
    is_admin: bool = False,
    html_response: Callable[..., Response],
    message: str = "",
    error: str = "",
) -> Response:
    url = _url(request)
    api_root = url("/api/source-docs-gold")
    payload = load_source_docs_gold(settings)
    available = bool(payload.get("available"))

    body = f"""
    <div class="source-docs-page semantic-builder-page">
      {page_header(
          "Source Semantic Reference",
          "Inspect gold MS Learn properties, relationships, and tags for this client.",
      )}
      {_admin_nav(available=available, is_admin=is_admin)}
    """
    if message:
        body += f'<div class="form-success">{escape(message)}</div>'
    if error:
        body += f'<div class="form-error">{escape(error)}</div>'
    body += """
      <div id="source-docs-status" class="source-docs-status" hidden></div>
      <div id="source-docs-content">
    """
    body += render_source_docs_inspector_content_html(settings, is_admin=is_admin)
    body += "</div>"
    body += _styles()
    body += _script(api_root)
    body += "</div>"

    return html_response(
        request,
        client=client,
        title="Source Semantic Reference",
        active_path=SOURCE_DOCS_INSPECTOR_ROOT,
        body=body,
        is_admin=is_admin,
        settings=settings,
    )
