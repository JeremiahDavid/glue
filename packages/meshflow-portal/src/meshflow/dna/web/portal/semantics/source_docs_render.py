"""Gold source-docs inspector — parallel to Semantic Builder, with overlay edits."""

from __future__ import annotations

import json
from html import escape
from typing import Any, Callable

from werkzeug.wrappers import Request, Response

from meshflow.dna.settings import DnaSettings
from meshflow.dna.source_docs.overlays import list_versions
from meshflow.dna.source_docs.reference import (
    list_reference_sources,
    load_source_docs_gold,
    normalize_reference_source,
    source_supports_gold_build,
)
from meshflow.dna.web.portal.dna_nav import (
    SOURCE_DOCS_INSPECTOR_ROOT,
    source_docs_inspector_path,
    source_label,
)
from meshflow.dna.web.theme import page_header


def _url(request: Request) -> Callable[[str], str]:
    return lambda path: f"{request.script_root}{path if path.startswith('/') else f'/{path}'}"


def _catalog_tables(catalog: dict[str, Any]) -> list[dict[str, Any]]:
    """Prefer `tables`; accept legacy `entities` for older gold files."""
    rows = catalog.get("tables")
    if rows is None:
        rows = catalog.get("entities")
    return [item for item in (rows or []) if isinstance(item, dict)]


def _table_name(row: dict[str, Any]) -> str:
    return str(row.get("silver_entity") or row.get("table") or "").strip()


def _action_btn(
    *,
    label: str,
    kind: str,
    attrs: dict[str, str],
    extra_class: str = "",
    aria_label: str = "",
) -> str:
    classes = "source-docs-edit-btn"
    if extra_class:
        classes += f" {extra_class}"
    data = " ".join(
        f'data-{escape(key)}="{escape(value)}"' for key, value in attrs.items() if value is not None
    )
    aria = f' aria-label="{escape(aria_label)}"' if aria_label else ""
    return (
        f'<button type="button" class="{classes}" data-action="exclude" '
        f'data-kind="{escape(kind)}" {data}{aria}>{escape(label)}</button>'
    )


def _source_switcher(
    *,
    sources: list[str],
    active_source: str,
    url: Callable[[str], str],
    availability: dict[str, bool],
) -> str:
    if len(sources) <= 1:
        label = source_label(active_source)
        return f"""
        <nav class="source-docs-source-nav" aria-label="Data sources">
          <a class="source-docs-source-chip is-active" href="{escape(url(source_docs_inspector_path(active_source)))}"
             aria-current="page">{escape(label)}</a>
        </nav>
        """
    chips = []
    for source in sources:
        active = " is-active" if source == active_source else ""
        current = ' aria-current="page"' if source == active_source else ""
        ready = availability.get(source)
        badge = ""
        if ready is True:
            badge = '<span class="source-docs-source-badge">Ready</span>'
        elif ready is False:
            badge = '<span class="source-docs-source-badge is-empty">Empty</span>'
        chips.append(
            f'<a class="source-docs-source-chip{active}" '
            f'href="{escape(url(source_docs_inspector_path(source)))}"{current}>'
            f"{escape(source_label(source))}{badge}</a>"
        )
    return (
        '<nav class="source-docs-source-nav" aria-label="Data sources">'
        + "".join(chips)
        + "</nav>"
    )


def _admin_nav(
    *,
    available: bool,
    is_admin: bool,
    build_supported: bool,
    source: str,
    pending_count: int = 0,
) -> str:
    if not is_admin or not build_supported:
        return ""
    items: list[str] = []
    if available:
        items.append(
            '<button type="button" class="semantic-builder-sub-nav-item '
            'semantic-builder-sub-nav-button semantic-builder-sub-nav-primary" '
            f'id="source-docs-rebuild-btn" data-source="{escape(source)}">'
            "Rebuild Semantic Model</button>"
        )
        disabled = " disabled" if pending_count <= 0 else ""
        items.append(
            '<button type="button" class="semantic-builder-sub-nav-item '
            'semantic-builder-sub-nav-button source-docs-submit-btn" '
            f'id="source-docs-submit-btn" data-source="{escape(source)}"{disabled}>'
            "Submit changes"
            f'<span class="source-docs-pending-count" id="source-docs-pending-count">'
            f"{pending_count}</span></button>"
        )
    if not items:
        return ""
    return (
        '<nav class="semantic-builder-sub-nav" id="source-docs-admin-nav" '
        'aria-label="Source docs actions">'
        + "".join(items)
        + "</nav>"
    )


