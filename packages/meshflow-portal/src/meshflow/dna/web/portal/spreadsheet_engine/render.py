"""Spreadsheet Engine Source Browser UI."""

from __future__ import annotations

import json
from html import escape
from typing import Any, Callable

from meshflow.dna.source_docs.reference import list_reference_sources, normalize_reference_source
from meshflow.dna.web.portal.dna_nav import source_docs_inspector_path, source_label
from meshflow.dna.web.portal.semantics.source_docs_render import _source_switcher
from meshflow.dna.web.theme import page_header


def _json_for_script(payload: Any) -> str:
    return json.dumps(payload).replace("<", "\\u003c")


def _chat_html(job: dict[str, Any] | None) -> str:
    history = list((job or {}).get("chat_history") or [])
    if not history:
        return (
            '<p class="pack-card-lead">'
            "Drop an Excel workbook to profile tables, or ask questions about a proposal."
            "</p>"
        )
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
    return html or '<p class="pack-card-lead">No messages yet.</p>'


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
        rows += (
            "<tr>"
            f"<td><code>{escape(str(col.get('name') or ''))}</code></td>"
            f"<td>{escape(str(col.get('type') or ''))}</td>"
            f"<td>{escape(str(col.get('description') or ''))}</td>"
            f"<td>{escape(', '.join(flags))}</td>"
            "</tr>"
        )
    if not rows:
        return "<p class='pack-card-lead'>No schema columns proposed.</p>"
    return (
        '<table class="data-table spreadsheet-schema-table">'
        "<thead><tr><th>Column</th><th>Type</th><th>Description</th><th>Flags</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
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
            f"<td>{escape(', '.join(col.get('patterns') or []))}</td>"
            "</tr>"
        )
    return (
        "<h3>Column profiling</h3>"
        '<table class="data-table spreadsheet-profile-table">'
        "<thead><tr><th>Column</th><th>Type</th><th>Null %</th><th>Cardinality</th>"
        "<th>Key?</th><th>Patterns</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
    )


