"""Silver field semantics browser UI."""

from __future__ import annotations

import json
from typing import Any, Callable

from werkzeug.wrappers import Request, Response

from meshflow.dna.field_semantics import (
    draft_differs_from_production,
    ensure_field_semantics_seed,
    field_semantics_summary,
    load_field_semantics_draft,
    load_field_semantics_workflow,
    load_production_field_semantics,
    list_silver_entities,
)
from meshflow.dna.settings import DnaSettings
from meshflow.dna.web.portal.config import ClientPortalConfig
from meshflow.dna.web.portal.semantics.api import entity_detail_payload
from meshflow.dna.web.theme import empty_state, escape, page_header


SEMANTICS_ROOT = "/portal/semantics"
_PREVIEW_LIMIT = 5
_PREVIEW_COL_MAX_WIDTH = "3in"
_TAGGER_COL_WIDTHS = ("9rem", "10rem", "11rem", "12rem", "14rem")


def _scroll_table_width_expr(widths: tuple[str, ...]) -> str:
    return " + ".join(widths)


def semantics_section_nav(settings: DnaSettings | None) -> tuple[tuple[str, str], ...]:
    if settings is None:
        return ((SEMANTICS_ROOT, "No entities yet"),)
    entities = list_silver_entities(settings)
    if not entities:
        return ((SEMANTICS_ROOT, "No entities yet"),)
    return tuple((f"{SEMANTICS_ROOT}/{name}", name.replace("_", " ").title()) for name in entities)


def _preview_table_html(rows: list[dict[str, Any]], columns: list[str]) -> str:
    if not columns:
        return """
    <div class="semantics-preview-panel">
      <div class="empty semantics-preview-empty">
        <strong>No columns yet</strong>
        <span>This silver entity has no discoverable columns yet.</span>
      </div>
    </div>
    """
    headers = "".join(f"<th>{escape(column)}</th>" for column in columns)
    body_rows = ""
    preview_rows = [row for row in rows[:_PREVIEW_LIMIT] if isinstance(row, dict)]
    for row in preview_rows:
        cells = "".join(f"<td>{escape(row.get(column))}</td>" for column in columns)
        body_rows += f"<tr>{cells}</tr>"
    if not preview_rows:
        body_rows = f"""
        <tr class="semantics-preview-empty-row">
          <td colspan="{len(columns)}">
            <span class="muted">No silver rows yet — ingest and consolidate data to preview this entity.</span>
          </td>
        </tr>
        """
    for _ in range(max(0, _PREVIEW_LIMIT - len(preview_rows) - (1 if not preview_rows else 0))):
        cells = "".join("<td>&nbsp;</td>" for _ in columns)
        body_rows += f'<tr class="semantics-preview-placeholder">{cells}</tr>'
    return f"""
    <div class="semantics-preview-panel">
      <div class="semantics-scroll-host semantics-preview-scroll" tabindex="0" aria-label="Silver preview horizontal scroll">
        <table class="semantics-preview-table">
          <thead><tr>{headers}</tr></thead>
          <tbody>{body_rows}</tbody>
        </table>
      </div>
    </div>
    """


def _status_bar_html(
    *,
    workflow: dict[str, Any],
    draft_summary: dict[str, Any],
    differs: bool,
    is_admin: bool,
) -> str:
    active_version = workflow.get("active_version")
    production_label = f"v{escape(str(active_version))}" if active_version else "Not published"
    draft_badge = (
        '<span class="badge badge-warn">Draft differs from production</span>'
        if differs
        else '<span class="badge">Draft in sync</span>'
    )
    admin_actions = ""
    if is_admin:
        admin_actions = """
        <div class="semantics-actions">
          <button type="button" class="btn btn-secondary btn-sm" id="semantics-discard-draft">Discard</button>
          <button type="button" class="btn btn-sm" id="semantics-save-draft">Save</button>
          <button type="button" class="btn btn-primary btn-sm" id="semantics-publish">Publish</button>
        </div>
        """
    return f"""
    <div class="semantics-status-bar">
      <dl class="semantics-status-meta">
        <div><dt>Production pin</dt><dd>{production_label}</dd></div>
        <div><dt>Mappings</dt><dd>{draft_summary.get("mapping_count", 0)}</dd></div>
        <div><dt>Entities</dt><dd>{draft_summary.get("entity_count", 0)}</dd></div>
        <div><dt>Custom tags</dt><dd>{draft_summary.get("custom_concept_count", 0)}</dd></div>
        <div><dt>Status</dt><dd>{draft_badge}</dd></div>
      </dl>
      {admin_actions}
      <div id="semantics-status-message" class="form-success semantics-status-flash" style="display:none"></div>
      <div id="semantics-status-error" class="form-error semantics-status-flash" style="display:none"></div>
    </div>
    """


