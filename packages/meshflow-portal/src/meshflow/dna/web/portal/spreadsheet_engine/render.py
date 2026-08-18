"""Spreadsheet Engine Source Browser UI — aligned with DNA Engine layout."""

from __future__ import annotations

import json
from html import escape
from typing import Any, Callable

from meshflow.dna.source_docs.reference import normalize_reference_source
from meshflow.dna.web.portal.dna_nav import source_docs_inspector_path
from meshflow.dna.web.portal.semantics.source_docs_render import _source_switcher, _styles as _source_docs_styles
from meshflow.dna.web.portal.spreadsheet_engine.service import spreadsheet_pipeline_progress

_IN_FLIGHT_JOB_STATUSES = frozenset(
    {
        "uploaded",
        "running",
        "parsing",
        "parsed",
        "profiling",
        "profiled",
        "interpreting",
        "interpreted",
        "proposing",
    }
)


def _json_for_script(payload: Any) -> str:
    return json.dumps(payload).replace("<", "\\u003c")


def _proposal_url(
    url: Callable[[str], str],
    *,
    source: str,
    job_id: str,
    table_index: int = 0,
) -> str:
    return url(
        f"{source_docs_inspector_path(source)}"
        f"?job_id={job_id}&tab=review&table_index={table_index}"
    )


def _catalog_url(
    url: Callable[[str], str],
    *,
    source: str,
    catalog_id: str = "",
) -> str:
    path = f"{source_docs_inspector_path(source)}?tab=catalog"
    if catalog_id:
        path += f"&catalog_id={catalog_id}"
    return url(path)


def _chat_html(
    table: dict[str, Any] | None,
    *,
    analyzing: bool = False,
    entity_name: str = "",
) -> str:
    history = list((table or {}).get("chat_history") or [])
    html = ""
    for entry in history:
        role = str(entry.get("role") or "user").strip().lower()
        text = str(entry.get("text") or "").strip()
        if not text:
            continue
        label = "You" if role == "user" else "Assistant"
        css = "assistant-bubble user" if role == "user" else "assistant-bubble"
        html += (
            f'<div class="{css}">'
            f'<div class="assistant-bubble-label">{escape(label)}</div>'
            f'<div class="assistant-bubble-text">{escape(text)}</div>'
            "</div>"
        )
    if analyzing:
        html += (
            '<div class="assistant-bubble" id="spreadsheet-job-running">'
            '<div class="assistant-bubble-label">Assistant</div>'
            '<div class="assistant-bubble-text">Analyzing workbook — parsing sheets, profiling columns, and drafting schema proposals…</div>'
            "</div>"
        )
    if html:
        return html
    label = entity_name or "this table"
    return (
        '<p class="pack-card-lead">'
        f"Ask the assistant to refine grain, column names, types, or relationships for {escape(label)}."
        "</p>"
    )


def _schema_table_html(schema: list[dict[str, Any]]) -> str:
    rows = ""
    for col in schema:
        if not isinstance(col, dict):
            continue
        flags = []
        if col.get("is_key"):
            flags.append("key")
        if col.get("is_foreign_key"):
            flags.append("fk")
        if col.get("nullable"):
            flags.append("nullable")
        flag_text = ", ".join(flags) if flags else "—"
        rows += (
            "<tr>"
            f"<td><code>{escape(str(col.get('name') or ''))}</code></td>"
            f"<td>{escape(str(col.get('type') or ''))}</td>"
            f"<td>{escape(str(col.get('description') or ''))}</td>"
            f"<td>{escape(flag_text)}</td>"
            "</tr>"
        )
    if not rows:
        return '<p class="muted">No schema columns proposed.</p>'
    return (
        '<table class="semantic-builder-table">'
        "<thead><tr><th>Column</th><th>Type</th><th>Description</th><th>Flags</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
    )


def _profiling_table_html(profiling: dict[str, Any]) -> str:
    columns = profiling.get("columns") or []
    if not columns:
        return ""
    rows = ""
    for col in columns:
        if not isinstance(col, dict):
            continue
        rows += (
            "<tr>"
            f"<td><code>{escape(str(col.get('name') or ''))}</code></td>"
            f"<td>{escape(str(col.get('inferred_type') or ''))}</td>"
            f"<td>{float(col.get('null_rate') or 0):.0%}</td>"
            f"<td>{int(col.get('cardinality') or 0)}</td>"
            f"<td>{'yes' if col.get('likely_key') else ''}</td>"
            f"<td>{escape(', '.join(col.get('patterns') or []) or '—')}</td>"
            "</tr>"
        )
    return (
        '<table class="semantic-builder-table">'
        "<thead><tr><th>Column</th><th>Type</th><th>Null %</th><th>Cardinality</th><th>Key?</th><th>Patterns</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
    )


def _schema_profiling_panel_html(schema: list[dict[str, Any]], profiling: dict[str, Any]) -> str:
    schema_table = _schema_table_html(schema)
    profiling_table = _profiling_table_html(profiling)
    if not profiling_table:
        return f"""
        <div class="spreadsheet-schema-toggle">
          <h3 class="kpi-section-heading">Proposed schema</h3>
          <div class="spreadsheet-schema-panel-wrap semantic-builder-scroll table-wrap">
            {schema_table}
          </div>
        </div>
        """
    return f"""
    <div class="spreadsheet-schema-toggle" id="spreadsheet-schema-toggle">
      <div class="spreadsheet-schema-toggle-head">
        <h3 class="kpi-section-heading">Schema details</h3>
        <div class="spreadsheet-schema-tabs" role="tablist" aria-label="Schema details">
          <button type="button" class="spreadsheet-schema-tab active" role="tab"
            data-spreadsheet-schema-tab="schema" aria-selected="true"
            aria-controls="spreadsheet-schema-panel-schema">Proposed schema</button>
          <button type="button" class="spreadsheet-schema-tab" role="tab"
            data-spreadsheet-schema-tab="profiling" aria-selected="false"
            aria-controls="spreadsheet-schema-panel-profiling">Column profiling</button>
        </div>
      </div>
      <div class="spreadsheet-schema-panel-wrap semantic-builder-scroll table-wrap">
        <div class="spreadsheet-schema-panel" id="spreadsheet-schema-panel-schema"
             data-spreadsheet-schema-panel="schema" role="tabpanel">
          {schema_table}
        </div>
        <div class="spreadsheet-schema-panel" id="spreadsheet-schema-panel-profiling"
             data-spreadsheet-schema-panel="profiling" role="tabpanel" hidden>
          {profiling_table}
        </div>
      </div>
    </div>
    """


