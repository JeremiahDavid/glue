"""Spreadsheet Engine Source Browser UI — aligned with DNA Engine layout."""

from __future__ import annotations

import json
from html import escape
from typing import Any, Callable

from meshflow.dna.source_docs.reference import normalize_reference_source
from meshflow.dna.web.portal.dna_nav import source_docs_inspector_path
from meshflow.dna.web.portal.semantics.source_docs_render import _source_switcher, _styles as _source_docs_styles


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
        '<div class="semantic-builder-scroll table-wrap">'
        '<table class="semantic-builder-table">'
        "<thead><tr><th>Column</th><th>Type</th><th>Description</th><th>Flags</th></tr></thead>"
        f"<tbody>{rows}</tbody></table></div>"
    )


def _profiling_html(profiling: dict[str, Any]) -> str:
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
    return f"""
    <h3 class="kpi-section-heading">Column profiling</h3>
    <div class="semantic-builder-scroll table-wrap">
      <table class="semantic-builder-table">
        <thead><tr><th>Column</th><th>Type</th><th>Null %</th><th>Cardinality</th><th>Key?</th><th>Patterns</th></tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </div>
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


def _table_analysis_html(
    table: dict[str, Any],
    *,
    job_id: str,
    table_index: int,
    total: int,
    url: Callable[[str], str],
    source: str,
) -> str:
    status = str(table.get("status") or "pending_review")
    status_label = status.replace("_", " ").title()
    schema = table.get("schema") or []
    profiling = table.get("profiling") or {}
    relationships = table.get("relationships") or []
    notes = table.get("notes") or []
    rel_html = ""
    for rel in relationships:
        if not isinstance(rel, dict):
            continue
        rel_html += (
            "<li>"
            f"{escape(str(rel.get('to_entity') or ''))} via "
            f"<code>{escape(str(rel.get('via_column') or ''))}</code>"
            f" ({float(rel.get('confidence') or 0):.0%})"
            "</li>"
        )
    notes_html = "".join(f"<li>{escape(str(note))}</li>" for note in notes if str(note).strip())
    approve_btn = ""
    if status != "approved":
        approve_btn = f"""
        <form method="post" class="assistant-approve-form">
          <input type="hidden" name="action" value="approve_table" />
          <input type="hidden" name="job_id" value="{escape(job_id)}" />
          <input type="hidden" name="table_id" value="{escape(str(table.get('table_id') or ''))}" />
          <input type="hidden" name="table_index" value="{table_index}" />
          <button type="submit" class="btn btn-primary">Approve table</button>
        </form>
        """
    else:
        approve_btn = '<p class="muted">This table proposal is approved.</p>'

    prev_href = next_href = ""
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

    return f"""
    <section class="card pack-card" id="spreadsheet-table-analysis">
      {nav}
      <h2>{escape(str(table.get('entity_name') or table.get('table_id') or 'Proposed table'))}</h2>
      <p class="pack-card-lead">{escape(str(table.get('purpose') or ''))}</p>
      {_stats_html(table)}
      <h3 class="kpi-section-heading">Proposed schema</h3>
      {_schema_table_html(schema)}
      {_profiling_html(profiling)}
      {"<h3 class='kpi-section-heading'>Relationships</h3><ul class='pack-card-lead'>" + rel_html + "</ul>" if rel_html else ""}
      {"<h3 class='kpi-section-heading'>Notes</h3><ul class='pack-card-lead'>" + notes_html + "</ul>" if notes_html else ""}
      {approve_btn}
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


def _tabs_html(*, active_tab: str, review_count: int, proposals_ready: bool) -> str:
    analyze_active = active_tab != "review"
    review_active = active_tab == "review"
    review_label = (
        f"Proposals ({review_count})" if review_count else "Proposals"
    )
    review_disabled = "" if proposals_ready else ' disabled title="Available after analysis completes"'
    return f"""
    <div class="semantic-builder-keys-tabs" role="tablist" aria-label="Spreadsheet Engine">
      <button type="button" class="semantic-builder-keys-tab{" active" if analyze_active else ""}" role="tab"
        data-spreadsheet-tab="analyze" aria-selected="{"true" if analyze_active else "false"}"
        aria-controls="spreadsheet-engine-panel-analyze">Upload</button>
      <button type="button" class="semantic-builder-keys-tab{" active" if review_active else ""}" role="tab"
        data-spreadsheet-tab="review" aria-selected="{"true" if review_active else "false"}"
        aria-controls="spreadsheet-engine-panel-review"{review_disabled}>{escape(review_label)}</button>
    </div>
    """


