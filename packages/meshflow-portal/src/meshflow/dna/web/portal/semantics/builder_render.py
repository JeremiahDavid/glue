"""Semantic Builder portal — overview, join review, and publish workflow."""

from __future__ import annotations

import json
from typing import Any, Callable

from werkzeug.wrappers import Request, Response

from meshflow.dna.semantic_model import (
    draft_differs_from_production,
    ensure_semantic_model_seed,
    evaluate_publish_readiness,
    load_production_semantic_model,
    load_semantic_model_draft,
    load_semantic_model_workflow,
    semantic_model_coverage,
)
from meshflow.dna.settings import DnaSettings
from meshflow.dna.web.portal.config import ClientPortalConfig
from meshflow.dna.web.portal.dna_nav import SEMANTIC_BUILDER_ROOT, SEMANTICS_ROOT
from meshflow.dna.web.portal.semantics.model_api import graph_view_payload
from meshflow.dna.web.theme import empty_state, escape, page_header

_ROLE_LABELS = {
    "fact": "Fact",
    "dimension": "Dimension",
    "bridge": "Bridge",
    "reference": "Reference",
}

_STATUS_CLASS = {
    "proposed": "semantics-status-proposed",
    "approved": "semantics-status-approved",
    "rejected": "semantics-status-rejected",
    "open": "semantics-status-proposed",
    "resolved": "semantics-status-approved",
}


def _status_badge(status: str) -> str:
    key = status.strip().lower()
    css = _STATUS_CLASS.get(key, "semantics-status-proposed")
    return f'<span class="semantics-status-badge {css}">{escape(key)}</span>'


def _coverage_cards(coverage: dict[str, Any], readiness: dict[str, Any]) -> str:
    ratio = int(float(coverage.get("attribute_tag_ratio") or 0) * 100)
    ready = readiness.get("ready")
    ready_label = "Ready to publish" if ready else "Not ready"
    ready_class = "semantics-ready-yes" if ready else "semantics-ready-no"
    return f"""
    <div class="semantic-builder-coverage">
      <div class="semantic-builder-stat">
        <span class="semantic-builder-stat-value">{coverage.get("entity_approved", 0)}</span>
        <span class="semantic-builder-stat-label">Entities approved</span>
        <span class="semantic-builder-stat-sub">{coverage.get("entity_proposed", 0)} proposed</span>
      </div>
      <div class="semantic-builder-stat">
        <span class="semantic-builder-stat-value">{coverage.get("relationship_approved", 0)}</span>
        <span class="semantic-builder-stat-label">Joins approved</span>
        <span class="semantic-builder-stat-sub">{coverage.get("relationship_proposed", 0)} proposed</span>
      </div>
      <div class="semantic-builder-stat">
        <span class="semantic-builder-stat-value">{ratio}%</span>
        <span class="semantic-builder-stat-label">Columns tagged</span>
        <span class="semantic-builder-stat-sub">{coverage.get("tagged_column_count", 0)} columns</span>
      </div>
      <div class="semantic-builder-stat">
        <span class="semantic-builder-stat-value {ready_class}">{escape(ready_label)}</span>
        <span class="semantic-builder-stat-label">Publish readiness</span>
        <span class="semantic-builder-stat-sub">{coverage.get("open_blocking_questions", 0)} blocking questions</span>
      </div>
    </div>
    """


def _readiness_errors(readiness: dict[str, Any]) -> str:
    errors = readiness.get("errors") or []
    if not errors:
        return ""
    items = "".join(f"<li>{escape(str(err))}</li>" for err in errors)
    return f'<div class="form-error semantic-builder-errors"><ul>{items}</ul></div>'