def _relationships_html(relationships: list[dict[str, Any]]) -> str:
    items = []
    for rel in relationships:
        if not isinstance(rel, dict):
            continue
        entity = str(rel.get("to_entity") or "").strip()
        column = str(rel.get("via_column") or "").strip()
        if not entity or not column:
            continue
        confidence = float(rel.get("confidence") or 0)
        items.append(
            "<li>"
            f"<span class=\"spreadsheet-relationship-entity\">{escape(entity)}</span>"
            f" via <code>{escape(column)}</code>"
            f"<span class=\"spreadsheet-relationship-confidence\">{confidence:.0%}</span>"
            "</li>"
        )
    if not items:
        return ""
    return f"""
    <section class="spreadsheet-meta-block">
      <h3 class="kpi-section-heading">Relationships</h3>
      <ul class="spreadsheet-relationship-list">{"".join(items)}</ul>
    </section>
    """


def _notes_html(notes: list[Any]) -> str:
    items: list[str] = []
    for note in notes:
        text = str(note or "").strip()
        if not text:
            continue
        if "heuristic fallback" in text.lower():
            items.append("Schema inferred locally because AI interpretation was unavailable.")
            continue
        items.append(text)
    if not items:
        return ""
    if len(items) == 1:
        body = f'<p class="spreadsheet-notes-copy">{escape(items[0])}</p>'
    else:
        body = (
            '<ul class="spreadsheet-notes-list">'
            + "".join(f"<li>{escape(item)}</li>" for item in items)
            + "</ul>"
        )
    return f"""
    <div class="spreadsheet-notes">
      <h3 class="kpi-section-heading">Notes</h3>
      {body}
    </div>
    """


def _transformation_steps_html(transformation: dict[str, Any]) -> str:
    steps = transformation.get("steps") or []
    if not steps:
        return '<p class="muted">No transformation steps.</p>'
    items = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        op = escape(str(step.get("op") or ""))
        detail = escape(json.dumps({k: v for k, v in step.items() if k != "op"}, default=str))
        items.append(f'<li><code>{op}</code> <span class="muted">{detail}</span></li>')
    return f'<ul class="spreadsheet-transform-steps">{"".join(items)}</ul>'


def _transform_preview_diff_html(transform_preview: dict[str, Any] | None) -> str:
    if not transform_preview:
        return ""
    before = transform_preview.get("before") or {}
    after = transform_preview.get("after") or {}
    if not before.get("rows") and not after.get("rows"):
        return ""
    before_html = _preview_html(before)
    after_html = _preview_html(after)
    if not before_html and not after_html:
        return ""
    return f"""
    <div class="spreadsheet-transform-diff">
      <div class="spreadsheet-transform-diff-col">
        <h4 class="kpi-section-heading">Before (raw)</h4>
        {before_html or '<p class="muted">No preview.</p>'}
      </div>
      <div class="spreadsheet-transform-diff-col">
        <h4 class="kpi-section-heading">After (transformed)</h4>
        {after_html or '<p class="muted">No preview.</p>'}
      </div>
    </div>
    """


def _transformation_panel_html(
    table: dict[str, Any],
    *,
    job_id: str = "",
    table_index: int = 0,
    url: Callable[[str], str] | None = None,
    source: str = "",
    readonly: bool = False,
    transform_preview: dict[str, Any] | None = None,
) -> str:
    transformation = table.get("transformation") or {}
    steps = transformation.get("steps") or []
    if not steps and readonly:
        return ""
    status = str(table.get("transformation_status") or "pending_review")
    drift = list(table.get("transformation_drift") or [])
    notes = list(table.get("transformation_notes") or [])
    confidence = float(table.get("transformation_confidence") or 0)
    drift_html = ""
    if drift:
        drift_html = '<ul class="spreadsheet-transform-drift">' + "".join(
            f"<li>{escape(item)}</li>" for item in drift
        ) + "</ul>"
    notes_html = ""
    if notes:
        notes_html = "<ul>" + "".join(f"<li>{escape(n)}</li>" for n in notes) + "</ul>"
    actions = ""
    if not readonly and url and job_id and steps:
        table_id = str(table.get("table_id") or "")
        actions = f"""
        <div class="spreadsheet-transform-actions">
          <form method="post" class="assistant-approve-form">
            <input type="hidden" name="action" value="approve_transformation" />
            <input type="hidden" name="job_id" value="{escape(job_id)}" />
            <input type="hidden" name="table_id" value="{escape(table_id)}" />
            <input type="hidden" name="table_index" value="{table_index}" />
            <button type="submit" class="btn btn-primary"{" disabled" if status == "approved" else ""}>Approve transformation</button>
          </form>
          <form method="post" class="spreadsheet-transform-reject-form">
            <input type="hidden" name="action" value="reject_transformation" />
            <input type="hidden" name="job_id" value="{escape(job_id)}" />
            <input type="hidden" name="table_id" value="{escape(table_id)}" />
            <input type="hidden" name="table_index" value="{table_index}" />
            <input type="text" name="reason" placeholder="Rejection reason (optional)" class="spreadsheet-transform-reason" />
            <button type="submit" class="btn btn-secondary">Reject &amp; re-propose</button>
          </form>
        </div>
        <form method="post" class="spreadsheet-transform-edit-form">
          <input type="hidden" name="action" value="edit_transformation" />
          <input type="hidden" name="job_id" value="{escape(job_id)}" />
          <input type="hidden" name="table_id" value="{escape(table_id)}" />
          <input type="hidden" name="table_index" value="{table_index}" />
          <label for="spreadsheet-transform-json">Edit transformation JSON</label>
          <textarea id="spreadsheet-transform-json" name="transformation_json" rows="6" class="spreadsheet-transform-json">{escape(json.dumps(transformation, indent=2, default=str))}</textarea>
          <button type="submit" class="btn btn-secondary">Save edits for review</button>
        </form>
        """
    status_chip = f'<span class="kpi-chip">{escape(status.replace("_", " "))}</span>'
    if confidence:
        status_chip += f' <span class="muted">Confidence {confidence:.0%}</span>'
    preview_block = _transform_preview_diff_html(
        (transform_preview or {}).get("transformation_preview")
        if isinstance(transform_preview, dict) and transform_preview.get("transformation_preview")
        else transform_preview
    )
    return f"""
    <section class="spreadsheet-transform-panel">
      <div class="spreadsheet-transform-head">
        <h3 class="kpi-section-heading">Transformation</h3>
        {status_chip}
      </div>
      {drift_html}
      {notes_html}
      {_transformation_steps_html(transformation)}
      {preview_block}
      {actions}
    </section>
    """