def _summary_cards(summary: dict[str, Any], *, available: bool, complete: bool) -> str:
    if not available:
        return ""
    status = "Complete" if complete else "Partial"
    items = [
        ("Tables", summary.get("table_count") or 0),
        ("Columns", summary.get("property_count") or 0),
        ("Relationships", summary.get("relationship_count") or 0),
        ("Tagged columns", summary.get("tagged_property_count") or 0),
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


def _empty_state(*, is_admin: bool, source: str, build_supported: bool) -> str:
    label = source_label(source)
    action = ""
    if is_admin and build_supported:
        action = (
            '<p class="semantic-builder-landing-action">'
            '<button type="button" class="btn semantic-builder-start-btn" '
            f'id="source-docs-build-empty-btn" data-source="{escape(source)}">'
            "Build Semantic Model</button></p>"
        )
    elif not build_supported:
        action = (
            f'<p class="pack-card-lead semantic-builder-landing-hint">'
            f"Gold merge for {escape(label)} is not wired yet. This slot is ready for a "
            f"future {escape(source)} semantic reference.</p>"
        )
    return f"""
    <section class="section semantic-builder-landing">
      <div class="card pack-card">
        <p class="pack-card-lead">
          No gold source documentation is available yet for
          <strong>{escape(label)}</strong> (<code>{escape(source)}</code>).
          Each datasource keeps its own Semantic Reference under
          <code>governance/source_semantic_reference/{escape(source)}/gold/</code>.
        </p>
        {action}
        <p class="pack-card-lead semantic-builder-landing-hint">
          After the build finishes, this page shows tables, relationships, and
          conceptual tags. Admins can exclude items and submit for gold merge.
        </p>
      </div>
    </section>
    """


def _tables_panel(
    catalog: dict[str, Any] | None,
    *,
    is_admin: bool,
    pending_tables: set[str],
) -> str:
    if not catalog:
        return '<p class="semantic-builder-empty-state">entity_properties.yaml is not in gold yet.</p>'
    tables = _catalog_tables(catalog)
    if not tables:
        return '<p class="semantic-builder-empty-state">No tables in gold catalog.</p>'

    ranked = sorted(
        tables,
        key=lambda row: (
            -len([p for p in (row.get("properties") or []) if isinstance(p, dict)]),
            _table_name(row),
        ),
    )

    options = []
    sections: list[str] = []
    for table in ranked:
        silver = _table_name(table)
        if not silver:
            continue
        props = [p for p in (table.get("properties") or []) if isinstance(p, dict)]
        options.append(f'<option value="{escape(silver)}">{escape(silver)} ({len(props)})</option>')
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
        slug = str(table.get("bc_resource_slug") or "")
        url = str(table.get("ms_learn_url") or "")
        meta = []
        if slug:
            meta.append(f"slug <code>{escape(slug)}</code>")
        if url:
            meta.append(
                f'<a href="{escape(url)}" target="_blank" rel="noopener noreferrer">MS Learn</a>'
            )
        meta_html = f'<p class="pack-card-lead">{" · ".join(meta)}</p>' if meta else ""
        desc = str(table.get("description") or "")
        desc_html = f'<p class="pack-card-lead">{escape(desc)}</p>' if desc else ""
        edit = ""
        if is_admin:
            edit = _action_btn(
                label="Remove",
                kind="table",
                attrs={"table": silver},
            )
        sections.append(
            f"""
            <div class="source-docs-entity" data-table="{escape(silver)}">
              <div class="source-docs-entity-title">{escape(silver)}
                <span class="source-docs-count">{len(props)} columns</span>
                {edit}
              </div>
              {meta_html}{desc_html}
              <div class="table-wrap semantic-builder-scroll">
                <table class="semantic-builder-table semantic-builder-compact-table">
                  <thead><tr><th>Column</th><th>Type</th><th>Description</th></tr></thead>
                  <tbody>{''.join(rows) or '<tr><td colspan="3">No columns</td></tr>'}</tbody>
                </table>
              </div>
            </div>
            """
        )

    return f"""
    <div class="source-docs-filter-bar">
      <label for="source-docs-table-filter">Table</label>
      <select id="source-docs-table-filter" class="source-docs-select">
        <option value="">All tables ({len(ranked)})</option>
        {''.join(options)}
      </select>
    </div>
    <div id="source-docs-tables-list">
      {''.join(sections)}
    </div>
    """


def _relationships_panel(
    catalog: dict[str, Any] | None,
    *,
    is_admin: bool,
    pending_relationships: set[str],
) -> str:
    if not catalog:
        return (
            '<p class="semantic-builder-empty-state">'
            "entity_relationships.yaml is not in gold yet.</p>"
        )
    tables = catalog.get("tables") or {}
    if not isinstance(tables, dict) or not tables:
        return '<p class="semantic-builder-empty-state">No tables in gold relationships catalog.</p>'

    ranked: list[tuple[str, dict[str, Any], list[dict[str, Any]]]] = []
    for table_name, table in tables.items():
        if not isinstance(table, dict):
            continue
        rels = [r for r in (table.get("relationships") or []) if isinstance(r, dict)]
        ranked.append((str(table_name), table, rels))
    ranked.sort(key=lambda item: (-len(item[2]), item[0]))

    options: list[str] = []
    sections: list[str] = []
    for table_name, table, rels in ranked:
        options.append(
            f'<option value="{escape(table_name)}">{escape(table_name)} ({len(rels)})</option>'
        )
        pk = str(table.get("PK") or "")
        if not rels:
            body = '<p class="semantic-builder-empty-state">No foreign keys</p>'
        else:
            rows = []
            for rel in rels:
                fk = str(rel.get("FK") or "")
                target = str(rel.get("target") or "")
                edit = ""
                if is_admin:
                    edit = _action_btn(
                        label="Remove",
                        kind="relationship",
                        attrs={"table": table_name, "fk": fk, "target": target},
                    )
                rows.append(
                    "<tr>"
                    f"<td><code>{escape(fk)}</code></td>"
                    f"<td><code>{escape(target)}</code></td>"
                    f"<td><code>{escape(str(rel.get('PK') or pk))}</code></td>"
                    f'<td class="source-docs-edit-cell">{edit}</td>'
                    "</tr>"
                )
            body = f"""
              <div class="table-wrap semantic-builder-scroll">
                <table class="semantic-builder-table semantic-builder-compact-table">
                  <thead><tr><th>FK</th><th>Target table</th><th>Target PK</th>
                  {"<th></th>" if is_admin else ""}</tr></thead>
                  <tbody>{''.join(rows)}</tbody>
                </table>
              </div>
            """
        sections.append(
            f"""
            <div class="source-docs-entity" data-table="{escape(table_name)}">
              <div class="source-docs-entity-title">{escape(table_name)}
                <span class="source-docs-count">PK <code>{escape(pk) or '—'}</code> ·
                {len(rels)} relationship{'s' if len(rels) != 1 else ''}</span>
              </div>
              {body}
            </div>
            """
        )

    return f"""
    <div class="source-docs-filter-bar">
      <label for="source-docs-rel-table-filter">Table</label>
      <select id="source-docs-rel-table-filter" class="source-docs-select">
        <option value="">All tables ({len(ranked)})</option>
        {''.join(options)}
      </select>
      <span class="pack-card-lead">
        {int(catalog.get('relationship_count') or 0)} relationships
        (sorted by relationship count)
      </span>
    </div>
    <div id="source-docs-relationships-list">
      {''.join(sections)}
    </div>
    """

def _collect_all_tags(tables: list[dict[str, Any]]) -> list[str]:
    seen: set[str] = set()
    tags: list[str] = []
    for table in tables:
        for prop in table.get("properties") or []:
            if not isinstance(prop, dict):
                continue
            for raw in prop.get("tags") or []:
                tag = str(raw or "").strip()
                key = tag.casefold()
                if not tag or key in seen:
                    continue
                seen.add(key)
                tags.append(tag)
    tags.sort(key=str.casefold)
    return tags


def _tags_panel(
    catalog: dict[str, Any] | None,
    *,
    is_admin: bool,
    pending_tags: set[str],
) -> str:
    if not catalog:
        return (
            '<p class="semantic-builder-empty-state">'
            "entity_property_tags.yaml is not in gold yet.</p>"
        )
    tables = _catalog_tables(catalog)
    if not tables:
        return '<p class="semantic-builder-empty-state">No tables in gold tags catalog.</p>'

    ranked: list[tuple[dict[str, Any], int, list[tuple[str, list[str]]]]] = []
    for table in tables:
        rows: list[tuple[str, list[str]]] = []
        tag_hits = 0
        for prop in table.get("properties") or []:
            if not isinstance(prop, dict):
                continue
            name = str(prop.get("name") or "").strip()
            if not name:
                continue
            tags = [str(t).strip() for t in (prop.get("tags") or []) if str(t).strip()]
            tag_hits += len(tags)
            rows.append((name, tags))
        ranked.append((table, tag_hits, rows))
    ranked.sort(key=lambda item: (-item[1], _table_name(item[0])))

    all_tags = _collect_all_tags(tables)
    datalist = "".join(f'<option value="{escape(tag)}"></option>' for tag in all_tags)

    options: list[str] = []
    sections: list[str] = []
    for table, tag_hits, rows in ranked:
        silver = _table_name(table)
        if not silver:
            continue
        options.append(
            f'<option value="{escape(silver)}">{escape(silver)} ({tag_hits})</option>'
        )
        body_rows = []
        for name, tags in rows:
            chips = []
            for tag in tags:
                remove = ""
                if is_admin:
                    remove = _action_btn(
                        label="×",
                        kind="tag",
                        attrs={
                            "silver-entity": silver,
                            "name": name,
                            "tag": tag,
                        },
                        extra_class="source-docs-tag-remove",
                        aria_label=f"Remove tag {tag}",
                    )
                chips.append(
                    f'<span class="source-docs-tag" data-tag="{escape(tag.casefold())}">'
                    f"{escape(tag)}{remove}</span>"
                )
            tag_html = (
                "".join(chips) if chips else '<span class="semantic-builder-empty-state">—</span>'
            )
            tag_keys = " ".join(t.casefold() for t in tags)
            body_rows.append(
                f'<tr class="source-docs-tag-row" data-table="{escape(silver)}" '
                f'data-tags="{escape(tag_keys)}">'
                f"<td><code>{escape(name)}</code></td>"
                f'<td class="source-docs-tag-cell">{tag_html}</td>'
                "</tr>"
            )
        sections.append(
            f"""
            <div class="source-docs-entity source-docs-tag-table"
                 data-table="{escape(silver)}" data-tag-count="{tag_hits}">
              <div class="source-docs-entity-title">{escape(silver)}
                <span class="source-docs-count">{tag_hits} tag{'s' if tag_hits != 1 else ''}</span>
              </div>
              <div class="table-wrap semantic-builder-scroll">
                <table class="semantic-builder-table semantic-builder-compact-table">
                  <thead><tr><th>Column</th><th>Tags</th></tr></thead>
                  <tbody>{''.join(body_rows) or '<tr><td colspan="2">No columns</td></tr>'}</tbody>
                </table>
              </div>
            </div>
            """
        )

    return f"""
    <div class="source-docs-filter-bar source-docs-tag-search-bar">
      <label for="source-docs-tag-table-filter">Table</label>
      <select id="source-docs-tag-table-filter" class="source-docs-select">
        <option value="">All tables ({len(options)})</option>
        {''.join(options)}
      </select>
      <label for="source-docs-tag-search">Search tags</label>
      <input id="source-docs-tag-search" class="source-docs-tag-search"
             type="search" list="source-docs-tag-suggestions"
             placeholder="Filter by tag…" autocomplete="off" />
      <datalist id="source-docs-tag-suggestions">{datalist}</datalist>
      <span class="pack-card-lead" id="source-docs-tag-search-hint">
        {int(catalog.get('tagged_property_count') or 0)} tagged columns
        (sorted by tag count)
      </span>
    </div>
    <div id="source-docs-tags-list">
      {''.join(sections)}
    </div>
    """

def _version_history(
    *,
    is_admin: bool,
    versions_payload: dict[str, Any],
) -> str:
    versions = versions_payload.get("versions") or []
    active = versions_payload.get("active_version")
    pending_count = int(versions_payload.get("pending_count") or 0)
    rows = []
    if not versions:
        rows.append(
            '<tr><td colspan="4" class="semantic-builder-empty-state">'
            "No submitted versions yet. Submit overlay changes to create the first snapshot."
            "</td></tr>"
        )
    for entry in versions:
        if not isinstance(entry, dict):
            continue
        ver = entry.get("version")
        created = str(entry.get("created_at") or "")
        note = str(entry.get("note") or "")
        is_active = active is not None and int(ver) == int(active)
        badge = ' <span class="source-docs-version-active">Active</span>' if is_active else ""
        restore = ""
        if is_admin and not is_active:
            restore = (
                f'<button type="button" class="btn source-docs-restore-btn" '
                f'data-version="{escape(str(ver))}">Restore</button>'
            )
        rows.append(
            "<tr>"
            f"<td>v{escape(str(ver))}{badge}</td>"
            f"<td>{escape(created)}</td>"
            f"<td>{escape(note)}</td>"
            f"<td>{restore}</td>"
            "</tr>"
        )
    pending_note = (
        f'<p class="pack-card-lead" id="source-docs-version-pending-note">'
        f"{pending_count} pending change{'s' if pending_count != 1 else ''} not yet submitted.</p>"
        if pending_count
        else '<p class="pack-card-lead" id="source-docs-version-pending-note" hidden></p>'
    )
    return f"""
    <section class="section source-docs-versions" id="source-docs-versions">
      <h2 class="source-docs-versions-title">Version history</h2>
      {pending_note}
      <div class="table-wrap">
        <table class="semantic-builder-table semantic-builder-compact-table">
          <thead><tr><th>Version</th><th>Created</th><th>Note</th><th></th></tr></thead>
          <tbody id="source-docs-versions-body">{''.join(rows)}</tbody>
        </table>
      </div>
    </section>
    """


def _workspace(
    payload: dict[str, Any],
    *,
    is_admin: bool,
) -> str:
    empty: set[str] = set()
    return f"""
    <section class="section">
      <div class="semantic-builder-keys-tabs-section" id="source-docs-tabs" data-default-tab="tables">
        <div class="semantic-builder-keys-tabs" role="tablist" aria-label="Gold source docs">
          <button type="button" class="semantic-builder-keys-tab active" role="tab"
                  data-source-docs-tab="tables" aria-selected="true"
                  aria-controls="source-docs-panel-tables">Tables</button>
          <button type="button" class="semantic-builder-keys-tab" role="tab"
                  data-source-docs-tab="relationships" aria-selected="false"
                  aria-controls="source-docs-panel-relationships">Relationships</button>
          <button type="button" class="semantic-builder-keys-tab" role="tab"
                  data-source-docs-tab="tags" aria-selected="false"
                  aria-controls="source-docs-panel-tags">Tags</button>
        </div>
        <div class="semantic-builder-keys-panel" id="source-docs-panel-tables"
             data-source-docs-panel="tables" role="tabpanel">
          {_tables_panel(
              payload.get("entity_properties"),
              is_admin=is_admin,
              pending_tables=empty,
          )}
        </div>
        <div class="semantic-builder-keys-panel" id="source-docs-panel-relationships"
             data-source-docs-panel="relationships" role="tabpanel" hidden>
          {_relationships_panel(
              payload.get("entity_relationships"),
              is_admin=is_admin,
              pending_relationships=empty,
          )}
        </div>
        <div class="semantic-builder-keys-panel" id="source-docs-panel-tags"
             data-source-docs-panel="tags" role="tabpanel" hidden>
          {_tags_panel(
              payload.get("entity_property_tags"),
              is_admin=is_admin,
              pending_tags=empty,
          )}
        </div>
      </div>
    </section>
    """


def render_source_docs_inspector_content_html(
    settings: DnaSettings,
    *,
    is_admin: bool,
    source: str | None = None,
) -> str:
    payload = load_source_docs_gold(settings, source=source)
    connector = str(payload.get("source") or settings.source)
    if not payload.get("available"):
        return _empty_state(
            is_admin=is_admin,
            source=connector,
            build_supported=bool(payload.get("build_supported")),
        )
    versions_payload = list_versions(settings, source=connector)
    # Pending removes are tracked client-side until Submit; do not SSR server overlay pending.
    versions_payload = {**versions_payload, "pending_count": 0, "pending": []}
    return (
        _summary_cards(
            payload.get("summary") or {},
            available=True,
            complete=bool(payload.get("complete")),
        )
        + _workspace(payload, is_admin=is_admin)
        + _version_history(is_admin=is_admin, versions_payload=versions_payload)
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
.source-docs-submit-btn {
  background: rgba(56, 189, 248, 0.15); border-color: rgba(56, 189, 248, 0.45);
  color: #e0f2fe; font-weight: 600;
}
.source-docs-submit-btn:hover:not(:disabled) {
  background: rgba(56, 189, 248, 0.25); border-color: #38bdf8;
}
.source-docs-pending-count {
  display: inline-flex; min-width: 1.25rem; justify-content: center;
  padding: 0.05rem 0.35rem; border-radius: 999px; font-size: 0.72rem;
  background: rgba(15, 23, 42, 0.55); border: 1px solid rgba(148, 163, 184, 0.35);
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
.source-docs-select {
  min-width: min(16rem, 100%);
  padding: 0.45rem 0.65rem;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
  background: #07101f;
  color: var(--text);
  font: inherit;
  color-scheme: dark;
}
.source-docs-select option {
  background: #07101f;
  color: var(--text);
}
.source-docs-select:focus {
  outline: none;
  border-color: rgba(56, 189, 248, 0.45);
  box-shadow: 0 0 0 3px rgba(56, 189, 248, 0.12);
}
.source-docs-source-nav {
  display: flex; flex-wrap: wrap; gap: 0.5rem; align-items: center;
}
.source-docs-source-chip {
  display: inline-flex; align-items: center; gap: 0.4rem;
  padding: 0.5rem 0.85rem;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: rgba(8, 18, 40, 0.45);
  color: var(--text-muted);
  text-decoration: none;
  font-size: 0.86rem;
  font-weight: 500;
}
.source-docs-source-chip:hover {
  color: var(--text);
  border-color: rgba(56, 189, 248, 0.4);
}
.source-docs-source-chip.is-active {
  color: var(--text);
  border-color: #38bdf8;
  background: rgba(56, 189, 248, 0.1);
}
.source-docs-source-badge {
  font-size: 0.68rem;
  font-weight: 600;
  padding: 0.1rem 0.4rem;
  border-radius: 999px;
  border: 1px solid rgba(52, 211, 153, 0.45);
  background: rgba(52, 211, 153, 0.12);
  color: #6ee7b7;
}
.source-docs-source-badge.is-empty {
  border-color: rgba(148, 163, 184, 0.35);
  background: rgba(148, 163, 184, 0.1);
  color: var(--text-muted);
}
.source-docs-tag-search {
  min-width: min(18rem, 100%);
  padding: 0.45rem 0.65rem;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
  background: rgba(8, 18, 40, 0.95);
  color: var(--text);
  font: inherit;
}
.source-docs-tag-search:focus {
  outline: none;
  border-color: rgba(56, 189, 248, 0.45);
  box-shadow: 0 0 0 3px rgba(56, 189, 248, 0.12);
}
.source-docs-entity {
  margin-bottom: 1.25rem; padding-bottom: 1rem; border-bottom: 1px solid var(--border);
}
.source-docs-entity-title {
  font-weight: 600; margin-bottom: 0.35rem; display: flex; gap: 0.5rem; align-items: baseline;
  flex-wrap: wrap;
}
.source-docs-count { font-size: 0.78rem; color: var(--text-muted); font-weight: 500; }
.source-docs-tag {
  display: inline-flex; align-items: center; gap: 0.25rem;
  margin: 0.1rem 0.25rem 0.1rem 0;
  padding: 0.15rem 0.45rem; border-radius: 999px;
  border: 1px solid rgba(56, 189, 248, 0.35);
  background: rgba(56, 189, 248, 0.1); font-size: 0.75rem;
}
.source-docs-tag.is-match {
  border-color: rgba(52, 211, 153, 0.55);
  background: rgba(52, 211, 153, 0.18);
}
.source-docs-edit-btn {
  margin-left: 0.35rem;
  padding: 0.15rem 0.45rem;
  border-radius: var(--radius-sm);
  border: 1px solid rgba(248, 113, 113, 0.45);
  background: rgba(248, 113, 113, 0.12);
  color: #fecaca;
  font: inherit;
  font-size: 0.72rem;
  cursor: pointer;
}
.source-docs-edit-btn.is-pending {
  border-color: rgba(56, 189, 248, 0.45);
  background: rgba(56, 189, 248, 0.12);
  color: #bae6fd;
}
.source-docs-edit-btn:disabled { opacity: 0.55; cursor: not-allowed; }
.source-docs-tag-remove {
  margin-left: 0.2rem;
  padding: 0;
  border: none;
  background: transparent;
  color: inherit;
  font-size: 0.7rem;
  line-height: 1;
  font-weight: 500;
  opacity: 0.4;
  vertical-align: middle;
}
.source-docs-tag-remove:hover,
.source-docs-tag-remove:focus-visible {
  opacity: 0.85;
  background: transparent;
  border: none;
  color: inherit;
}
.source-docs-tag-remove.is-pending {
  opacity: 0.75;
  border: none;
  background: transparent;
  color: #7dd3fc;
}
.is-pending-remove {
  opacity: 0.62;
  text-decoration: line-through;
}
.source-docs-tag.is-pending-remove { text-decoration: line-through; }
.source-docs-tag.is-pending-remove .source-docs-tag-remove {
  text-decoration: none;
}
.source-docs-versions-title {
  font-size: 1.05rem; margin: 0 0 0.65rem; font-weight: 600;
}
.source-docs-version-active {
  margin-left: 0.35rem; font-size: 0.68rem; font-weight: 600;
  padding: 0.1rem 0.4rem; border-radius: 999px;
  border: 1px solid rgba(52, 211, 153, 0.45);
  background: rgba(52, 211, 153, 0.12); color: #6ee7b7;
}
.source-docs-restore-btn { font-size: 0.78rem; padding: 0.25rem 0.55rem; }
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


def _script(
    api_root: str,
    *,
    source: str,
    generated_at: str = "",
    artifact_generated_at: dict[str, str] | None = None,
) -> str:
    api = json.dumps(api_root)
    source_js = json.dumps(source)
    generated_js = json.dumps(generated_at)
    artifact_generated_js = json.dumps(artifact_generated_at or {})
    return f"""
<script>
(function () {{
  var apiRoot = {api};
  var activeSource = {source_js};
  var baselineGeneratedAt = {generated_js};
  var baselineArtifactGeneratedAt = {artifact_generated_js};
  var GOLD_ARTIFACTS = ["entity_properties", "entity_relationships", "entity_property_tags"];
  var statusEl = document.getElementById("source-docs-status");
  var pollTimer = null;
  var submitMode = false;
  var pendingQueue = [];

  function buildIsFresh(status) {{
    // Require all three gold catalogs (including tags) before treating rebuild/submit as done.
    if (!status.complete) return false;
    var times = ((status.summary || {{}}).artifact_generated_at) || {{}};
    var hasBaseline = GOLD_ARTIFACTS.some(function (key) {{
      return !!(baselineArtifactGeneratedAt && baselineArtifactGeneratedAt[key]);
    }});
    if (!hasBaseline) {{
      // First build: complete catalogs are enough.
      return true;
    }}
    // Rebuild/submit: every artifact must be rewritten (new generated_at), not just properties.
    return GOLD_ARTIFACTS.every(function (key) {{
      var next = times[key] || "";
      var prev = (baselineArtifactGeneratedAt && baselineArtifactGeneratedAt[key]) || "";
      return !!next && next !== prev;
    }});
  }}

  function storageKey() {{
    return "meshflow:source-docs-pending:" + activeSource;
  }}

  function loadPending() {{
    try {{
      var raw = sessionStorage.getItem(storageKey());
      var parsed = raw ? JSON.parse(raw) : [];
      pendingQueue = Array.isArray(parsed) ? parsed : [];
    }} catch (err) {{
      pendingQueue = [];
    }}
  }}

  function savePending() {{
    try {{
      sessionStorage.setItem(storageKey(), JSON.stringify(pendingQueue));
    }} catch (err) {{}}
  }}

  function clearPendingStorage() {{
    pendingQueue = [];
    try {{
      sessionStorage.removeItem(storageKey());
    }} catch (err) {{}}
  }}

  function itemKey(item) {{
    var kind = item.kind || "";
    if (kind === "table") return "table|" + (item.table || "");
    if (kind === "relationship") {{
      return "relationship|" + (item.table || "") + "|" + (item.FK || "") + "|" + (item.target || "");
    }}
    if (kind === "tag") {{
      return "tag|" + (item.silver_entity || "") + "|" + (item.name || "") + "|" + (item.tag || "");
    }}
    return kind + "|" + JSON.stringify(item);
  }}

  function findPendingIndex(item) {{
    var key = itemKey(item);
    for (var i = 0; i < pendingQueue.length; i++) {{
      if (itemKey(pendingQueue[i]) === key) return i;
    }}
    return -1;
  }}

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

  function setPendingCount(count) {{
    var el = document.getElementById("source-docs-pending-count");
    if (el) el.textContent = String(count || 0);
    var btn = document.getElementById("source-docs-submit-btn");
    if (btn) btn.disabled = !(count > 0);
    var note = document.getElementById("source-docs-version-pending-note");
    if (note) {{
      if (count > 0) {{
        note.hidden = false;
        note.textContent = count + " pending change" + (count === 1 ? "" : "s") + " not yet submitted.";
      }} else {{
        note.hidden = true;
        note.textContent = "";
      }}
    }}
  }}

  function markButtonPending(btn, pending) {{
    if (!btn) return;
    btn.classList.toggle("is-pending", !!pending);
    btn.setAttribute("data-action", pending ? "undo" : "exclude");
    if (btn.classList.contains("source-docs-tag-remove")) {{
      btn.textContent = "×";
    }} else {{
      btn.textContent = pending ? "Undo" : "Remove";
    }}
  }}

  function targetForItem(item) {{
    var kind = item.kind;
    if (kind === "table") {{
      var table = item.table || "";
      var entities = [];
      document.querySelectorAll("#source-docs-tables-list .source-docs-entity").forEach(function (el) {{
        if ((el.getAttribute("data-table") || "") === table) entities.push(el);
      }});
      return entities;
    }}
    if (kind === "relationship") {{
      var rows = [];
      document.querySelectorAll("#source-docs-relationships-list tr").forEach(function (tr) {{
        var btn = tr.querySelector('.source-docs-edit-btn[data-kind="relationship"]');
        if (!btn) return;
        if (
          (btn.getAttribute("data-table") || "") === (item.table || "") &&
          (btn.getAttribute("data-fk") || "") === (item.FK || "") &&
          (btn.getAttribute("data-target") || "") === (item.target || "")
        ) {{
          rows.push(tr);
        }}
      }});
      return rows;
    }}
    if (kind === "tag") {{
      var chips = [];
      document.querySelectorAll("#source-docs-tags-list .source-docs-tag").forEach(function (chip) {{
        var btn = chip.querySelector('.source-docs-edit-btn[data-kind="tag"]');
        if (!btn) return;
        if (
          (btn.getAttribute("data-silver-entity") || "") === (item.silver_entity || "") &&
          (btn.getAttribute("data-name") || "") === (item.name || "") &&
          (btn.getAttribute("data-tag") || "") === (item.tag || "")
        ) {{
          chips.push(chip);
        }}
      }});
      return chips;
    }}
    return [];
  }}

  function applyItemVisual(item, pending) {{
    targetForItem(item).forEach(function (node) {{
      node.classList.toggle("is-pending-remove", !!pending);
      var btn = null;
      if (item.kind === "table") {{
        btn = node.querySelector('.source-docs-edit-btn[data-kind="table"]');
      }} else if (item.kind === "relationship") {{
        btn = node.querySelector('.source-docs-edit-btn[data-kind="relationship"]');
      }} else if (item.kind === "tag") {{
        btn = node.querySelector('.source-docs-edit-btn[data-kind="tag"]');
      }}
      markButtonPending(btn, pending);
    }});
  }}

  function refreshPendingVisuals() {{
    document.querySelectorAll(".is-pending-remove").forEach(function (el) {{
      el.classList.remove("is-pending-remove");
    }});
    document.querySelectorAll(".source-docs-edit-btn.is-pending").forEach(function (btn) {{
      markButtonPending(btn, false);
    }});
    pendingQueue.forEach(function (item) {{
      applyItemVisual(item, true);
    }});
    setPendingCount(pendingQueue.length);
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

  function filterListByTable(selectId, listId) {{
    var select = document.getElementById(selectId);
    var list = document.getElementById(listId);
    if (!select || !list) return;
    var value = select.value || "";
    list.querySelectorAll(".source-docs-entity").forEach(function (el) {{
      var table = el.getAttribute("data-table") || "";
      el.hidden = !!(value && table !== value);
    }});
  }}

  function filterTables() {{
    filterListByTable("source-docs-table-filter", "source-docs-tables-list");
  }}

  function filterRelationships() {{
    filterListByTable("source-docs-rel-table-filter", "source-docs-relationships-list");
  }}

  function filterTags() {{
    var select = document.getElementById("source-docs-tag-table-filter");
    var input = document.getElementById("source-docs-tag-search");
    var list = document.getElementById("source-docs-tags-list");
    if (!list) return;
    var tableValue = select ? (select.value || "") : "";
    var query = input ? (input.value || "").trim().toLowerCase() : "";
    list.querySelectorAll(".source-docs-tag-table").forEach(function (section) {{
      var table = section.getAttribute("data-table") || "";
      if (tableValue && table !== tableValue) {{
        section.hidden = true;
        return;
      }}
      var rows = section.querySelectorAll(".source-docs-tag-row");
      var any = false;
      rows.forEach(function (row) {{
        var tags = (row.getAttribute("data-tags") || "");
        var match = !query || tags.indexOf(query) !== -1;
        row.hidden = !match;
        if (match) any = true;
        row.querySelectorAll(".source-docs-tag").forEach(function (chip) {{
          var tag = (chip.getAttribute("data-tag") || "");
          chip.classList.toggle("is-match", !!(query && tag.indexOf(query) !== -1));
        }});
      }});
      section.hidden = !any;
    }});
  }}

  function bindTabs() {{
    var section = document.getElementById("source-docs-tabs");
    if (!section) return;
    section.querySelectorAll("[data-source-docs-tab]").forEach(function (btn) {{
      btn.addEventListener("click", function () {{
        activateTab(btn.getAttribute("data-source-docs-tab") || "tables");
      }});
    }});
    activateTab(section.getAttribute("data-default-tab") || "tables");
  }}

  function bindFilters() {{
    var tableFilter = document.getElementById("source-docs-table-filter");
    if (tableFilter) tableFilter.addEventListener("change", filterTables);
    var relFilter = document.getElementById("source-docs-rel-table-filter");
    if (relFilter) relFilter.addEventListener("change", filterRelationships);
    var tagTableFilter = document.getElementById("source-docs-tag-table-filter");
    if (tagTableFilter) tagTableFilter.addEventListener("change", filterTags);
    var tagSearch = document.getElementById("source-docs-tag-search");
    if (tagSearch) {{
      tagSearch.addEventListener("input", filterTags);
      tagSearch.addEventListener("change", filterTags);
    }}
  }}

  function statusUrl() {{
    return apiRoot + "?source=" + encodeURIComponent(activeSource);
  }}

  async function fetchStatus() {{
    var response = await fetch(statusUrl(), {{ credentials: "same-origin" }});
    if (!response.ok) throw new Error("Status request failed (" + response.status + ")");
    return response.json();
  }}

  async function postJson(path, body) {{
    var response = await fetch(apiRoot + path, {{
      method: "POST",
      credentials: "same-origin",
      headers: {{ "Content-Type": "application/json" }},
      body: JSON.stringify(body || {{}})
    }});
    var payload = await response.json().catch(function () {{ return {{}}; }});
    if (!response.ok) {{
      throw new Error(payload.error || payload.message || ("Request failed (" + response.status + ")"));
    }}
    return payload;
  }}

  async function startBuild(source) {{
    activeSource = source || activeSource;
    submitMode = false;
    setStatus("Building semantic model for " + activeSource + "…");
    ["source-docs-rebuild-btn", "source-docs-build-empty-btn", "source-docs-submit-btn"].forEach(function (id) {{
      var btn = document.getElementById(id);
      if (btn) btn.disabled = true;
    }});
    try {{
      var payload = await postJson("/build", {{
        source: activeSource,
        seed_missing_overlays: true,
        publish_schemas: false
      }});
      if (payload.status === "published") {{
        setStatus("Semantic model ready. Reloading…");
        window.location.reload();
        return;
      }}
      setStatus("Semantic model build queued. Waiting for catalogs…");
      startPolling();
    }} catch (err) {{
      setStatus(String(err && err.message ? err.message : err), true);
      ["source-docs-rebuild-btn", "source-docs-build-empty-btn"].forEach(function (id) {{
        var btn = document.getElementById(id);
        if (btn) btn.disabled = false;
      }});
      setPendingCount(pendingQueue.length);
    }}
  }}

  async function commitVersion() {{
    await postJson("/versions/commit", {{ source: activeSource, note: "Submitted" }});
    clearPendingStorage();
    setStatus("Changes committed. Reloading…");
    window.location.reload();
  }}

  async function startSubmit(source) {{
    activeSource = source || activeSource;
    loadPending();
    if (!pendingQueue.length) {{
      setStatus("No pending changes to submit.", true);
      return;
    }}
    submitMode = true;
    setStatus("Submitting " + pendingQueue.length + " overlay change(s) for " + activeSource + "…");
    ["source-docs-rebuild-btn", "source-docs-submit-btn"].forEach(function (id) {{
      var btn = document.getElementById(id);
      if (btn) btn.disabled = true;
    }});
    try {{
      var payload = await postJson("/submit", {{
        source: activeSource,
        excludes: pendingQueue
      }});
      if (payload.status === "published") {{
        clearPendingStorage();
        setStatus("Changes submitted and versioned. Reloading…");
        window.location.reload();
        return;
      }}
      setStatus("Gold merge queued. Waiting to commit version…");
      startPolling();
    }} catch (err) {{
      setStatus(String(err && err.message ? err.message : err), true);
      var rebuild = document.getElementById("source-docs-rebuild-btn");
      if (rebuild) rebuild.disabled = false;
      setPendingCount(pendingQueue.length);
      submitMode = false;
    }}
  }}

  function startPolling() {{
    if (pollTimer) clearInterval(pollTimer);
    var attempts = 0;
    pollTimer = setInterval(async function () {{
      attempts += 1;
      try {{
        var status = await fetchStatus();
        if (buildIsFresh(status)) {{
          clearInterval(pollTimer);
          if (submitMode) {{
            setStatus("Gold updated. Committing version…");
            try {{
              await commitVersion();
            }} catch (err) {{
              setStatus(String(err && err.message ? err.message : err), true);
            }}
            return;
          }}
          setStatus("Semantic model ready. Reloading…");
          window.location.reload();
          return;
        }}
        if (attempts >= 40) {{
          clearInterval(pollTimer);
          setStatus("Build is still running. Refresh this page in a minute.", true);
        }} else if (status.available && !status.complete) {{
          setStatus("Waiting for tags catalog to finish merging…");
        }} else if (baselineGeneratedAt || Object.keys(baselineArtifactGeneratedAt || {{}}).length) {{
          setStatus("Merging catalogs (tables, relationships, tags)…");
        }}
      }} catch (err) {{
        if (attempts >= 5) {{
          clearInterval(pollTimer);
          setStatus(String(err && err.message ? err.message : err), true);
        }}
      }}
    }}, 3000);
  }}

  function itemFromButton(btn) {{
    var kind = btn.getAttribute("data-kind") || "";
    if (kind === "table") {{
      return {{ kind: "table", table: btn.getAttribute("data-table") || "" }};
    }}
    if (kind === "relationship") {{
      return {{
        kind: "relationship",
        table: btn.getAttribute("data-table") || "",
        FK: btn.getAttribute("data-fk") || "",
        target: btn.getAttribute("data-target") || ""
      }};
    }}
    if (kind === "tag") {{
      var tag = btn.getAttribute("data-tag") || "";
      return {{
        kind: "tag",
        silver_entity: btn.getAttribute("data-silver-entity") || "",
        name: btn.getAttribute("data-name") || "",
        tag: tag,
        tags: [tag]
      }};
    }}
    return null;
  }}

  function handleExcludeClick(btn) {{
    var item = itemFromButton(btn);
    if (!item) return;
    var idx = findPendingIndex(item);
    if (idx >= 0) {{
      pendingQueue.splice(idx, 1);
      applyItemVisual(item, false);
      setStatus("Pending remove undone. Submit when ready.");
    }} else {{
      pendingQueue.push(item);
      applyItemVisual(item, true);
      setStatus("Marked for removal. Submit when ready.");
    }}
    savePending();
    setPendingCount(pendingQueue.length);
  }}

  async function handleRestore(btn) {{
    var version = btn.getAttribute("data-version");
    if (!version) return;
    if (!window.confirm("Restore version v" + version + "? This rewrites overlays and gold.")) {{
      return;
    }}
    btn.disabled = true;
    try {{
      await postJson("/restore", {{ source: activeSource, version: parseInt(version, 10) }});
      clearPendingStorage();
      setStatus("Restored version v" + version + ". Reloading…");
      window.location.reload();
    }} catch (err) {{
      btn.disabled = false;
      setStatus(String(err && err.message ? err.message : err), true);
    }}
  }}

  document.addEventListener("click", function (event) {{
    var target = event.target;
    if (!target) return;
    var editBtn = target.closest ? target.closest(".source-docs-edit-btn") : null;
    if (editBtn) {{
      handleExcludeClick(editBtn);
      return;
    }}
    var restoreBtn = target.closest ? target.closest(".source-docs-restore-btn") : null;
    if (restoreBtn) {{
      handleRestore(restoreBtn);
      return;
    }}
    if (!target.id) return;
    if (target.id === "source-docs-rebuild-btn" || target.id === "source-docs-build-empty-btn") {{
      startBuild(target.getAttribute("data-source") || activeSource);
    }} else if (target.id === "source-docs-submit-btn") {{
      startSubmit(target.getAttribute("data-source") || activeSource);
    }}
  }});

  loadPending();
  refreshPendingVisuals();
  bindTabs();
  bindFilters();
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
    source: str | None = None,
    configured_sources: list[str] | None = None,
) -> Response:
    url = _url(request)
    sources = list_reference_sources(settings, configured=configured_sources)
    active = normalize_reference_source(source or "") or (sources[0] if sources else settings.source)
    if active not in sources:
        sources = [active, *[s for s in sources if s != active]]

    availability = {
        key: bool(load_source_docs_gold(settings, source=key).get("available")) for key in sources
    }
    payload = load_source_docs_gold(settings, source=active)
    available = bool(payload.get("available"))
    build_supported = bool(payload.get("build_supported", source_supports_gold_build(active)))
    api_root = url("/api/source-docs-gold")
    label = source_label(active)
    summary = payload.get("summary") or {}
    generated_at = str(summary.get("generated_at") or "")
    artifact_generated_at = summary.get("artifact_generated_at") or {}
    if not isinstance(artifact_generated_at, dict):
        artifact_generated_at = {}

    body = f"""
    <div class="source-docs-page semantic-builder-page" data-source="{escape(active)}">
      {page_header(
          "Source Browser",
          f"Inspect and customize gold tables, relationships, and tags per datasource. Viewing {label}.",
      )}
      {_source_switcher(
          sources=sources,
          active_source=active,
          url=url,
          availability=availability,
      )}
      {_admin_nav(
          available=available,
          is_admin=is_admin,
          build_supported=build_supported,
          source=active,
          pending_count=0,
      )}
    """
    if message:
        body += f'<div class="form-success">{escape(message)}</div>'
    if error:
        body += f'<div class="form-error">{escape(error)}</div>'
    body += """
      <div id="source-docs-status" class="source-docs-status" hidden></div>
      <div id="source-docs-content">
    """
    body += render_source_docs_inspector_content_html(
        settings,
        is_admin=is_admin,
        source=active,
    )
    body += "</div>"
    body += _styles()
    body += _script(
        api_root,
        source=active,
        generated_at=generated_at,
        artifact_generated_at={
            str(k): str(v or "") for k, v in artifact_generated_at.items() if str(k).strip()
        },
    )
    body += "</div>"

    return html_response(
        request,
        client=client,
        title=f"Source Browser — {label}",
        active_path=SOURCE_DOCS_INSPECTOR_ROOT,
        body=body,
        is_admin=is_admin,
        settings=settings,
    )