def _entities_table(entities: list[dict[str, Any]], *, is_admin: bool) -> str:
    if not entities:
        return empty_state("No entities yet", "Run semantic init to propose entities from your silver tables.")
    rows = ""
    for entity in entities:
        if not isinstance(entity, dict):
            continue
        ent_id = str(entity.get("id") or "")
        silver = str(entity.get("silver_entity") or "")
        role = _ROLE_LABELS.get(str(entity.get("role") or ""), str(entity.get("role") or ""))
        status = str(entity.get("status") or "proposed")
        desc = str(entity.get("description") or "")
        actions = ""
        if is_admin and status == "proposed":
            actions = f"""
            <button type="button" class="btn btn-primary btn-sm" data-entity-approve="{escape(ent_id)}">Approve</button>
            <button type="button" class="btn btn-secondary btn-sm" data-entity-reject="{escape(ent_id)}">Reject</button>
            """
        rows += f"""
        <tr>
          <td><code>{escape(silver)}</code></td>
          <td>{escape(role)}</td>
          <td>{_status_badge(status)}</td>
          <td>{escape(desc)}</td>
          <td>{actions}</td>
        </tr>
        """
    return f"""
    <section class="section">
      <div class="section-title">Entities ({len([e for e in entities if isinstance(e, dict)])})</div>
      <div class="table-wrap semantic-builder-scroll">
        <table class="semantic-builder-table">
          <thead>
            <tr><th>Silver table</th><th>Role</th><th>Status</th><th>Description</th><th></th></tr>
          </thead>
          <tbody>{rows}</tbody>
        </table>
      </div>
    </section>
    """


def _relationships_table(relationships: list[dict[str, Any]], *, is_admin: bool) -> str:
    if not relationships:
        return ""
    rows = ""
    for rel in relationships:
        if not isinstance(rel, dict):
            continue
        rel_id = str(rel.get("id") or "")
        label = (
            f"{rel.get('from_entity')}.{rel.get('from_column')} → "
            f"{rel.get('to_entity')}.{rel.get('to_column')}"
        )
        status = str(rel.get("status") or "proposed")
        citation = str(rel.get("citation") or rel.get("description") or "")
        actions = ""
        if is_admin and status == "proposed":
            actions = f"""
            <button type="button" class="btn btn-primary btn-sm" data-rel-approve="{escape(rel_id)}">Approve</button>
            <button type="button" class="btn btn-secondary btn-sm" data-rel-reject="{escape(rel_id)}">Reject</button>
            """
        rows += f"""
        <tr>
          <td><code>{escape(label)}</code></td>
          <td>{escape(str(rel.get("cardinality") or ""))}</td>
          <td>{_status_badge(status)}</td>
          <td class="semantic-builder-citation">{escape(citation)}</td>
          <td class="semantic-builder-actions">{actions}</td>
        </tr>
        """
    return f"""
    <section class="section">
      <div class="section-title">Relationships</div>
      <p class="pack-card-lead">Review proposed joins between silver tables before gold compile.</p>
      <div class="table-wrap">
        <table class="semantic-builder-table">
          <thead>
            <tr><th>Join</th><th>Cardinality</th><th>Status</th><th>Source</th><th></th></tr>
          </thead>
          <tbody>{rows}</tbody>
        </table>
      </div>
    </section>
    """


def _graph_section(settings: DnaSettings, *, api_root: str) -> str:
    graph_data = graph_view_payload(settings)
    svg = str(graph_data.get("svg") or "")
    edge_count = len((graph_data.get("graph") or {}).get("edges") or [])
    node_count = len((graph_data.get("graph") or {}).get("nodes") or [])
    if not node_count:
        return ""

    facts = graph_data.get("facts") or []
    options = '<option value="">All facts (overview)</option>'
    for fact in facts:
        if not isinstance(fact, dict):
            continue
        fact_id = str(fact.get("id") or "")
        label = str(fact.get("label") or fact_id)
        if not fact_id:
            continue
        options += f'<option value="{escape(fact_id)}">{escape(label)}</option>'

    return f"""
    <section class="section semantic-graph-section">
      <div class="section-title">Model graph</div>
      <p class="pack-card-lead">{node_count} entities · {edge_count} relationships (approved joins shown in green). Drag to pan.</p>
      <div class="semantic-graph-controls">
        <label class="semantic-graph-label" for="semantic-graph-fact-select">Inspect fact</label>
        <select id="semantic-graph-fact-select" class="semantic-graph-select" data-api-root="{escape(api_root)}">
          {options}
        </select>
      </div>
      <div class="semantic-graph-wrap" id="semantic-graph-view">{svg}</div>
    </section>
    """