def _preview_html(preview: dict[str, Any] | None) -> str:
    if not preview:
        return ""
    headers = [str(name) for name in (preview.get("headers") or []) if str(name).strip()]
    rows = preview.get("rows") or []
    if not headers and not rows:
        return ""
    header_cells = "".join(f"<th>{escape(name)}</th>" for name in headers)
    body_rows = ""
    for row in rows:
        if not isinstance(row, list):
            continue
        cells = ""
        width = len(headers) if headers else len(row)
        for idx in range(width):
            value = row[idx] if idx < len(row) else ""
            if value is None:
                text = ""
            else:
                text = str(value)
            cells += f"<td>{escape(text)}</td>"
        body_rows += f"<tr>{cells}</tr>"
    if not body_rows:
        return ""
    total_rows = int(preview.get("row_count") or 0)
    shown = int(preview.get("preview_row_count") or len(rows))
    note = f"Showing {shown} of {total_rows} data rows."
    if preview.get("truncated"):
        note += " Preview is limited to 100 rows."
    return f"""
    <h3 class="kpi-section-heading">Data preview</h3>
    <p class="muted spreadsheet-preview-note">{escape(note)}</p>
    <div class="semantic-builder-scroll table-wrap spreadsheet-preview-table">
      <table class="semantic-builder-table">
        <thead><tr>{header_cells}</tr></thead>
        <tbody>{body_rows}</tbody>
      </table>
    </div>
    """


def _schema_toggle_script() -> str:
    return """
<script>
(function () {
  var root = document.getElementById("spreadsheet-schema-toggle");
  if (!root) return;
  var tabs = root.querySelectorAll("[data-spreadsheet-schema-tab]");
  var panels = root.querySelectorAll("[data-spreadsheet-schema-panel]");
  function activate(name) {
    tabs.forEach(function (tab) {
      var active = tab.getAttribute("data-spreadsheet-schema-tab") === name;
      tab.classList.toggle("active", active);
      tab.setAttribute("aria-selected", active ? "true" : "false");
    });
    panels.forEach(function (panel) {
      var active = panel.getAttribute("data-spreadsheet-schema-panel") === name;
      panel.hidden = !active;
    });
  }
  tabs.forEach(function (tab) {
    tab.addEventListener("click", function () {
      activate(tab.getAttribute("data-spreadsheet-schema-tab") || "schema");
    });
  });
})();
</script>
"""


def _stats_html(table: dict[str, Any]) -> str:
    source = table.get("source") or {}
    items = [
        ("Grain", str(table.get("grain") or "—")),
        ("Sheet", str(source.get("sheet") or "—")),
        ("Rows", str(int(source.get("row_count") or 0))),
        ("Confidence", f"{float(table.get('confidence') or 0):.0%}"),
    ]
    cards = "".join(
        f'<div class="source-docs-stat"><span class="source-docs-stat-label">{escape(label)}</span>'
        f'<strong class="source-docs-stat-value">{escape(value)}</strong></div>'
        for label, value in items
    )
    return f'<div class="source-docs-summary">{cards}</div>'


def _reload_validation_html(
    table: dict[str, Any],
    *,
    job_id: str = "",
    table_index: int = 0,
    url: Callable[[str], str] | None = None,
    source: str = "",
) -> str:
    if not table.get("reload_mode"):
        return ""
    status = str(table.get("reload_validation_status") or "")
    issues = list(table.get("reload_validation_issues") or [])
    linked = str(table.get("linked_catalog_id") or table.get("reused_from_catalog_id") or "")
    table_id = str(table.get("table_id") or "")

    if status == "passed":
        return f"""
        <section class="spreadsheet-reload-validation is-passed">
          <h3 class="kpi-section-heading">Reload validation passed</h3>
          <p class="muted">Transformed output matches the approved schema for <code>{escape(linked)}</code>. No AI analysis was run.</p>
          <form method="post" class="assistant-approve-form">
            <input type="hidden" name="action" value="complete_reload" />
            <input type="hidden" name="job_id" value="{escape(job_id)}" />
            <input type="hidden" name="table_id" value="{escape(table_id)}" />
            <input type="hidden" name="table_index" value="{table_index}" />
            <button type="submit" class="btn btn-primary">Complete reload</button>
          </form>
        </section>
        """

    issue_html = ""
    if issues:
        issue_html = "<ul class=\"spreadsheet-reload-validation-issues\">" + "".join(
            f"<li>{escape(item)}</li>" for item in issues
        ) + "</ul>"

    recovery = ""
    if url and job_id and source:
        analyze_href = escape(url(f"{source_docs_inspector_path(source)}?tab=analyze"))
        recovery = f"""
        <div class="spreadsheet-reload-recovery">
          <p class="pack-card-lead">Choose how to proceed:</p>
          <div class="spreadsheet-reload-recovery-actions">
            <a class="btn btn-secondary" href="{analyze_href}">Upload a different file</a>
            <form method="post" class="spreadsheet-reload-recovery-form">
              <input type="hidden" name="action" value="request_schema_rewrite" />
              <input type="hidden" name="job_id" value="{escape(job_id)}" />
              <input type="hidden" name="table_index" value="{table_index}" />
              <button type="submit" class="btn btn-secondary">Rewrite schema with AI</button>
            </form>
            <form method="post" class="spreadsheet-reload-recovery-form">
              <input type="hidden" name="action" value="request_transformation_rewrite" />
              <input type="hidden" name="job_id" value="{escape(job_id)}" />
              <input type="hidden" name="table_index" value="{table_index}" />
              <button type="submit" class="btn btn-secondary">Propose new transformation with AI</button>
            </form>
          </div>
        </div>
        """

    return f"""
    <section class="spreadsheet-reload-validation is-failed">
      <h3 class="kpi-section-heading">Reload validation failed</h3>
      <p class="muted">The new file does not match the approved schema for <code>{escape(linked)}</code>. No AI analysis was run.</p>
      {issue_html}
      {recovery}
    </section>
    """