def _chip_html(concept_id: str, label: str, *, is_admin: bool) -> str:
    remove_btn = ""
    if is_admin:
        remove_btn = (
            f'<button type="button" class="semantics-chip-remove" '
            f'aria-label="Remove {escape(label)}" title="Remove tag">&times;</button>'
        )
    return (
        f'<span class="semantics-chip" data-concept="{escape(concept_id)}">'
        f'<span class="semantics-chip-label">{escape(label)}</span>{remove_btn}</span>'
    )


def _column_tagger_html(
    columns: list[dict[str, Any]],
    *,
    is_admin: bool,
) -> str:
    if not columns:
        return empty_state("No columns found", "This silver entity has no discoverable columns yet.")
    rows = ""
    for item in columns:
        column = str(item.get("column") or "")
        sample = str(item.get("sample_value") or "—")
        concepts = item.get("concepts") or []
        chips = "".join(
            _chip_html(str(concept), str(concept), is_admin=is_admin)
            for concept in concepts
        )
        disabled = "" if is_admin else " disabled"
        rows += f"""
        <tr data-column="{escape(column)}">
          <td><code>{escape(column)}</code></td>
          <td class="semantics-sample">{escape(sample)}</td>
          <td><div class="semantics-chip-row">{chips or '<span class="muted">No tags</span>'}</div></td>
          <td>
            <select class="semantics-concept-select"{disabled}
              data-column="{escape(column)}">
              <option value="">Add tag…</option>
            </select>
          </td>
          <td>
            <input type="text" class="semantics-notes-input" value="{escape(str(item.get('notes') or ''))}"
              placeholder="Optional notes"{disabled} data-column="{escape(column)}">
          </td>
        </tr>
        """
    readonly_note = "" if is_admin else '<p class="muted">Read-only — admin access required to edit tags.</p>'
    colgroup = "".join(
        f'<col style="width:{width};" />' for width in _TAGGER_COL_WIDTHS
    )
    table_width = f"calc({_scroll_table_width_expr(_TAGGER_COL_WIDTHS)})"
    return f"""
    {readonly_note}
    <div class="semantics-tagger-panel">
      <div class="semantics-scroll-host semantics-tagger-scroll" tabindex="0" aria-label="Column tags scroll">
        <table class="semantics-tagger-table" id="semantics-tagger-table" style="width: {table_width};">
          <colgroup>{colgroup}</colgroup>
          <thead>
            <tr>
              <th>Column</th>
              <th>Sample value</th>
              <th>Tags</th>
              <th>Add tags</th>
              <th>Notes</th>
            </tr>
          </thead>
          <tbody>{rows}</tbody>
        </table>
      </div>
    </div>
    """


def _custom_tag_form_html(*, is_admin: bool) -> str:
    if not is_admin:
        return ""
    return """
    <section class="section semantics-custom-tag">
      <div class="section-title">Create custom tag</div>
      <div class="card">
        <div class="form-field">
          <label for="semantics-custom-label">Label</label>
          <input id="semantics-custom-label" type="text" placeholder="e.g. Freight allocation">
        </div>
        <div class="form-field">
          <label for="semantics-custom-category">Category</label>
          <input id="semantics-custom-category" type="text" placeholder="e.g. cost">
        </div>
        <button type="button" class="btn btn-secondary" id="semantics-add-custom-tag">Add custom tag</button>
      </div>
    </section>
    """