def _attributes_section(attributes: list[dict[str, Any]], *, is_admin: bool) -> str:
    proposed = [
        item
        for item in attributes
        if isinstance(item, dict)
        and str(item.get("status") or "") == "proposed"
        and item.get("concepts")
    ]
    if not proposed:
        return ""
    rows = ""
    for item in proposed:
        entity = str(item.get("entity") or "")
        column = str(item.get("column") or "")
        concepts = ", ".join(str(c) for c in item.get("concepts") or [])
        actions = ""
        if is_admin:
            actions = f"""
            <button type="button" class="btn btn-primary btn-sm"
              data-attr-approve="{escape(entity)}::{escape(column)}">Approve</button>
            <button type="button" class="btn btn-secondary btn-sm"
              data-attr-reject="{escape(entity)}::{escape(column)}">Reject</button>
            """
        rows += f"""
        <tr>
          <td><code>{escape(entity)}</code></td>
          <td><code>{escape(column)}</code></td>
          <td>{escape(concepts)}</td>
          <td>{actions}</td>
        </tr>
        """
    bulk = ""
    if is_admin:
        bulk = '<button type="button" class="btn btn-secondary btn-sm" id="semantic-approve-all-tags">Approve all proposed tags</button>'
    return f"""
    <section class="section">
      <div class="section-title">Column tags to review ({len(proposed)})</div>
      <p class="pack-card-lead">AI-proposed concept tags awaiting approval. {bulk}</p>
      <div class="table-wrap semantic-builder-scroll">
        <table class="semantic-builder-table">
          <thead><tr><th>Table</th><th>Column</th><th>Concepts</th><th></th></tr></thead>
          <tbody>{rows}</tbody>
        </table>
      </div>
    </section>
    """


def _assistant_section(*, is_admin: bool) -> str:
    if not is_admin:
        return ""
    return """
    <section class="section semantic-builder-assistant">
      <div class="section-title">Semantic assistant</div>
      <p class="pack-card-lead">Ask about entities, joins, column meaning, or BC data model conventions.</p>
      <div id="semantic-assistant-log" class="semantic-assistant-log"></div>
      <form id="semantic-assistant-form" class="semantic-assistant-form">
        <textarea id="semantic-assistant-input" rows="2" placeholder="e.g. Should revenue use posting date on invoice lines?"></textarea>
        <button type="submit" class="btn btn-primary">Ask</button>
      </form>
    </section>
    """


def _questions_section(questions: list[dict[str, Any]], *, is_admin: bool) -> str:
    if not questions:
        return ""
    items = ""
    for question in questions:
        if not isinstance(question, dict):
            continue
        qid = str(question.get("id") or "")
        text = str(question.get("text") or "")
        status = str(question.get("status") or "open")
        blocking = " · blocks publish" if question.get("blocks_publish") else ""
        resolve_btn = ""
        if is_admin and status == "open":
            resolve_btn = f"""
            <button type="button" class="btn btn-secondary btn-sm" data-question-resolve="{escape(qid)}">Resolve</button>
            """
        resolution = str(question.get("resolution") or "")
        resolution_html = f'<p class="semantic-builder-resolution">{escape(resolution)}</p>' if resolution else ""
        items += f"""
        <li class="semantic-builder-question">
          <div class="semantic-builder-question-head">
            {_status_badge(status)}{blocking}
            <span>{escape(text)}</span>
            {resolve_btn}
          </div>
          {resolution_html}
        </li>
        """
    return f"""
    <section class="section">
      <div class="section-title">Open decisions</div>
      <ul class="semantic-builder-questions">{items}</ul>
    </section>
    """