def _table_analysis_html(
    table: dict[str, Any],
    *,
    job_id: str = "",
    table_index: int = 0,
    total: int = 1,
    url: Callable[[str], str] | None = None,
    source: str = "",
    readonly: bool = False,
    catalog_meta: dict[str, Any] | None = None,
    embedded: bool = False,
    table_preview: dict[str, Any] | None = None,
    transform_preview: dict[str, Any] | None = None,
) -> str:
    status = str(table.get("status") or "pending_review")
    status_label = status.replace("_", " ").title()
    schema = table.get("schema") or []
    profiling = table.get("profiling") or {}
    relationships = table.get("relationships") or []
    notes = table.get("notes") or []
    approve_btn = ""
    reload_mode = bool(table.get("reload_mode"))
    reload_validation = str(table.get("reload_validation_status") or "")
    if readonly:
        meta = catalog_meta or {}
        approved_at = str(meta.get("approved_at") or table.get("approved_at") or "")
        approved_by = str(meta.get("approved_by") or table.get("approved_by") or "")
        workbook = str(meta.get("filename") or "")
        details = []
        if workbook:
            details.append(f"Workbook: {escape(workbook)}")
        if approved_at:
            details.append(f"Approved {escape(approved_at)}")
        if approved_by:
            details.append(f"by {escape(approved_by)}")
        detail_text = " · ".join(details) if details else "Approved proposal"
        approve_btn = f'<p class="muted">{detail_text}</p>'
    elif reload_mode and reload_validation == "passed":
        approve_btn = ""
    elif reload_mode and reload_validation == "failed":
        approve_btn = ""
    elif status != "approved":
        transformation = table.get("transformation") or {}
        steps = transformation.get("steps") or []
        transform_status = str(table.get("transformation_status") or "")
        can_approve_table = not steps or transform_status == "approved"
        approve_btn = f"""
        <form method="post" class="assistant-approve-form">
          <input type="hidden" name="action" value="approve_table" />
          <input type="hidden" name="job_id" value="{escape(job_id)}" />
          <input type="hidden" name="table_id" value="{escape(str(table.get('table_id') or ''))}" />
          <input type="hidden" name="table_index" value="{table_index}" />
          <button type="submit" class="btn btn-primary"{" disabled" if not can_approve_table else ""}>Approve table</button>
        </form>
        """
        if not can_approve_table:
            approve_btn += '<p class="muted">Approve the transformation before approving the table.</p>'
    else:
        approve_btn = '<p class="muted">This table proposal is approved.</p>'

    prev_href = next_href = ""
    nav = ""
    if not readonly and url and job_id:
        if table_index > 0:
            prev_href = _proposal_url(url, source=source, job_id=job_id, table_index=table_index - 1)
        if table_index < total - 1:
            next_href = _proposal_url(url, source=source, job_id=job_id, table_index=table_index + 1)
        nav = '<div class="assistant-diff-nav">'
        nav += f'<span class="assistant-diff-nav-label">Table {table_index + 1} of {total}</span>'
        if prev_href:
            nav += f'<a class="btn btn-secondary assistant-diff-nav-btn" href="{escape(prev_href)}">Previous</a>'
        if next_href:
            nav += f'<a class="btn btn-secondary assistant-diff-nav-btn" href="{escape(next_href)}">Next</a>'
        nav += f'<span class="kpi-chip">{escape(status_label)}</span></div>'

    inner = f"""
      {_reload_validation_html(table, job_id=job_id, table_index=table_index, url=url, source=source)}
      <p class="pack-card-lead">{escape(str(table.get('purpose') or ''))}</p>
      {_stats_html(table)}
      {_preview_html(table_preview)}
      {_transformation_panel_html(
          table,
          job_id=job_id,
          table_index=table_index,
          url=url,
          source=source,
          readonly=readonly or reload_mode,
          transform_preview=transform_preview,
      )}
      {_schema_profiling_panel_html(schema, profiling)}
      {_relationships_html(relationships)}
      {_notes_html(notes)}
      {approve_btn}
    """
    if embedded:
        return inner
    return f"""
    <section class="card pack-card" id="spreadsheet-table-analysis">
      {nav}
      <h2>{escape(str(table.get('entity_name') or table.get('table_id') or 'Proposed table'))}</h2>
      {inner}
    </section>
    """


def _table_pager_html(
    *,
    job_id: str,
    tables: list[dict[str, Any]],
    table_index: int,
    url: Callable[[str], str],
    source: str,
) -> str:
    if not tables:
        return ""
    chips = []
    for idx, table in enumerate(tables):
        active = " is-active" if idx == table_index else ""
        label = str(table.get("entity_name") or table.get("table_id") or f"Table {idx + 1}")
        status = str(table.get("status") or "")
        badge = ""
        if status == "approved":
            badge = '<span class="source-docs-source-badge">Approved</span>'
        elif status == "pending_review":
            badge = '<span class="source-docs-source-badge is-empty">Review</span>'
        href = _proposal_url(url, source=source, job_id=job_id, table_index=idx)
        chips.append(
            f'<a class="source-docs-source-chip{active}" href="{escape(href)}">'
            f"{escape(label)}{badge}</a>"
        )
    return (
        '<nav class="source-docs-source-nav" aria-label="Proposed tables">'
        + "".join(chips)
        + "</nav>"
    )


def _tabs_html(*, active_tab: str, review_count: int, catalog_count: int) -> str:
    analyze_active = active_tab == "analyze"
    review_active = active_tab == "review"
    catalog_active = active_tab == "catalog"
    review_label = f"Proposals ({review_count})" if review_count else "Proposals"
    catalog_label = f"Catalog ({catalog_count})" if catalog_count else "Catalog"
    return f"""
    <div class="semantic-builder-keys-tabs" role="tablist" aria-label="Spreadsheet Engine">
      <button type="button" class="semantic-builder-keys-tab{" active" if analyze_active else ""}" role="tab"
        data-spreadsheet-tab="analyze" aria-selected="{"true" if analyze_active else "false"}"
        aria-controls="spreadsheet-engine-panel-analyze">Upload</button>
      <button type="button" class="semantic-builder-keys-tab{" active" if review_active else ""}" role="tab"
        data-spreadsheet-tab="review" aria-selected="{"true" if review_active else "false"}"
        aria-controls="spreadsheet-engine-panel-review">{escape(review_label)}</button>
      <button type="button" class="semantic-builder-keys-tab{" active" if catalog_active else ""}" role="tab"
        data-spreadsheet-tab="catalog" aria-selected="{"true" if catalog_active else "false"}"
        aria-controls="spreadsheet-engine-panel-catalog">{escape(catalog_label)}</button>
    </div>
    """