def _upload_form_html(url: Callable[[str], str], *, is_admin: bool, source: str) -> str:
    if not is_admin:
        return '<p class="muted">Ask an admin to upload a workbook for analysis.</p>'
    return f"""
    <form method="post" enctype="multipart/form-data" class="spreadsheet-upload-form"
          action="{escape(url(source_docs_inspector_path(source)))}">
      <input type="hidden" name="action" value="upload" />
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


def _recent_jobs_html(
    recent_jobs: list[dict[str, Any]] | None,
    *,
    url: Callable[[str], str],
    source: str,
    active_job_id: str,
) -> str:
    if not recent_jobs:
        return ""
    items = ""
    for recent in recent_jobs[:8]:
        rid = str(recent.get("job_id") or "")
        fname = str(recent.get("filename") or "workbook")
        rstatus = str(recent.get("status") or "")
        active = " is-active" if rid == active_job_id else ""
        if rstatus == "ready":
            href = _proposal_url(url, source=source, job_id=rid, table_index=0)
        else:
            href = url(f"{source_docs_inspector_path(source)}?job_id={rid}&tab=analyze")
        items += (
            f'<a class="source-docs-source-chip{active}" href="{escape(href)}">'
            f"{escape(fname)}"
            f'<span class="source-docs-source-badge{" is-empty" if rstatus != "ready" else ""}">'
            f"{escape(rstatus)}</span></a>"
        )
    return f"""
    <div class="spreadsheet-recent-jobs">
      <p class="muted spreadsheet-recent-label">Recent workbooks</p>
      <nav class="source-docs-source-nav" aria-label="Recent workbook jobs">{items}</nav>
    </div>
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
  var section = document.getElementById("spreadsheet-engine-tabs");
  if (!section) return;
  var defaultTab = section.getAttribute("data-default-tab") || "analyze";
  activateTab(defaultTab);
  section.querySelectorAll("[data-spreadsheet-tab]").forEach(function (tab) {
    if (tab.disabled) return;
    tab.addEventListener("click", function () {
      activateTab(tab.getAttribute("data-spreadsheet-tab") || "analyze");
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


def _status_poll_script(status_url: str, job_id: str) -> str:
    if not job_id:
        return ""
    return f"""
<script>
(function () {{
  if (!document.getElementById("spreadsheet-job-running")) return;
  var statusUrl = {_json_for_script(status_url)};
  var jobId = {_json_for_script(job_id)};
  var timer = setInterval(function () {{
    fetch(statusUrl + "?job_id=" + encodeURIComponent(jobId), {{
      credentials: "same-origin",
      headers: {{ "Accept": "application/json" }}
    }})
      .then(function (r) {{ return r.json(); }})
      .then(function (payload) {{
        if (payload.status === "ready" || payload.status === "error") {{
          clearInterval(timer);
          if (payload.status === "ready" && (payload.table_count || 0) > 0) {{
            var url = new URL(window.location.href);
            url.searchParams.set("tab", "review");
            url.searchParams.set("table_index", "0");
            window.location.href = url.toString();
            return;
          }}
          window.location.reload();
        }}
      }})
      .catch(function () {{}});
  }}, 2500);
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
    table_index: int = 0,
    recent_jobs: list[dict[str, Any]] | None = None,
    message: str = "",
    error: str = "",
    status_url: str = "",
    active_tab: str = "analyze",
) -> str:
    source = normalize_reference_source(active_source) or "sse"
    job_id = str((job or {}).get("job_id") or "")
    job_status = str((job or {}).get("status") or "")
    filename = str((job or {}).get("filename") or "")
    tables = list((report or {}).get("tables") or [])
    analyzing = job_status in {"running", "parsing", "profiling", "interpreting", "uploaded"}
    has_proposals = bool(tables) and job_status not in {"error"}
    if table_index < 0 or table_index >= len(tables):
        table_index = 0
    active_table = tables[table_index] if tables else None

    if active_tab == "review" and has_proposals:
        tab = "review"
    elif active_tab == "analyze":
        tab = "analyze"
    elif has_proposals:
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

    analyze_hidden = " hidden" if tab == "review" else ""
    review_hidden = "" if tab == "review" else " hidden"

    body += f"""
    <section class="semantic-builder-keys-tabs-section" id="spreadsheet-engine-tabs"
             data-default-tab="{escape(tab)}">
      {_tabs_html(active_tab=tab, review_count=len(tables), proposals_ready=has_proposals)}
      <div class="semantic-builder-keys-panel" id="spreadsheet-engine-panel-analyze"
           data-spreadsheet-panel="analyze" role="tabpanel"{analyze_hidden}>
        <section class="card" id="spreadsheet-engine-upload">
          <h2>Upload workbook</h2>
          <p class="muted">Excel workbooks are parsed into table candidates, profiled for types and keys, then interpreted into proposed schemas.</p>
          {_upload_form_html(url, is_admin=is_admin, source=source)}
          {_recent_jobs_html(recent_jobs, url=url, source=source, active_job_id=job_id)}
        </section>
    """

    if analyzing and job_id:
        body += f"""
        <section class="card" id="spreadsheet-engine-progress">
          <h2>Analysis in progress</h2>
          <p class="muted">Profiling <strong>{escape(filename or "workbook")}</strong>. This page will open proposals when analysis completes.</p>
          <div class="assistant-chat">
            {_chat_html(None, analyzing=True)}
          </div>
        </section>
        """

    body += f"""
      </div>
      <div class="semantic-builder-keys-panel" id="spreadsheet-engine-panel-review"
           data-spreadsheet-panel="review" role="tabpanel"{review_hidden}>
"""

    if has_proposals:
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
        )
        body += _chat_panel_html(
            url,
            source=source,
            job_id=job_id,
            table=active_table,
            table_index=table_index,
        )
    else:
        body += """
        <section class="card pack-card">
          <h2>Proposals</h2>
          <p class="pack-card-lead">Upload and analyze a workbook on the Upload tab. Proposed tables will appear here with schema, profiling, and per-table chat.</p>
        </section>
        """

    body += """
      </div>
    </section>
    """
    body += _source_docs_styles()
    body += _tabs_script()
    body += _compose_script()
    body += _scroll_script()
    body += _dropzone_script()
    body += _status_poll_script(status_url, job_id if analyzing else "")
    body += "</div>"
    return body