def _admin_actions(*, is_admin: bool, init_completed: bool, differs: bool, readiness: dict[str, Any]) -> str:
    if not is_admin:
        return ""
    init_btn = ""
    if not init_completed:
        init_btn = '<button type="button" class="btn btn-primary" id="semantic-init-btn">Initialize from source docs</button>'
    publish_disabled = "" if readiness.get("ready") else " disabled"
    publish_hint = "" if readiness.get("ready") else ' title="Resolve readiness issues before publishing"'
    return f"""
    <div class="semantic-builder-actions-bar">
      {init_btn}
      <button type="button" class="btn btn-secondary" id="semantic-reinit-btn"{" hidden" if not init_completed else ""}>Re-run init</button>
      <button type="button" class="btn btn-secondary" id="semantic-approve-all-structure"{" hidden" if not init_completed else ""}>Approve all entities &amp; joins</button>
      <button type="button" class="btn btn-primary" id="semantic-publish-btn"{publish_disabled}{publish_hint}>Publish semantic model</button>
      <button type="button" class="btn btn-secondary" id="semantic-discard-btn"{" disabled" if not differs else ""}>Discard draft changes</button>
    </div>
    """


def _builder_styles() -> str:
    return """
<style>
.semantic-builder-page { display: flex; flex-direction: column; gap: 1.25rem; }
.semantic-builder-coverage {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(10rem, 1fr));
  gap: 0.75rem;
}
.semantic-builder-stat {
  padding: 0.85rem 1rem;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: rgba(8, 18, 40, 0.45);
}
.semantic-builder-stat-value {
  display: block;
  font-size: 1.35rem;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
.semantic-builder-stat-label {
  display: block;
  font-size: 0.82rem;
  color: var(--text-muted);
  margin-top: 0.15rem;
}
.semantic-builder-stat-sub {
  display: block;
  font-size: 0.75rem;
  color: var(--text-muted);
  margin-top: 0.2rem;
}
.semantics-ready-yes { color: #34d399; }
.semantics-ready-no { color: #fbbf24; }
.semantics-status-badge {
  display: inline-block;
  padding: 0.1rem 0.45rem;
  border-radius: 999px;
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}
.semantics-status-proposed { background: rgba(251, 191, 36, 0.18); color: #fcd34d; }
.semantics-status-approved { background: rgba(52, 211, 153, 0.18); color: #6ee7b7; }
.semantics-status-rejected { background: rgba(239, 68, 68, 0.15); color: #fca5a5; }
.semantic-builder-table code { font-size: 0.8rem; word-break: break-all; }
.semantic-builder-citation { font-size: 0.82rem; color: var(--text-muted); max-width: 16rem; }
.semantic-builder-actions { white-space: nowrap; }
.semantic-builder-actions .btn { margin-right: 0.35rem; }
.semantic-builder-actions-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  align-items: center;
}
.semantic-builder-questions {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 0.65rem;
}
.semantic-builder-question {
  padding: 0.75rem 1rem;
  border: 1px solid var(--border);
  border-radius: var(--radius);
}
.semantic-builder-question-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
}
.semantic-builder-resolution {
  margin: 0.5rem 0 0;
  font-size: 0.84rem;
  color: var(--text-muted);
}
.semantic-builder-errors ul { margin: 0.25rem 0 0; padding-left: 1.1rem; }
.semantic-builder-nav {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
  margin-bottom: 0.5rem;
}
.semantic-builder-scroll {
  max-height: 28rem;
  overflow: auto;
}
.semantic-graph-wrap {
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 0.5rem;
  background: rgba(8, 18, 40, 0.35);
  max-height: 28rem;
  overflow: auto;
  cursor: grab;
  user-select: none;
  -webkit-overflow-scrolling: touch;
}
.semantic-graph-wrap.is-dragging {
  cursor: grabbing;
}
.semantic-graph-controls {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.65rem;
}
.semantic-graph-label {
  font-size: 0.82rem;
  color: var(--text-muted);
}
.semantic-graph-select {
  min-width: 14rem;
  max-width: 100%;
}
.semantic-graph-svg {
  display: block;
  max-width: none;
}
.semantic-assistant-log {
  min-height: 4rem;
  max-height: 14rem;
  overflow-y: auto;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 0.75rem;
  margin-bottom: 0.5rem;
  font-size: 0.88rem;
}
.semantic-assistant-form {
  display: flex;
  gap: 0.5rem;
  align-items: flex-start;
}
.semantic-assistant-form textarea {
  flex: 1;
  min-height: 2.5rem;
}
.semantic-assistant-msg { margin: 0.35rem 0; }
.semantic-assistant-msg-user { color: #93c5fd; }
.semantic-assistant-msg-bot { color: var(--text-muted); }
</style>
<script>
(function() {{
  var panState = null;
  document.addEventListener("mousedown", function(event) {{
    var wrap = event.target.closest(".semantic-graph-wrap");
    if (!wrap || event.button !== 0) return;
    panState = {{
      wrap: wrap,
      x: event.clientX,
      y: event.clientY,
      scrollLeft: wrap.scrollLeft,
      scrollTop: wrap.scrollTop
    }};
    wrap.classList.add("is-dragging");
    event.preventDefault();
  }});
  document.addEventListener("mousemove", function(event) {{
    if (!panState) return;
    panState.wrap.scrollLeft = panState.scrollLeft - (event.clientX - panState.x);
    panState.wrap.scrollTop = panState.scrollTop - (event.clientY - panState.y);
  }});
  document.addEventListener("mouseup", function() {{
    if (!panState) return;
    panState.wrap.classList.remove("is-dragging");
    panState = null;
  }});

  window.bindSemanticGraphFactSelect = function() {{
    document.querySelectorAll("#semantic-graph-fact-select").forEach(function(select) {{
      if (select.dataset.bound === "1") return;
      select.dataset.bound = "1";
      var apiRoot = select.getAttribute("data-api-root") || "";
      var view = document.getElementById("semantic-graph-view");
      if (!apiRoot || !view) return;
      select.addEventListener("change", function() {{
        var fact = select.value;
        var url = apiRoot + "/graph" + (fact ? "?fact=" + encodeURIComponent(fact) : "");
        fetch(url, {{ credentials: "same-origin", headers: {{ "Accept": "application/json" }} }})
          .then(function(response) {{
            return response.json().then(function(data) {{
              if (!response.ok) throw new Error(data.error || "Failed to load graph");
              return data;
            }});
          }})
          .then(function(data) {{
            if (typeof data.svg === "string") view.innerHTML = data.svg;
          }})
          .catch(function(err) {{
            alert(err.message);
            select.value = "";
          }});
      }});
    }});
  }};
  window.bindSemanticGraphFactSelect();
}})();
</script>
"""