def _table_analysis_html(table: dict[str, Any], *, job_id: str, table_index: int, total: int) -> str:
    status = str(table.get("status") or "pending_review")
    status_label = status.replace("_", " ").title()
    source = table.get("source") or {}
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
        <form method="post" class="spreadsheet-approve-form">
          <input type="hidden" name="action" value="approve_table" />
          <input type="hidden" name="job_id" value="{escape(job_id)}" />
          <input type="hidden" name="table_id" value="{escape(str(table.get('table_id') or ''))}" />
          <button type="submit" class="btn btn-primary">Approve this table</button>
        </form>
        """
    return f"""
    <section class="card spreadsheet-table-analysis" id="spreadsheet-table-analysis">
      <div class="spreadsheet-table-nav">
        <span class="spreadsheet-table-counter">Table {table_index + 1} of {total}</span>
        <span class="spreadsheet-table-status is-{escape(status)}">{escape(status_label)}</span>
      </div>
      <h2>{escape(str(table.get('entity_name') or table.get('table_id') or 'Proposed table'))}</h2>
      <p class="pack-card-lead">{escape(str(table.get('purpose') or ''))}</p>
      <dl class="spreadsheet-meta-grid">
        <div><dt>Grain</dt><dd>{escape(str(table.get('grain') or ''))}</dd></div>
        <div><dt>Sheet</dt><dd>{escape(str(source.get('sheet') or ''))}</dd></div>
        <div><dt>Rows</dt><dd>{int(source.get('row_count') or 0)}</dd></div>
        <div><dt>Confidence</dt><dd>{float(table.get('confidence') or 0):.0%}</dd></div>
      </dl>
      <h3>Proposed schema</h3>
      {_schema_table_html(schema)}
      {_profiling_html(profiling)}
      {"<h3>Relationships</h3><ul>" + rel_html + "</ul>" if rel_html else ""}
      {"<h3>Notes</h3><ul>" + notes_html + "</ul>" if notes_html else ""}
      {approve_btn}
    </section>
    """


def _pagination_html(
    *,
    job_id: str,
    tables: list[dict[str, Any]],
    table_index: int,
    url: Callable[[str], str],
    source: str,
) -> str:
    if len(tables) <= 1:
        return ""
    links = []
    for idx, table in enumerate(tables):
        active = " is-active" if idx == table_index else ""
        label = str(table.get("entity_name") or table.get("table_id") or f"Table {idx + 1}")
        href = url(
            f"{source_docs_inspector_path(source)}"
            f"?job_id={job_id}&table_index={idx}"
        )
        links.append(
            f'<a class="spreadsheet-table-pager{active}" href="{escape(href)}">'
            f"{escape(label)}</a>"
        )
    prev_href = next_href = ""
    if table_index > 0:
        prev_href = url(
            f"{source_docs_inspector_path(source)}?job_id={job_id}&table_index={table_index - 1}"
        )
    if table_index < len(tables) - 1:
        next_href = url(
            f"{source_docs_inspector_path(source)}?job_id={job_id}&table_index={table_index + 1}"
        )
    nav = '<nav class="spreadsheet-table-pager-nav" aria-label="Proposed tables">' + "".join(links) + "</nav>"
    prev_next = '<div class="spreadsheet-table-prev-next">'
    if prev_href:
        prev_next += f'<a class="btn btn-secondary" href="{escape(prev_href)}">Previous</a>'
    if next_href:
        prev_next += f'<a class="btn btn-secondary" href="{escape(next_href)}">Next</a>'
    prev_next += "</div>"
    return nav + prev_next


def _upload_form_html(url: Callable[[str], str], *, is_admin: bool, source: str) -> str:
    if not is_admin:
        return "<p class='pack-card-lead'>Ask an admin to upload a workbook for analysis.</p>"
    return f"""
    <form method="post" enctype="multipart/form-data" class="spreadsheet-upload-form"
          action="{escape(url(source_docs_inspector_path(source)))}">
      <input type="hidden" name="action" value="upload" />
      <div class="spreadsheet-dropzone" id="spreadsheet-dropzone">
        <p class="spreadsheet-dropzone-lead">Drop an Excel workbook (.xlsx) here</p>
        <p class="spreadsheet-dropzone-sub">or choose a file to profile sheets, tables, and columns.</p>
        <input type="file" name="workbook" id="spreadsheet-workbook" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" required />
      </div>
      <button type="submit" class="btn btn-primary portal-submit-btn">Analyze workbook</button>
    </form>
    """


def _chat_form_html(
    url: Callable[[str], str],
    *,
    source: str,
    job_id: str,
    table_id: str,
    disabled: bool = False,
) -> str:
    if disabled or not job_id:
        return ""
    table_field = (
        f'<input type="hidden" name="table_id" value="{escape(table_id)}" />' if table_id else ""
    )
    return f"""
    <form method="post" action="{escape(url(source_docs_inspector_path(source)))}" class="assistant-compose">
      <input type="hidden" name="action" value="chat" />
      <input type="hidden" name="job_id" value="{escape(job_id)}" />
      {table_field}
      <div class="form-field assistant-compose-field">
        <label for="spreadsheet-chat">Message</label>
        <textarea id="spreadsheet-chat" name="message" rows="2" required
          class="assistant-compose-input"
          placeholder="e.g. Treat the Customer No column as the primary key and rename it customer_id"></textarea>
      </div>
      <button type="submit" class="btn btn-primary portal-submit-btn">Send</button>
    </form>
    """


def _status_poll_script(status_url: str, job_id: str) -> str:
    if not job_id:
        return ""
    return f"""