def _upload_form_html(
    url: Callable[[str], str],
    *,
    is_admin: bool,
    source: str,
    catalog_entries: list[dict[str, Any]] | None = None,
    prefill_catalog_id: str = "",
) -> str:
    if not is_admin:
        return '<p class="muted">Ask an admin to upload a workbook for analysis.</p>'
    catalog_options = '<option value="">— New workbook (no link) —</option>'
    for entry in catalog_entries or []:
        cid = str(entry.get("catalog_id") or "")
        if not cid:
            continue
        label = f"{entry.get('entity_name') or cid} ({entry.get('filename') or ''})"
        selected = " selected" if cid == prefill_catalog_id else ""
        catalog_options += f'<option value="{escape(cid)}"{selected}>{escape(label)}</option>'
    return f"""
    <form method="post" enctype="multipart/form-data" class="spreadsheet-upload-form"
          action="{escape(url(source_docs_inspector_path(source)))}">
      <input type="hidden" name="action" value="upload" />
      <div class="form-field">
        <label for="spreadsheet-linked-catalog">Link to existing catalog entry (optional)</label>
        <select name="linked_catalog_id" id="spreadsheet-linked-catalog" class="spreadsheet-catalog-select">
          {catalog_options}
        </select>
        <p class="muted">Re-uploads reuse saved transformations when structure matches.</p>
      </div>
      <label class="spreadsheet-dropzone" id="spreadsheet-dropzone" for="spreadsheet-workbook">
        <span class="spreadsheet-dropzone-title">Drop an Excel workbook (.xlsx)</span>
        <span class="spreadsheet-dropzone-hint muted">or click to choose a file — sheets, tables, and columns will be profiled automatically.</span>
        <span class="spreadsheet-dropzone-action btn btn-secondary">Choose file</span>
      </label>
      <input type="file" name="workbook" id="spreadsheet-workbook" class="spreadsheet-file-input"
        accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" required />
      <div class="spreadsheet-upload-actions">
        <button type="submit" class="btn btn-primary portal-submit-btn">Analyze workbook</button>
      </div>
    </form>
    """


def _catalog_list_html(
    entries: list[dict[str, Any]],
    *,
    url: Callable[[str], str],
    source: str,
    active_catalog_id: str = "",
) -> str:
    if not entries:
        return (
            '<section class="card pack-card">'
            "<h2>Approved catalog</h2>"
            "<p class=\"pack-card-lead\">Approved table proposals are saved here for review. "
            "Approve tables on the Proposals tab after analyzing a workbook.</p>"
            "</section>"
        )
    chips = []
    for entry in entries:
        cid = str(entry.get("catalog_id") or "")
        entity = str(entry.get("entity_name") or entry.get("table_id") or "Table")
        workbook = str(entry.get("filename") or "workbook")
        last_upload = str(entry.get("last_upload_at") or "")
        meta = f"Last upload: {escape(last_upload)}" if last_upload else ""
        active = " is-active" if cid and cid == active_catalog_id else ""
        href = _catalog_url(url, source=source, catalog_id=cid)
        chips.append(
            f'<a class="source-docs-source-chip{active}" href="{escape(href)}">'
            f"{escape(entity)}"
            f'<span class="source-docs-source-badge">{escape(workbook)}</span>'
            f'{"<span class=\"source-docs-source-badge\">" + meta + "</span>" if meta else ""}'
            "</a>"
        )
    return f"""
    <section class="card spreadsheet-catalog-list">
      <h2>Approved catalog</h2>
      <p class="muted">Every approved table proposal is saved here. Select one to review its schema and profiling.</p>
      <nav class="source-docs-source-nav" aria-label="Approved proposals">{"".join(chips)}</nav>
    </section>
    """


def _catalog_detail_html(
    entry: dict[str, Any],
    *,
    url: Callable[[str], str],
    source: str,
    table_preview: dict[str, Any] | None = None,
    is_admin: bool = False,
) -> str:
    proposal = entry.get("proposal") if isinstance(entry.get("proposal"), dict) else entry
    if not isinstance(proposal, dict):
        return ""
    entity = str(entry.get("entity_name") or proposal.get("entity_name") or "Approved table")
    catalog_id = str(entry.get("catalog_id") or "")
    transformation = entry.get("transformation") or proposal.get("transformation") or {}
    upload_history = list(entry.get("upload_history") or [])
    history_html = ""
    if upload_history:
        rows = ""
        for item in reversed(upload_history[-10:]):
            rows += (
                "<tr>"
                f"<td>{escape(str(item.get('uploaded_at') or ''))}</td>"
                f"<td><code>{escape(str(item.get('job_id') or ''))}</code></td>"
                f"<td>{escape(str(item.get('uploaded_by') or ''))}</td>"
                "</tr>"
            )
        history_html = f"""
        <h3 class="kpi-section-heading">Upload history</h3>
        <table class="semantic-builder-table">
          <thead><tr><th>Uploaded</th><th>Job</th><th>By</th></tr></thead>
          <tbody>{rows}</tbody>
        </table>
        """
    reupload_form = ""
    if is_admin and catalog_id:
        reupload_form = f"""
        <form method="post" enctype="multipart/form-data" class="spreadsheet-reupload-form">
          <input type="hidden" name="action" value="reupload_catalog" />
          <input type="hidden" name="catalog_id" value="{escape(catalog_id)}" />
          <label class="spreadsheet-dropzone spreadsheet-reupload-dropzone" for="spreadsheet-reupload-workbook">
            <span class="spreadsheet-dropzone-title">Re-upload workbook for {escape(entity)}</span>
            <span class="spreadsheet-dropzone-hint muted">Linked to catalog entry {escape(catalog_id)}</span>
          </label>
          <input type="file" name="workbook" id="spreadsheet-reupload-workbook" class="spreadsheet-file-input"
            accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" required />
          <button type="submit" class="btn btn-primary portal-submit-btn">Analyze re-upload</button>
        </form>
        """
    return f"""
    <section class="card spreadsheet-catalog-detail">
      <div class="assistant-diff-nav">
        <a class="btn btn-secondary assistant-diff-nav-btn" href="{escape(_catalog_url(url, source=source))}">All catalog entries</a>
        <span class="kpi-chip">Approved</span>
      </div>
      <h2>{escape(entity)}</h2>
      {reupload_form}
      <section class="spreadsheet-transform-panel">
        <h3 class="kpi-section-heading">Approved transformation</h3>
        {_transformation_steps_html(transformation)}
      </section>
      {history_html}
      {_table_analysis_html(
          proposal,
          readonly=True,
          catalog_meta=entry,
          embedded=True,
          table_preview=table_preview,
          transform_preview=None,
      )}
    </section>
    """