def _builder_script(api_root: str, *, is_admin: bool) -> str:
    if not is_admin:
        return ""
    return f"""
<script>
(function() {{
  var apiRoot = {json.dumps(api_root)};

  function post(path, body) {{
    return fetch(apiRoot + path, {{
      method: "POST",
      headers: {{ "Content-Type": "application/json" }},
      body: body ? JSON.stringify(body) : "{{}}",
      credentials: "same-origin"
    }}).then(function(r) {{
      return r.json().then(function(data) {{
        if (!r.ok) {{
          var detail = data.error || data.message || data.Message || ("Request failed (" + r.status + ")");
          if (r.status === 401 || detail === "authentication_required" || /auth/i.test(String(detail))) {{
            throw new Error("Session expired — refresh the page and log in again.");
          }}
          throw new Error(detail);
        }}
        return data;
      }}, function() {{
        if (r.status === 401 || r.status === 403) {{
          throw new Error("Session expired — refresh the page and log in again.");
        }}
        throw new Error("Request failed (" + r.status + ")");
      }});
    }});
  }}

  function reload() {{ window.location.reload(); }}

  function refreshBuilderContent() {{
    var scrollY = window.scrollY;
    var assistantLog = document.getElementById("semantic-assistant-log");
    var assistantHtml = assistantLog ? assistantLog.innerHTML : "";
    return fetch(apiRoot + "/builder-ui", {{
      credentials: "same-origin",
      headers: {{ "Accept": "application/json" }}
    }}).then(function(r) {{
      return r.json().then(function(data) {{
        if (!r.ok) {{
          throw new Error(data.error || "Failed to refresh builder");
        }}
        return data;
      }});
    }}).then(function(data) {{
      var el = document.getElementById("semantic-builder-content");
      if (!el || typeof data.html !== "string") return;
      el.innerHTML = data.html;
      bindBuilderActions();
      var restoredLog = document.getElementById("semantic-assistant-log");
      if (restoredLog && assistantHtml) {{
        restoredLog.innerHTML = assistantHtml;
      }}
      if (window.bindSemanticGraphFactSelect) window.bindSemanticGraphFactSelect();
      window.scrollTo(0, scrollY);
    }});
  }}

  function afterReviewAction(promise, btn) {{
    if (btn) btn.disabled = true;
    return promise.then(refreshBuilderContent).catch(function(err) {{
      alert(err.message);
      if (btn) btn.disabled = false;
    }});
  }}

  function bindBuilderActions() {{
    var assistantForm = document.getElementById("semantic-assistant-form");
    var assistantInput = document.getElementById("semantic-assistant-input");
    var assistantLog = document.getElementById("semantic-assistant-log");
    if (assistantForm && assistantInput && assistantLog) {{
      assistantForm.addEventListener("submit", function(event) {{
        event.preventDefault();
        var text = (assistantInput.value || "").trim();
        if (!text) return;
        assistantInput.value = "";
        assistantLog.innerHTML += '<p class="semantic-assistant-msg semantic-assistant-msg-user"><strong>You:</strong> ' + text.replace(/</g, "&lt;") + '</p>';
        post("/assistant", {{ message: text }}).then(function(data) {{
          var reply = (data.reply || "").replace(/</g, "&lt;");
          assistantLog.innerHTML += '<p class="semantic-assistant-msg semantic-assistant-msg-bot"><strong>Assistant:</strong> ' + reply + '</p>';
          assistantLog.scrollTop = assistantLog.scrollHeight;
        }}).catch(function(err) {{
          assistantLog.innerHTML += '<p class="form-error">' + err.message + '</p>';
        }});
      }});
    }}

    var initBtn = document.getElementById("semantic-init-btn");
    if (initBtn) {{
      initBtn.addEventListener("click", function() {{
        initBtn.disabled = true;
        post("/init").then(reload).catch(function(err) {{
          alert(err.message);
          initBtn.disabled = false;
        }});
      }});
    }}

    var reinitBtn = document.getElementById("semantic-reinit-btn");
    if (reinitBtn) {{
      reinitBtn.addEventListener("click", function() {{
        if (!confirm("Re-run init? Proposed (non-approved) items will be refreshed from source docs.")) return;
        reinitBtn.disabled = true;
        post("/init", {{ force: true }}).then(reload).catch(function(err) {{
          alert(err.message);
          reinitBtn.disabled = false;
        }});
      }});
    }}

    document.querySelectorAll("[data-rel-approve]").forEach(function(btn) {{
      btn.addEventListener("click", function() {{
        afterReviewAction(
          post("/relationships/" + btn.getAttribute("data-rel-approve") + "/approve"),
          btn
        );
      }});
    }});
    document.querySelectorAll("[data-rel-reject]").forEach(function(btn) {{
      btn.addEventListener("click", function() {{
        afterReviewAction(
          post("/relationships/" + btn.getAttribute("data-rel-reject") + "/reject"),
          btn
        );
      }});
    }});
    document.querySelectorAll("[data-entity-approve]").forEach(function(btn) {{
      btn.addEventListener("click", function() {{
        afterReviewAction(
          post("/entities/" + btn.getAttribute("data-entity-approve") + "/approve"),
          btn
        );
      }});
    }});
    document.querySelectorAll("[data-entity-reject]").forEach(function(btn) {{
      btn.addEventListener("click", function() {{
        afterReviewAction(
          post("/entities/" + btn.getAttribute("data-entity-reject") + "/reject"),
          btn
        );
      }});
    }});
    document.querySelectorAll("[data-question-resolve]").forEach(function(btn) {{
      btn.addEventListener("click", function() {{
        var resolution = prompt("Optional resolution note:") || "";
        afterReviewAction(
          post("/questions/" + btn.getAttribute("data-question-resolve") + "/resolve", {{ resolution: resolution }}),
          btn
        );
      }});
    }});

    document.querySelectorAll("[data-attr-approve]").forEach(function(btn) {{
      btn.addEventListener("click", function() {{
        var raw = btn.getAttribute("data-attr-approve") || "";
        var parts = raw.split("::");
        afterReviewAction(
          post("/attributes/" + encodeURIComponent(parts[0]) + "/" + encodeURIComponent(parts[1]) + "/approve"),
          btn
        );
      }});
    }});
    document.querySelectorAll("[data-attr-reject]").forEach(function(btn) {{
      btn.addEventListener("click", function() {{
        var raw = btn.getAttribute("data-attr-reject") || "";
        var parts = raw.split("::");
        afterReviewAction(
          post("/attributes/" + encodeURIComponent(parts[0]) + "/" + encodeURIComponent(parts[1]) + "/reject"),
          btn
        );
      }});
    }});

    var approveTagsBtn = document.getElementById("semantic-approve-all-tags");
    if (approveTagsBtn) {{
      approveTagsBtn.addEventListener("click", function() {{
        afterReviewAction(post("/approve-all-tags"), approveTagsBtn);
      }});
    }}

    var approveStructureBtn = document.getElementById("semantic-approve-all-structure");
    if (approveStructureBtn) {{
      approveStructureBtn.addEventListener("click", function() {{
        if (!confirm("Approve all proposed entities and relationships?")) return;
        afterReviewAction(post("/approve-all-structure"), approveStructureBtn);
      }});
    }}

    var publishBtn = document.getElementById("semantic-publish-btn");
    if (publishBtn) {{
      publishBtn.addEventListener("click", function() {{
        if (!confirm("Publish semantic model? Gold compile requires a published model.")) return;
        publishBtn.disabled = true;
        post("/publish").then(refreshBuilderContent).catch(function(err) {{
          alert(err.message);
          publishBtn.disabled = false;
        }});
      }});
    }}

    var discardBtn = document.getElementById("semantic-discard-btn");
    if (discardBtn) {{
      discardBtn.addEventListener("click", function() {{
        if (!confirm("Discard draft and revert to production pin?")) return;
        afterReviewAction(post("/discard"), discardBtn);
      }});
    }}
  }}

  bindBuilderActions();
}})();
</script>
"""


