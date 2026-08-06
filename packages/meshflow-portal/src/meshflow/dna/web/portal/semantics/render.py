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
_PREVIEW_LIMIT = 15


def semantics_section_nav(settings: DnaSettings | None) -> tuple[tuple[str, str], ...]:
    if settings is None:
        return ((SEMANTICS_ROOT, "No entities yet"),)
    entities = list_silver_entities(settings)
    if not entities:
        return ((SEMANTICS_ROOT, "No entities yet"),)
    return tuple((f"{SEMANTICS_ROOT}/{name}", name.replace("_", " ").title()) for name in entities)


def _preview_table_html(rows: list[dict[str, Any]], columns: list[str]) -> str:
    if not rows or not columns:
        return empty_state(
            "No silver rows yet",
            "Ingest and consolidate data to preview this entity.",
        )
    headers = "".join(f"<th>{escape(column)}</th>" for column in columns)
    body_rows = ""
    for row in rows[:_PREVIEW_LIMIT]:
        if not isinstance(row, dict):
            continue
        cells = "".join(f"<td>{escape(row.get(column))}</td>" for column in columns)
        body_rows += f"<tr>{cells}</tr>"
    return f"""
    <div class="table-wrap">
      <table class="data-table semantics-preview-table">
        <thead><tr>{headers}</tr></thead>
        <tbody>{body_rows}</tbody>
      </table>
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
          <button type="button" class="btn btn-secondary" id="semantics-discard-draft">Discard draft</button>
          <button type="button" class="btn" id="semantics-save-draft">Save draft</button>
          <button type="button" class="btn btn-primary" id="semantics-publish">Publish</button>
        </div>
        """
    return f"""
    <div class="card semantics-status-bar">
      <dl class="pack-meta semantics-status-meta">
        <div><dt>Production pin</dt><dd>{production_label}</dd></div>
        <div><dt>Mappings</dt><dd>{draft_summary.get("mapping_count", 0)} tagged columns</dd></div>
        <div><dt>Entities</dt><dd>{draft_summary.get("entity_count", 0)} with tags</dd></div>
        <div><dt>Custom tags</dt><dd>{draft_summary.get("custom_concept_count", 0)}</dd></div>
        <div><dt>Status</dt><dd>{draft_badge}</dd></div>
      </dl>
      {admin_actions}
      <div id="semantics-status-message" class="form-success" style="display:none"></div>
      <div id="semantics-status-error" class="form-error" style="display:none"></div>
    </div>
    """


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
            f'<span class="semantics-chip" data-concept="{escape(str(concept))}">{escape(str(concept))}</span>'
            for concept in concepts
        )
        disabled = "" if is_admin else " disabled"
        rows += f"""
        <tr data-column="{escape(column)}">
          <td><code>{escape(column)}</code></td>
          <td class="semantics-sample">{escape(sample)}</td>
          <td><div class="semantics-chip-row">{chips or '<span class="muted">No tags</span>'}</div></td>
          <td>
            <select class="semantics-concept-select" multiple size="4"{disabled}
              data-column="{escape(column)}"></select>
          </td>
          <td>
            <input type="text" class="semantics-notes-input" value="{escape(str(item.get('notes') or ''))}"
              placeholder="Optional notes"{disabled} data-column="{escape(column)}">
          </td>
        </tr>
        """
    readonly_note = "" if is_admin else '<p class="muted">Read-only — admin access required to edit tags.</p>'
    return f"""
    {readonly_note}
    <div class="table-wrap">
      <table class="data-table semantics-tagger-table" id="semantics-tagger-table">
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
    """


def _custom_tag_form_html(*, is_admin: bool) -> str:
    if not is_admin:
        return ""
    return """
    <section class="section semantics-custom-tag">
      <div class="section-title">Create custom tag</div>
      <div class="card">
        <div class="form-row">
          <label for="semantics-custom-label">Label</label>
          <input id="semantics-custom-label" type="text" placeholder="e.g. Freight allocation">
        </div>
        <div class="form-row">
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

  function populateConceptSelects() {{
    if (!conceptsCache) return;
    var allConcepts = (conceptsCache.concepts || []).concat(conceptsCache.custom_concepts || []);
    document.querySelectorAll(".semantics-concept-select").forEach(function(select) {{
      var column = select.getAttribute("data-column");
      var row = document.querySelector('tr[data-column="' + column + '"]');
      var selected = [];
      if (row) {{
        row.querySelectorAll(".semantics-chip").forEach(function(chip) {{
          selected.push(chip.getAttribute("data-concept"));
        }});
      }}
      select.innerHTML = "";
      allConcepts.forEach(function(concept) {{
        var option = document.createElement("option");
        option.value = concept.id;
        option.textContent = concept.label + " (" + concept.id + ")";
        if (selected.indexOf(concept.id) >= 0) option.selected = true;
        select.appendChild(option);
      }});
    }});
  }}

  function collectMappingsFromUi() {{
    var mappings = [];
    document.querySelectorAll("#semantics-tagger-table tbody tr").forEach(function(row) {{
      var column = row.getAttribute("data-column");
      var select = row.querySelector(".semantics-concept-select");
      var notesInput = row.querySelector(".semantics-notes-input");
      var concepts = [];
      if (select) {{
        Array.prototype.forEach.call(select.selectedOptions, function(opt) {{
          concepts.push(opt.value);
        }});
      }}
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

  function loadConcepts() {{
    return fetchJson(apiRoot + "/concepts").then(function(data) {{
      conceptsCache = data;
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

  loadConcepts();
  refreshDraft();
}})();
</script>
<style>
.semantics-layout {{ display: grid; grid-template-columns: 1fr; gap: 1.25rem; }}
@media (min-width: 1100px) {{
  .semantics-layout {{ grid-template-columns: 1.2fr 1fr; }}
}}
.semantics-status-bar .semantics-actions {{ display: flex; gap: 0.5rem; flex-wrap: wrap; margin-top: 0.75rem; }}
.semantics-chip-row {{ display: flex; flex-wrap: wrap; gap: 0.35rem; }}
.semantics-chip {{
  display: inline-block; padding: 0.15rem 0.45rem; border-radius: 999px;
  background: rgba(99,102,241,0.12); font-size: 0.82rem;
}}
.semantics-concept-select {{ min-width: 12rem; max-width: 100%; }}
.semantics-sample {{ max-width: 14rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
.muted {{ color: var(--muted, #6b7280); }}
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
    body = page_header(
        "Field Semantics",
        "Tag silver columns with operational business concepts for the Config Assistant.",
        eyebrow="Silver layer",
    )
    if message:
        body += f'<div class="form-success">{escape(message)}</div>'
    if error:
        body += f'<div class="form-error">{escape(error)}</div>'

    body += _status_bar_html(
        workflow=workflow,
        draft_summary=draft_summary,
        differs=differs,
        is_admin=is_admin,
    )

    if not entities:
        body += empty_state(
            "No silver entities configured",
            "Connect and ingest a data source to browse silver tables here.",
        )
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
      <section class="section">
        <div class="section-title">Silver preview · {escape(entity_name)}</div>
        {_preview_table_html(preview_rows, preview_columns)}
      </section>
      <section class="section">
        <div class="section-title">Column tags</div>
        {_column_tagger_html(columns, is_admin=is_admin)}
      </section>
    </div>
    """
    body += _custom_tag_form_html(is_admin=is_admin)
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