def _chat_panel_html(
    url: Callable[[str], str],
    *,
    source: str,
    job_id: str,
    table: dict[str, Any] | None,
    table_index: int,
    disabled: bool = False,
) -> str:
    table_id = str((table or {}).get("table_id") or "")
    entity_name = str((table or {}).get("entity_name") or table_id or "this table")
    if disabled or not table_id:
        return ""
    return f"""
    <section class="card" id="spreadsheet-table-chat">
      <h2>Refine this table</h2>
      <p class="muted">Chat applies only to <strong>{escape(entity_name)}</strong>. Switch tables above to refine a different proposal.</p>
      <div class="governance-update-panel">
        <div class="assistant-chat-shell">
          <div class="assistant-chat">
            {_chat_html(table, entity_name=entity_name)}
          </div>
          <form method="post" action="{escape(url(source_docs_inspector_path(source)))}" class="assistant-compose">
            <input type="hidden" name="action" value="chat" />
            <input type="hidden" name="job_id" value="{escape(job_id)}" />
            <input type="hidden" name="table_id" value="{escape(table_id)}" />
            <input type="hidden" name="table_index" value="{table_index}" />
            <div class="form-field assistant-compose-field">
              <label for="spreadsheet-chat">Message</label>
              <textarea id="spreadsheet-chat" name="message" rows="2" required
                class="assistant-compose-input"
                placeholder="e.g. Treat Customer No as the primary key and rename it customer_id"></textarea>
            </div>
            <button type="submit" class="btn btn-primary portal-submit-btn">Send</button>
          </form>
        </div>
      </div>
    </section>
    """


def _proposal_generation_status_html(
    *,
    filename: str,
    pipeline: dict[str, Any],
    job_id: str,
) -> str:
    stages_html = ""
    for stage in pipeline.get("stages") or []:
        if not isinstance(stage, dict):
            continue
        state = str(stage.get("state") or "pending")
        key = escape(str(stage.get("key") or ""))
        label = escape(str(stage.get("label") or ""))
        stages_html += (
            f'<li class="spreadsheet-proposal-stage is-{escape(state)}" data-stage="{key}">'
            f'<span class="spreadsheet-proposal-stage-marker" aria-hidden="true"></span>'
            f'<span class="spreadsheet-proposal-stage-label">{label}</span>'
            "</li>"
        )
    execution_status = str(pipeline.get("execution_status") or "").strip().lower()
    badge = ""
    if execution_status:
        badge = (
            '<span class="kpi-chip spreadsheet-proposal-execution-badge" '
            f'id="spreadsheet-proposal-execution-badge">Step Functions: {escape(execution_status.upper())}</span>'
        )
    error = str(pipeline.get("error") or "").strip()
    error_html = ""
    if error:
        error_html = f'<p class="form-error spreadsheet-proposal-status-error" id="spreadsheet-proposal-status-error">{escape(error)}</p>'
    return f"""
    <section class="card spreadsheet-proposal-status" id="spreadsheet-proposal-status"
             data-job-id="{escape(job_id)}">
      <div class="spreadsheet-proposal-status-head">
        <div>
          <h2 id="spreadsheet-proposal-status-label">{escape(str(pipeline.get("status_label") or "Analyzing workbook"))}</h2>
          <p class="muted" id="spreadsheet-proposal-status-detail">{escape(str(pipeline.get("status_detail") or ""))}</p>
        </div>
        {badge}
      </div>
      <p class="muted spreadsheet-proposal-status-workbook">Workbook: <strong>{escape(filename or "workbook")}</strong></p>
      <ol class="spreadsheet-proposal-stages" id="spreadsheet-proposal-stages" aria-label="Proposal generation progress">
        {stages_html}
      </ol>
      {error_html}
    </section>
    """


def _proposal_finished_empty_html(*, filename: str, error: str = "") -> str:
    if error:
        body = f'<p class="form-error">{escape(error)}</p>'
    else:
        body = (
            '<p class="pack-card-lead">Analysis finished but no table proposals were generated. '
            "Try uploading a workbook with a clear header row and tabular data.</p>"
        )
    return f"""
    <section class="card pack-card spreadsheet-proposal-empty">
      <h2>{escape(filename or "Workbook")}</h2>
      {body}
    </section>
    """


def _ready_banner_html(
    *,
    url: Callable[[str], str],
    source: str,
    job_id: str,
    table_count: int,
) -> str:
    href = _proposal_url(url, source=source, job_id=job_id, table_index=0)
    noun = "table" if table_count == 1 else "tables"
    return f"""
    <div class="form-success spreadsheet-ready-banner">
      Analysis complete — {table_count} proposed {noun} ready for review.
      <a class="btn btn-secondary spreadsheet-ready-banner-btn" href="{escape(href)}">View proposals</a>
    </div>
    """


def _tabs_script() -> str:
    return """
<script>
(function () {
  function activateTab(name) {
    var section = document.getElementById("spreadsheet-engine-tabs");
    if (!section) return;
    section.querySelectorAll("[data-spreadsheet-tab]").forEach(function (tab) {
      var active = tab.getAttribute("data-spreadsheet-tab") === name;
      tab.classList.toggle("active", active);
      tab.setAttribute("aria-selected", active ? "true" : "false");
    });
    section.querySelectorAll("[data-spreadsheet-panel]").forEach(function (panel) {
      panel.hidden = panel.getAttribute("data-spreadsheet-panel") !== name;
    });
  }
  function syncTabUrl(name) {
    var url = new URL(window.location.href);
    url.searchParams.set("tab", name);
    window.history.replaceState({}, "", url.toString());
  }
  var section = document.getElementById("spreadsheet-engine-tabs");
  if (!section) return;
  var defaultTab = section.getAttribute("data-default-tab") || "analyze";
  activateTab(defaultTab);
  section.querySelectorAll("[data-spreadsheet-tab]").forEach(function (tab) {
    tab.addEventListener("click", function () {
      var name = tab.getAttribute("data-spreadsheet-tab") || "analyze";
      activateTab(name);
      syncTabUrl(name);
    });
  });
})();
</script>
"""