def render_semantic_builder_content_html(
    *,
    settings: DnaSettings,
    is_admin: bool,
    api_root: str = "",
) -> str:
    ensure_semantic_model_seed(settings)
    from meshflow.dna.semantic_structure import sync_semantic_draft_from_catalog

    sync_semantic_draft_from_catalog(settings)
    draft = load_semantic_model_draft(settings)
    production = load_production_semantic_model(settings)
    workflow = load_semantic_model_workflow(settings)
    coverage = semantic_model_coverage(draft)
    readiness = evaluate_publish_readiness(draft)
    differs = draft_differs_from_production(settings)
    init_completed = bool(workflow.get("init_completed"))

    active_version = workflow.get("active_version")
    pin_label = f"v{active_version}" if active_version else "Not published"

    html = f"""
      <p class="pack-card-lead">Production pin: <strong>{escape(pin_label)}</strong>
        · Source: <code>{escape(str(draft.get("source") or settings.source))}</code>
      </p>
      {_coverage_cards(coverage, readiness)}
      {_readiness_errors(readiness)}
      {_admin_actions(
          is_admin=is_admin,
          init_completed=init_completed,
          differs=differs,
          readiness=readiness,
      )}
    """

    if not init_completed:
        html += empty_state(
            "Semantic model not initialized",
            "Run initialize to profile silver tables and propose entities, joins, and column tags "
            "from Business Central documentation.",
        )
    else:
        html += _graph_section(settings, api_root=api_root)
        html += _entities_table(draft.get("entities") or [], is_admin=is_admin)
        html += _relationships_table(draft.get("relationships") or [], is_admin=is_admin)
        html += _attributes_section(draft.get("attributes") or [], is_admin=is_admin)
        html += _questions_section(draft.get("questions") or [], is_admin=is_admin)
        html += _assistant_section(is_admin=is_admin)

    if production and differs:
        html += '<p class="form-error" style="margin-top:0.5rem">Draft has unpublished semantic changes.</p>'

    return html