<script>
(function () {{
  var statusUrl = {_json_for_script(status_url)};
  var jobId = {_json_for_script(job_id)};
  if (!document.getElementById("spreadsheet-job-running")) return;
  var timer = setInterval(function () {{
    fetch(statusUrl + "?job_id=" + encodeURIComponent(jobId), {{ credentials: "same-origin" }})
      .then(function (r) {{ return r.json(); }})
      .then(function (payload) {{
        if (payload.status === "ready" || payload.status === "error") {{
          clearInterval(timer);
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
  });
})();
</script>
"""


def _styles() -> str:
    return """
<style>
.spreadsheet-dropzone {
  border: 2px dashed var(--border-subtle, #cbd5e1);
  border-radius: 12px;
  padding: 2rem;
  text-align: center;
  margin-bottom: 1rem;
  background: var(--surface-muted, #f8fafc);
}
.spreadsheet-dropzone.is-dragover { border-color: var(--accent, #2563eb); }
.spreadsheet-dropzone input[type="file"] { margin-top: 1rem; }
.spreadsheet-meta-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(10rem, 1fr));
  gap: 0.75rem 1rem;
  margin: 1rem 0;
}
.spreadsheet-table-pager-nav {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-bottom: 1rem;
}
.spreadsheet-table-pager {
  padding: 0.35rem 0.75rem;
  border-radius: 999px;
  border: 1px solid var(--border-subtle, #cbd5e1);
  text-decoration: none;
}
.spreadsheet-table-pager.is-active {
  background: var(--accent, #2563eb);
  color: #fff;
  border-color: transparent;
}
.spreadsheet-table-prev-next {
  display: flex;
  gap: 0.75rem;
  margin-bottom: 1rem;
}
.spreadsheet-table-status.is-approved { color: #15803d; }
.spreadsheet-job-list { list-style: none; padding: 0; margin: 0; }
.spreadsheet-job-list li { margin-bottom: 0.5rem; }
</style>
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
) -> str:
    source = normalize_reference_source(active_source) or "sse"
    body = f"""
    <div class="source-docs-page spreadsheet-engine-page" data-source="{escape(source)}">
      {page_header(
          "Source Browser",
          "Upload Excel workbooks, profile candidate tables, and approve proposed schemas.",
      )}
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

    job_id = str((job or {}).get("job_id") or "")
    job_status = str((job or {}).get("status") or "")
    running = job_status in {"running", "parsing", "profiling", "interpreting", "uploaded"}
    if running and job_status != "ready":
        body += (
            '<div class="form-success" id="spreadsheet-job-running">'
            "Analyzing workbook — parse, profile, and semantic interpretation in progress…"
            "</div>"
        )

    body += """
      <section class="card" id="spreadsheet-engine-upload">
        <h2>Workbook</h2>
    """
    body += _upload_form_html(url, is_admin=is_admin, source=source)

    if recent_jobs:
        items = ""
        for recent in recent_jobs[:8]:
            rid = str(recent.get("job_id") or "")
            fname = str(recent.get("filename") or "workbook")
            rstatus = str(recent.get("status") or "")
            href = url(f"{source_docs_inspector_path(source)}?job_id={rid}")
            items += (
                f'<li><a href="{escape(href)}">{escape(fname)}</a> '
                f'<span class="spreadsheet-job-status">({escape(rstatus)})</span></li>'
            )
        body += f'<ul class="spreadsheet-job-list"><li><strong>Recent jobs</strong></li>{items}</ul>'

    body += "</section>"

    body += """
      <section class="card" id="spreadsheet-engine-chat">
        <h2>Assistant</h2>
        <div class="governance-update-panel">
          <div class="assistant-chat-shell">
            <div class="assistant-chat">
    """
    body += _chat_html(job)
    body += """
            </div>
    """
    tables = list((report or {}).get("tables") or [])
    active_table = tables[table_index] if tables and 0 <= table_index < len(tables) else None
    table_id = str((active_table or {}).get("table_id") or "")
    body += _chat_form_html(
        url,
        source=source,
        job_id=job_id,
        table_id=table_id,
        disabled=not job_id or job_status not in {"ready", "parsed", "profiled"},
    )
    body += """
          </div>
        </div>
      </section>
    """

    if tables and job_status == "ready":
        body += _pagination_html(
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
        )
    elif job_id and job_status == "error":
        body += f'<div class="form-error">{escape(str((job or {}).get("error") or "Analysis failed."))}</div>'

    body += _styles()
    body += _dropzone_script()
    body += _status_poll_script(status_url, job_id)
    body += "</div>"
    return body