def _compose_script() -> str:
    return """
<script>
(function () {
  var box = document.getElementById("spreadsheet-chat");
  var form = document.querySelector("#spreadsheet-table-chat form.assistant-compose");
  if (!box || !form || box.dataset.enterBound === "1") return;
  box.dataset.enterBound = "1";
  box.addEventListener("keydown", function (event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      form.requestSubmit();
    }
  });
})();
</script>
"""


def _scroll_script() -> str:
    return """
<script>
(function () {
  var chat = document.querySelector("#spreadsheet-table-chat .assistant-chat");
  if (!chat) return;
  chat.scrollTop = chat.scrollHeight;
})();
</script>
"""


def _status_poll_script(status_url: str, job_id: str, *, poll: bool) -> str:
    if not job_id or not poll:
        return ""
    return f"""
<script>
(function () {{
  var statusUrl = {_json_for_script(status_url)};
  var jobId = {_json_for_script(job_id)};
  var statusRoot = document.getElementById("spreadsheet-proposal-status");
  if (!statusRoot) return;

  var stopped = false;
  var reloadKey = "sse-proposals-loaded-" + jobId;

  function hasProposalContent() {{
    return !!document.getElementById("spreadsheet-table-analysis");
  }}

  function setStageState(node, state) {{
    node.classList.remove("is-pending", "is-active", "is-complete", "is-error");
    node.classList.add("is-" + state);
  }}

  function renderPipeline(pipeline) {{
    if (!pipeline) return;
    var label = document.getElementById("spreadsheet-proposal-status-label");
    var detail = document.getElementById("spreadsheet-proposal-status-detail");
    var badge = document.getElementById("spreadsheet-proposal-execution-badge");
    var error = document.getElementById("spreadsheet-proposal-status-error");
    if (label) label.textContent = pipeline.status_label || "Analyzing workbook";
    if (detail) detail.textContent = pipeline.status_detail || "";
    if (badge) {{
      var executionStatus = (pipeline.execution_status || "").toUpperCase();
      if (executionStatus) {{
        badge.textContent = "Step Functions: " + executionStatus;
        badge.hidden = false;
      }} else {{
        badge.hidden = true;
      }}
    }}
    if (error) {{
      if (pipeline.error) {{
        error.textContent = pipeline.error;
        error.hidden = false;
      }} else {{
        error.hidden = true;
      }}
    }}
    (pipeline.stages || []).forEach(function (stage) {{
      var node = statusRoot.querySelector('[data-stage="' + stage.key + '"]');
      if (node) setStageState(node, stage.state || "pending");
    }});
  }}

  function tableCount(payload) {{
    if (payload.report && payload.report.tables && payload.report.tables.length) {{
      return payload.report.tables.length;
    }}
    return payload.table_count || 0;
  }}

  function stopPolling() {{
    stopped = true;
  }}

  function handlePayload(payload) {{
    if (stopped || hasProposalContent()) {{
      stopPolling();
      return true;
    }}
    if (payload.pipeline) renderPipeline(payload.pipeline);
    if (tableCount(payload) > 0) {{
      stopPolling();
      if (sessionStorage.getItem(reloadKey) === "1") {{
        return true;
      }}
      sessionStorage.setItem(reloadKey, "1");
      var url = new URL(window.location.href);
      url.searchParams.set("job_id", jobId);
      url.searchParams.set("tab", "review");
      url.searchParams.set("table_index", "0");
      window.location.replace(url.toString());
      return true;
    }}
    if (payload.pipeline && payload.pipeline.failed) {{
      stopPolling();
      return true;
    }}
    if (payload.status === "ready" || payload.status === "error") {{
      stopPolling();
      if (sessionStorage.getItem(reloadKey) !== "1") {{
        sessionStorage.setItem(reloadKey, "1");
        window.location.replace(window.location.href);
      }}
      return true;
    }}
    return false;
  }}

  function pollOnce() {{
    if (stopped) return Promise.resolve(true);
    return fetch(statusUrl + "?job_id=" + encodeURIComponent(jobId), {{
      credentials: "same-origin",
      headers: {{ "Accept": "application/json" }}
    }})
      .then(function (r) {{ return r.json(); }})
      .then(function (payload) {{ return handlePayload(payload); }})
      .catch(function () {{ return false; }});
  }}

  pollOnce().then(function (done) {{
    if (done || stopped) return;
    var timer = setInterval(function () {{
      pollOnce().then(function (finished) {{
        if (finished) clearInterval(timer);
      }});
    }}, 2500);
  }});
}})();
</script>
"""


def _dropzone_script() -> str:
    return """
<script>
(function () {
  var zone = document.getElementById("spreadsheet-dropzone");
  var input = document.getElementById("spreadsheet-workbook");
  if (!zone || !input) return;
  function setName() {
    var label = zone.querySelector(".spreadsheet-dropzone-title");
    if (!label || !input.files || !input.files.length) return;
    label.textContent = input.files[0].name;
  }
  input.addEventListener("change", setName);
  ["dragenter", "dragover"].forEach(function (name) {
    zone.addEventListener(name, function (event) {
      event.preventDefault();
      zone.classList.add("is-dragover");
    });
  });
  ["dragleave", "drop"].forEach(function (name) {
    zone.addEventListener(name, function (event) {
      event.preventDefault();
      zone.classList.remove("is-dragover");
    });
  });
  zone.addEventListener("drop", function (event) {
    var files = event.dataTransfer && event.dataTransfer.files;
    if (!files || !files.length) return;
    input.files = files;
    setName();
  });
})();
</script>
"""