def render_semantic_builder_page(
    request: Request,
    *,
    settings: DnaSettings,
    client: ClientPortalConfig,
    is_admin: bool = False,
    html_response: Callable[..., Response],
    message: str = "",
    error: str = "",
) -> Response:
    ensure_semantic_model_seed(settings)

    url: Callable[[str], str] = lambda path: f"{request.script_root}{path if path.startswith('/') else f'/{path}'}"
    api_root = url("/api/semantic-model")

    body = f"""
    <div class="semantic-builder-page">
      <div class="semantic-builder-nav">
        <a class="btn btn-secondary btn-sm" href="{escape(url(SEMANTIC_BUILDER_ROOT))}">Builder</a>
        <a class="btn btn-secondary btn-sm" href="{escape(url(SEMANTICS_ROOT))}">Column tags</a>
      </div>
      {page_header(
          "Semantic Builder",
          "Qualify silver tables — entities, joins, and column concepts — before gold compile.",
          eyebrow="DNA",
      )}
    """
    if message:
        body += f'<div class="form-success">{escape(message)}</div>'
    if error:
        body += f'<div class="form-error">{escape(error)}</div>'

    body += f"""
      <div id="semantic-builder-content">
        {render_semantic_builder_content_html(settings=settings, is_admin=is_admin, api_root=api_root)}
      </div>
    </div>
    """
    body += _builder_styles()
    body += _builder_script(api_root, is_admin=is_admin)

    return html_response(
        request,
        client=client,
        title="Semantic Builder",
        active_path=SEMANTIC_BUILDER_ROOT,
        body=body,
        is_admin=is_admin,
        settings=settings,
    )