def _semantics_script(*, is_admin: bool, entity: str, api_root: str) -> str:
    return f"""
<script>
(function() {{
  var apiRoot = {json.dumps(api_root)};
  var currentEntity = {json.dumps(entity)};
  var isAdmin = {json.dumps(is_admin)};
  var conceptsCache = null;
  var draftCache = null;

  function showMessage(text, isError) {{
    var ok = document.getElementById("semantics-status-message");
    var err = document.getElementById("semantics-status-error");
    if (!ok || !err) return;
    ok.style.display = isError ? "none" : "block";
    err.style.display = isError ? "block" : "none";
    (isError ? err : ok).textContent = text || "";
  }}

  function fetchJson(url, options) {{
    return fetch(url, options || {{}}).then(function(resp) {{
      return resp.json().then(function(data) {{
        if (!resp.ok) throw new Error((data && data.error) || resp.statusText);
        return data;
      }});
    }});
  }}

  function conceptLabel(concept) {{
    return concept.label || concept.id || "";
  }}

  function selectedConceptsForRow(row) {{
    var concepts = [];
    row.querySelectorAll(".semantics-chip").forEach(function(chip) {{
      concepts.push(chip.getAttribute("data-concept"));
    }});
    return concepts;
  }}

  function renderChips(row, concepts) {{
    var chipRow = row.querySelector(".semantics-chip-row");
    if (!chipRow) return;
    if (!concepts.length) {{
      chipRow.innerHTML = '<span class="muted">No tags</span>';
      return;
    }}
    chipRow.innerHTML = concepts.map(function(conceptId) {{
      var concept = (conceptsCache.concepts || []).concat(conceptsCache.custom_concepts || [])
        .find(function(item) {{ return item.id === conceptId; }});
      var label = concept ? conceptLabel(concept) : conceptId;
      var removeBtn = isAdmin
        ? '<button type="button" class="semantics-chip-remove" aria-label="Remove tag" title="Remove tag">&times;</button>'
        : "";
      return '<span class="semantics-chip" data-concept="' + conceptId + '">'
        + '<span class="semantics-chip-label">' + label + '</span>'
        + removeBtn
        + '</span>';
    }}).join("");
  }}

  function removeConceptFromRow(row, conceptId) {{
    if (!conceptId) return;
    var concepts = selectedConceptsForRow(row).filter(function(id) {{
      return id !== conceptId;
    }});
    renderChips(row, concepts);
    populateConceptSelects();
  }}

  function addConceptToRow(row, conceptId) {{
    if (!conceptId) return;
    var concepts = selectedConceptsForRow(row);
    if (concepts.indexOf(conceptId) >= 0) return;
    concepts.push(conceptId);
    renderChips(row, concepts);
    populateConceptSelects();
  }}

  function populateConceptSelects() {{
    if (!conceptsCache) return;
    var allConcepts = (conceptsCache.concepts || []).concat(conceptsCache.custom_concepts || []);
    document.querySelectorAll(".semantics-concept-select").forEach(function(select) {{
      var column = select.getAttribute("data-column");
      var row = document.querySelector('tr[data-column="' + column + '"]');
      var selected = row ? selectedConceptsForRow(row) : [];
      var previous = select.value;
      select.innerHTML = '<option value="">Add tag…</option>';
      allConcepts.forEach(function(concept) {{
        if (selected.indexOf(concept.id) >= 0) return;
        var option = document.createElement("option");
        option.value = concept.id;
        option.textContent = conceptLabel(concept);
        select.appendChild(option);
      }});
      if (previous && selected.indexOf(previous) < 0) {{
        select.value = previous;
      }}
    }});
  }}

  function collectMappingsFromUi() {{
    var mappings = [];
    document.querySelectorAll("#semantics-tagger-table tbody tr").forEach(function(row) {{
      var column = row.getAttribute("data-column");
      if (!column) return;
      var notesInput = row.querySelector(".semantics-notes-input");
      var concepts = selectedConceptsForRow(row);
      if (!concepts.length) return;
      mappings.push({{
        silver_entity: currentEntity,
        column: column,
        concepts: concepts,
        notes: notesInput ? notesInput.value : ""
      }});
    }});
    return mappings;
  }}

  function buildDraftPayload() {{
    var base = draftCache && draftCache.draft ? draftCache.draft : {{}};
    var otherMappings = (base.mappings || []).filter(function(item) {{
      return item.silver_entity !== currentEntity;
    }});
    return {{
      version: base.version || "1.0.0",
      status: "draft",
      source: base.source,
      custom_concepts: base.custom_concepts || [],
      mappings: otherMappings.concat(collectMappingsFromUi())
    }};
  }}

  function refreshDraft() {{
    return fetchJson(apiRoot + "/draft").then(function(data) {{
      draftCache = data;
      return data;
    }});
  }}

  function refreshChipLabels() {{
    document.querySelectorAll("#semantics-tagger-table tbody tr").forEach(function(row) {{
      renderChips(row, selectedConceptsForRow(row));
    }});
  }}

  function loadConcepts() {{
    return fetchJson(apiRoot + "/concepts").then(function(data) {{
      conceptsCache = data;
      refreshChipLabels();
      populateConceptSelects();
      return data;
    }});
  }}

  function saveDraft() {{
    if (!isAdmin) return;
    var payload = buildDraftPayload();
    fetchJson(apiRoot + "/draft", {{
      method: "PUT",
      headers: {{ "Content-Type": "application/json" }},
      body: JSON.stringify(payload)
    }}).then(function(data) {{
      draftCache = {{ draft: data.draft, draft_differs_from_production: data.draft_differs_from_production }};
      showMessage("Draft saved.", false);
    }}).catch(function(err) {{
      showMessage(err.message || "Save failed", true);
    }});
  }}

  function publishDraft() {{
    if (!isAdmin) return;
    saveDraft();
    fetchJson(apiRoot + "/publish", {{ method: "POST" }}).then(function(data) {{
      showMessage("Published v" + (data.version || ""), false);
      refreshDraft();
    }}).catch(function(err) {{
      showMessage(err.message || "Publish failed", true);
    }});
  }}

  function discardDraft() {{
    if (!isAdmin) return;
    fetchJson(apiRoot + "/discard", {{ method: "POST" }}).then(function() {{
      window.location.reload();
    }}).catch(function(err) {{
      showMessage(err.message || "Discard failed", true);
    }});
  }}

  var saveBtn = document.getElementById("semantics-save-draft");
  var publishBtn = document.getElementById("semantics-publish");
  var discardBtn = document.getElementById("semantics-discard-draft");
  if (saveBtn) saveBtn.addEventListener("click", saveDraft);
  if (publishBtn) publishBtn.addEventListener("click", publishDraft);
  if (discardBtn) discardBtn.addEventListener("click", discardDraft);

  document.querySelectorAll(".semantics-concept-select").forEach(function(select) {{
    select.addEventListener("change", function() {{
      var column = select.getAttribute("data-column");
      var row = document.querySelector('tr[data-column="' + column + '"]');
      if (!row || !select.value) return;
      addConceptToRow(row, select.value);
      select.value = "";
    }});
  }});

  var taggerTable = document.getElementById("semantics-tagger-table");
  if (taggerTable && isAdmin) {{
    taggerTable.addEventListener("click", function(event) {{
      var btn = event.target.closest(".semantics-chip-remove");
      if (!btn) return;
      event.preventDefault();
      var chip = btn.closest(".semantics-chip");
      var row = btn.closest("tr[data-column]");
      if (!chip || !row) return;
      removeConceptFromRow(row, chip.getAttribute("data-concept"));
    }});
  }}

  var addCustomBtn = document.getElementById("semantics-add-custom-tag");
  if (addCustomBtn) {{
    addCustomBtn.addEventListener("click", function() {{
      var labelInput = document.getElementById("semantics-custom-label");
      var categoryInput = document.getElementById("semantics-custom-category");
      var label = labelInput ? labelInput.value.trim() : "";
      var category = categoryInput ? categoryInput.value.trim().toLowerCase() : "";
      if (!label || !category) {{
        showMessage("Label and category are required for a custom tag.", true);
        return;
      }}
      fetchJson(apiRoot + "/custom-concepts", {{
        method: "POST",
        headers: {{ "Content-Type": "application/json" }},
        body: JSON.stringify({{ label: label, category: category }})
      }}).then(function() {{
        if (labelInput) labelInput.value = "";
        loadConcepts();
        showMessage("Custom tag added.", false);
      }}).catch(function(err) {{
        showMessage(err.message || "Could not add custom tag", true);
      }});
    }});
  }}

  document.querySelectorAll(".semantics-preview-scroll").forEach(function(previewScroll) {{
    previewScroll.addEventListener("wheel", function(event) {{
      if (previewScroll.scrollWidth <= previewScroll.clientWidth) return;
      if (Math.abs(event.deltaY) <= Math.abs(event.deltaX)) return;
      event.preventDefault();
      previewScroll.scrollLeft += event.deltaY;
    }}, {{ passive: false }});
  }});

  loadConcepts();
  refreshDraft();
}})();
</script>
<style>
.semantics-page {{
  max-width: 100%;
  min-width: 0;
}}
.semantics-page-header {{
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem 1.5rem;
  margin-bottom: 1.35rem;
  flex-wrap: wrap;
}}
.semantics-page-header .page-header {{
  margin-bottom: 0;
  flex: 1 1 16rem;
  min-width: 0;
}}
.semantics-status-bar {{
  flex: 0 1 22rem;
  min-width: 0;
  padding: 0.65rem 0.85rem;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: rgba(255, 255, 255, 0.02);
}}
.semantics-status-meta {{
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.35rem 0.75rem;
  margin: 0;
}}
.semantics-status-meta div {{ min-width: 0; }}
.semantics-status-meta dt {{
  font-size: 0.62rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-dim);
  margin-bottom: 0.1rem;
}}
.semantics-status-meta dd {{
  margin: 0;
  font-size: 0.78rem;
  color: var(--text-muted);
  line-height: 1.3;
}}
.semantics-status-bar .semantics-actions {{
  display: flex;
  gap: 0.35rem;
  flex-wrap: wrap;
  margin-top: 0.55rem;
}}
.semantics-status-bar .btn-sm {{
  padding: 0.3rem 0.6rem;
  font-size: 0.72rem;
  min-height: auto;
}}
.semantics-status-flash {{
  margin: 0.45rem 0 0;
  font-size: 0.78rem;
}}
.badge-warn {{
  border-color: rgba(245, 158, 11, 0.35);
  color: #fcd34d;
  background: rgba(245, 158, 11, 0.08);
}}
.semantics-layout {{
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 1.25rem;
  max-width: 100%;
  min-width: 0;
}}
.semantics-layout > .section {{
  min-width: 0;
  max-width: 100%;
}}
.semantics-column-tags,
.semantics-silver-preview {{
  min-width: 0;
  max-width: 100%;
}}
.semantics-scroll-host {{
  display: block;
  width: 100%;
  max-width: 100%;
  min-width: 0;
  overflow: auto;
  contain: inline-size;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  -webkit-overflow-scrolling: touch;
  scrollbar-gutter: stable;
}}
.semantics-page .semantics-scroll-host > table {{
  margin: 0;
  border-collapse: collapse;
  font-size: 0.84rem;
}}
.semantics-page .semantics-scroll-host > table.semantics-tagger-table {{
  table-layout: fixed;
}}
.semantics-page .semantics-scroll-host > table.semantics-preview-table {{
  table-layout: auto;
  width: max-content;
  min-width: 100%;
}}
.semantics-tagger-panel,
.semantics-preview-panel {{
  width: 100%;
  max-width: 100%;
  min-width: 0;
}}
.semantics-tagger-scroll {{
  max-height: calc(2.45rem * 8 + 2.4rem);
}}
.semantics-tagger-table thead th,
.semantics-tagger-table tbody td {{
  overflow: hidden;
  text-overflow: ellipsis;
  vertical-align: top;
}}
.semantics-tagger-table th:nth-child(3),
.semantics-tagger-table td:nth-child(3) {{
  white-space: normal;
  overflow: visible;
}}
.semantics-tagger-table td code {{
  word-break: break-all;
  white-space: normal;
}}
.semantics-preview-scroll {{
  height: calc(2.15rem * 5 + 2.35rem);
  overflow-y: hidden;
  overflow-x: auto;
}}
.semantics-preview-table thead th,
.semantics-preview-table tbody td {{
  max-width: {_PREVIEW_COL_MAX_WIDTH};
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}}
.semantics-preview-table tbody tr {{
  height: 2.15rem;
}}
.semantics-preview-table tbody td {{
  padding-top: 0.35rem;
  padding-bottom: 0.35rem;
}}
.semantics-preview-empty {{
  height: calc(2.15rem * 5 + 2.35rem);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 1rem;
  border: 1px dashed var(--border);
  border-radius: var(--radius);
}}
.semantics-preview-empty-row td {{
  text-align: center;
  color: var(--text-muted);
  font-size: 0.84rem;
}}
.semantics-preview-placeholder td {{
  color: transparent;
}}
.semantics-chip-row {{
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.3rem;
}}
.semantics-chip {{
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  padding: 0.15rem 0.3rem 0.15rem 0.5rem;
  border-radius: 999px;
  background: rgba(99,102,241,0.12);
  font-size: 0.82rem;
  max-width: 100%;
}}
.semantics-chip-label {{
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}}
.semantics-chip-remove {{
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 1rem;
  height: 1rem;
  padding: 0;
  margin: 0;
  border: none;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.08);
  color: var(--text-muted);
  font-size: 0.85rem;
  line-height: 1;
  cursor: pointer;
  font: inherit;
}}
.semantics-chip-remove:hover {{
  background: rgba(239, 68, 68, 0.22);
  color: #fca5a5;
}}
.semantics-concept-select {{
  width: 100%;
  min-width: 0;
  padding: 0.45rem 0.65rem;
  border-radius: var(--radius-sm);
  border: 1px solid rgba(56, 189, 248, 0.28);
  background: rgba(8, 18, 40, 0.95);
  color: var(--text);
  font: inherit;
  font-size: 0.84rem;
}}
.semantics-concept-select option {{
  background: #0a1628;
  color: var(--text);
}}
.semantics-concept-select:focus {{
  outline: none;
  border-color: rgba(56, 189, 248, 0.45);
  box-shadow: 0 0 0 3px rgba(56, 189, 248, 0.12);
}}
.semantics-notes-input {{
  width: 100%;
  min-width: 0;
  padding: 0.45rem 0.65rem;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
  background: rgba(255,255,255,0.03);
  color: var(--text);
  font: inherit;
  font-size: 0.84rem;
}}
.semantics-notes-input:focus {{
  outline: none;
  border-color: rgba(56, 189, 248, 0.45);
  box-shadow: 0 0 0 3px rgba(56, 189, 248, 0.12);
}}
.semantics-sample {{
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 12rem;
}}
.semantics-custom-tag .form-field:last-of-type {{
  margin-bottom: 1rem;
}}
.semantics-custom-tag #semantics-add-custom-tag {{
  margin-top: 0.15rem;
}}
.muted {{ color: var(--text-muted); }}
@media (max-width: 900px) {{
  .semantics-page-header {{
    flex-direction: column;
  }}
  .semantics-status-bar {{
    flex: 1 1 auto;
    width: 100%;
  }}
}}
</style>
"""