def render_spreadsheet_engine_page(
    *,
    url: Callable[[str], str],
    sources: list[str],
    active_source: str,
    availability: dict[str, bool],
    is_admin: bool,
    job: dict[str, Any] | None = None,
    report: dict[str, Any] | None = None,
    request_job_id: str = "",
    table_index: int = 0,
    catalog_entries: list[dict[str, Any]] | None = None,
    active_catalog: dict[str, Any] | None = None,
    message: str = "",
    error: str = "",
    status_url: str = "",
    active_tab: str = "analyze",
    table_preview: dict[str, Any] | None = None,
    catalog_preview: dict[str, Any] | None = None,
    transform_preview: dict[str, Any] | None = None,
    prefill_catalog_id: str = "",
) -> str:
    source = normalize_reference_source(active_source) or "sse"
    job_id = str((job or {}).get("job_id") or request_job_id or "")
    job_status = str((job or {}).get("status") or "")
    filename = str((job or {}).get("filename") or "")
    tables = list((report or {}).get("tables") or [])
    analyzing = job_status in _IN_FLIGHT_JOB_STATUSES
    has_proposals = bool(tables) and job_status != "error"
    show_generation_status = bool(job_id) and not has_proposals and analyzing
    pipeline = spreadsheet_pipeline_progress(
        job_status or ("running" if job_id and analyzing else ""),
        error=str((job or {}).get("error") or ""),
        reload_mode=bool((job or {}).get("reload_mode")) or bool((job or {}).get("reupload")),
    )
    catalog = list(catalog_entries or [])
    active_catalog_id = str((active_catalog or {}).get("catalog_id") or "")
    if table_index < 0 or table_index >= len(tables):
        table_index = 0
    active_table = tables[table_index] if tables else None

    if active_tab == "catalog":
        tab = "catalog"
    elif active_tab == "analyze":
        tab = "analyze"
    elif active_tab == "review" or has_proposals or job_id:
        tab = "review"
    else:
        tab = "analyze"

    body = f"""
    <div class="source-docs-page spreadsheet-engine-page" data-source="{escape(source)}">
      {_source_switcher(
          sources=sources,
          active_source=source,
          url=url,
          availability=availability,
      )}
    """
    if message:
        body += f'<div class="form-success">{escape(message)}</div>'
    if error:
        body += f'<div class="form-error">{escape(error)}</div>'
    if job_id and job_status == "error":
        body += f'<div class="form-error">{escape(str((job or {}).get("error") or "Analysis failed."))}</div>'
    if has_proposals and tab == "analyze":
        body += _ready_banner_html(
            url=url, source=source, job_id=job_id, table_count=len(tables)
        )

    analyze_hidden = "" if tab == "analyze" else " hidden"
    review_hidden = "" if tab == "review" else " hidden"
    catalog_hidden = "" if tab == "catalog" else " hidden"

    body += f"""
    <section class="semantic-builder-keys-tabs-section" id="spreadsheet-engine-tabs"
             data-default-tab="{escape(tab)}">
      {_tabs_html(active_tab=tab, review_count=len(tables), catalog_count=len(catalog))}
      <div class="semantic-builder-keys-panel" id="spreadsheet-engine-panel-analyze"
           data-spreadsheet-panel="analyze" role="tabpanel"{analyze_hidden}>
        <section class="card" id="spreadsheet-engine-upload">
          <h2>Upload workbook</h2>
          <p class="muted">Excel workbooks are parsed into table candidates, profiled for types and keys, then interpreted into proposed schemas.</p>
          {_upload_form_html(
              url,
              is_admin=is_admin,
              source=source,
              catalog_entries=catalog,
              prefill_catalog_id=prefill_catalog_id,
          )}
        </section>
    """

    body += f"""
      </div>
      <div class="semantic-builder-keys-panel" id="spreadsheet-engine-panel-review"
           data-spreadsheet-panel="review" role="tabpanel"{review_hidden}>
"""

    if show_generation_status:
        body += _proposal_generation_status_html(
            filename=filename,
            pipeline=pipeline,
            job_id=job_id,
        )
    elif has_proposals:
        suggested = list((job or {}).get("suggested_catalog_ids") or [])
        linked = str((job or {}).get("linked_catalog_id") or "")
        if suggested and not linked and is_admin:
            links = ""
            for cid in suggested[:3]:
                links += f"""
                <form method="post" class="spreadsheet-catalog-suggest-form" style="display:inline">
                  <input type="hidden" name="action" value="link_catalog" />
                  <input type="hidden" name="job_id" value="{escape(job_id)}" />
                  <input type="hidden" name="catalog_id" value="{escape(cid)}" />
                  <button type="submit" class="btn btn-secondary btn-sm">{escape(cid)}</button>
                </form>
                """
            body += f"""
        <section class="card spreadsheet-catalog-suggestions">
          <h2>Catalog match suggestions</h2>
          <p class="muted">This workbook structure matches existing catalog entries. Link one to reuse transformations:</p>
          <div class="spreadsheet-catalog-suggest-actions">{links}</div>
        </section>
            """
        if filename:
            body += f"""
        <section class="card spreadsheet-job-summary">
          <h2>{escape(filename)}</h2>
          <p class="muted">{len(tables)} proposed table{"s" if len(tables) != 1 else ""} — review schema, grain, and profiling, then approve or refine with chat.</p>
        </section>
            """
        body += _table_pager_html(
            job_id=job_id,
            tables=tables,
            table_index=table_index,
            url=url,
            source=source,
        )
        body += _table_analysis_html(
            active_table or {},
            job_id=job_id,
            table_index=table_index,
            total=len(tables),
            url=url,
            source=source,
            table_preview=table_preview,
            transform_preview=transform_preview,
        )
        body += _chat_panel_html(
            url,
            source=source,
            job_id=job_id,
            table=active_table,
            table_index=table_index,
        )
    elif job_id and job_status == "error":
        body += _proposal_finished_empty_html(
            filename=filename,
            error=str((job or {}).get("error") or "Analysis failed."),
        )
    elif job_id and job_status == "ready":
        body += _proposal_finished_empty_html(filename=filename)
    elif not show_generation_status:
        body += """
        <section class="card pack-card">
          <h2>Proposals</h2>
          <p class="pack-card-lead">Upload and analyze a workbook on the Upload tab. Proposed tables will appear here with schema, profiling, and per-table chat.</p>
        </section>
        """

    body += f"""
      </div>
      <div class="semantic-builder-keys-panel" id="spreadsheet-engine-panel-catalog"
           data-spreadsheet-panel="catalog" role="tabpanel"{catalog_hidden}>
        {_catalog_list_html(catalog, url=url, source=source, active_catalog_id=active_catalog_id)}
"""

    if active_catalog:
        body += _catalog_detail_html(
            active_catalog,
            url=url,
            source=source,
            table_preview=catalog_preview,
            is_admin=is_admin,
        )

    body += """
      </div>
    </section>
    """
    body += _source_docs_styles()
    body += _tabs_script()
    body += _schema_toggle_script()
    body += _compose_script()
    body += _scroll_script()
    body += _dropzone_script()
    body += _status_poll_script(
        status_url,
        job_id,
        poll=show_generation_status,
    )
    body += "</div>"
    return body