def semantic_model_governance_card_html(
    *,
    url: Callable[[str], str],
    settings: DnaSettings,
) -> str:
    ensure_semantic_model_seed(settings)
    workflow = load_semantic_model_workflow(settings)
    production = load_production_semantic_model(settings)
    draft = load_semantic_model_draft(settings)
    coverage = semantic_model_coverage(draft)
    readiness = evaluate_publish_readiness(draft)
    differs = draft_differs_from_production(settings)
    active_version = workflow.get("active_version")
    if active_version:
        pin_label = f'<span class="pack-version">v{escape(str(active_version))}</span>'
    else:
        pin_label = '<span class="pack-version">Not published</span>'
    init_label = "Yes" if workflow.get("init_completed") else "No — run init in Builder"
    warn = (
        '<p class="form-error" style="margin-top:0.5rem">Draft has unpublished semantic changes.</p>'
        if differs
        else ""
    )
    gate_warn = ""
    if workflow.get("init_completed") and not readiness.get("ready"):
        gate_warn = '<p class="form-error" style="margin-top:0.5rem">Gold compile blocked until semantic model is published.</p>'
    return f"""
    <section class="section">
      <div class="section-title">Semantic model</div>
      <div class="card pack-card">
        <p class="pack-card-lead">Entities, joins, and qualified columns between silver and gold.</p>
        <dl class="pack-meta">
          <div><dt>Production pin</dt><dd>{pin_label}</dd></div>
          <div><dt>Initialized</dt><dd>{escape(init_label)}</dd></div>
          <div><dt>Joins approved</dt><dd>{coverage.get("relationship_approved", 0)}</dd></div>
          <div><dt>Columns tagged</dt><dd>{coverage.get("tagged_column_count", 0)}</dd></div>
        </dl>
        {gate_warn}
        {warn}
        <p style="margin-top:0.75rem">
          <a class="btn btn-secondary" href="{escape(url('/portal/semantics/builder'))}">Open Semantic Builder</a>
        </p>
      </div>
    </section>
    """