def render_semantics_page(
    request: Request,
    *,
    settings: DnaSettings,
    client: ClientPortalConfig,
    entity: str = "",
    is_admin: bool = False,
    html_response: Callable[..., Response],
    message: str = "",
    error: str = "",
) -> Response:
    ensure_field_semantics_seed(settings)
    entities = list_silver_entities(settings)
    entity_name = entity.strip().lower()
    if not entity_name and entities:
        entity_name = entities[0]

    workflow = load_field_semantics_workflow(settings)
    production = load_production_field_semantics(settings)
    draft = load_field_semantics_draft(settings)
    draft_summary = field_semantics_summary(draft)
    differs = draft_differs_from_production(settings)

    url: Callable[[str], str] = lambda path: f"{request.script_root}{path if path.startswith('/') else f'/{path}'}"
    api_root = url("/api/semantics")

    title = entity_name.replace("_", " ").title() if entity_name else "Field Semantics"
    status_bar = _status_bar_html(
        workflow=workflow,
        draft_summary=draft_summary,
        differs=differs,
        is_admin=is_admin,
    )
    body = f"""
    <div class="semantics-page">
    <div class="semantics-page-header">
      {page_header(
          "Field Semantics",
          "Tag silver columns with operational business concepts for the Config Assistant.",
          eyebrow="Silver layer",
      )}
      {status_bar}
    </div>
    """
    if message:
        body += f'<div class="form-success">{escape(message)}</div>'
    if error:
        body += f'<div class="form-error">{escape(error)}</div>'

    if not entities:
        body += empty_state(
            "No silver entities configured",
            "Connect and ingest a data source to browse silver tables here.",
        )
        body += "</div>"
        return html_response(
            request,
            client=client,
            title="Field Semantics",
            active_path=SEMANTICS_ROOT,
            body=body,
            is_admin=is_admin,
            settings=settings,
        )

    if entity_name and entity_name not in entities:
        return Response("Not found", status=404, mimetype="text/plain")

    if not entity_name:
        target = f"{SEMANTICS_ROOT}/{entities[0]}"
        return Response(
            status=302,
            headers={"Location": f"{request.script_root}{target}"},
        )

    detail = entity_detail_payload(settings, entity_name)
    columns = detail.get("columns") or []
    preview_rows = detail.get("preview_rows") or []
    preview_columns = [str(item.get("column") or "") for item in columns]

    body += f"""
    <div class="semantics-layout">
      <section class="section semantics-column-tags">
        <div class="section-title">Column tags</div>
        {_column_tagger_html(columns, is_admin=is_admin)}
      </section>
      <section class="section semantics-silver-preview">
        <div class="section-title">Silver preview · {escape(entity_name)}</div>
        {_preview_table_html(preview_rows, preview_columns)}
      </section>
    </div>
    """
    body += _custom_tag_form_html(is_admin=is_admin)
    body += "</div>"
    body += _semantics_script(is_admin=is_admin, entity=entity_name, api_root=api_root)

    return html_response(
        request,
        client=client,
        title=title,
        active_path=f"{SEMANTICS_ROOT}/{entity_name}",
        body=body,
        is_admin=is_admin,
        settings=settings,
    )


def field_semantics_governance_card_html(
    *,
    url: Callable[[str], str],
    settings: DnaSettings,
) -> str:
    ensure_field_semantics_seed(settings)
    workflow = load_field_semantics_workflow(settings)
    production = load_production_field_semantics(settings)
    draft = load_field_semantics_draft(settings)
    draft_summary = field_semantics_summary(draft)
    production_summary = field_semantics_summary(production) if production else None
    differs = draft_differs_from_production(settings)
    active_version = workflow.get("active_version")
    pin_label = f"v{escape(str(active_version))}" if active_version else "Not published"
    warn = (
        '<p class="form-error" style="margin-top:0.5rem">Draft has unpublished tag changes.</p>'
        if differs
        else ""
    )
    prod_mappings = (production_summary or {}).get("mapping_count", 0)
    return f"""
    <section class="section">
      <div class="section-title">Field semantics</div>
      <div class="card pack-card">
        <p class="pack-card-lead">Operational concept tags on silver columns — referenced by the Config Assistant.</p>
        <dl class="pack-meta">
          <div><dt>Production pin</dt><dd>{pin_label}</dd></div>
          <div><dt>Published mappings</dt><dd>{prod_mappings}</dd></div>
          <div><dt>Draft mappings</dt><dd>{draft_summary.get("mapping_count", 0)}</dd></div>
          <div><dt>Entities tagged</dt><dd>{draft_summary.get("entity_count", 0)}</dd></div>
        </dl>
        {warn}
        <p style="margin-top:0.75rem">
          <a class="btn btn-secondary" href="{escape(url('/portal/semantics'))}">Edit in Semantics browser</a>
        </p>
      </div>
    </section>
    """
