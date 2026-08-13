"""KPI Generator portal page markup."""

from __future__ import annotations

import json
from datetime import datetime
from meshflow.compat import UTC
from html import escape
from typing import Any, Callable

from meshflow.dna.settings import DnaSettings
from meshflow.dna.source_docs.reference import load_source_docs_gold_artifact
from meshflow.dna.web.portal.governance_helpers.proposals import (
    bump_major_version,
    bump_minor_version,
    bump_patch_version,
)
from meshflow.dna.web.portal.kpi_generator.service import (
    build_fields_by_fact,
    list_fact_options,
)
from meshflow.dna.web.portal.kpi_generator.integrity import (
    draft_target_label,
    group_integrity_passed,
    group_integrity_status,
    group_pending_drafts,
)
from meshflow.dna.web.portal.kpi_generator.sql_format import format_kpi_sql
from meshflow.dna.web.portal.version_bump import (
    version_bump_field_html,
    version_bump_script,
)
from meshflow.dna.workflow import load_production_pack, load_workflow_state


def _json_for_script(payload: Any) -> str:
    """Serialize JSON for inline <script> without closing the HTML script element."""
    return json.dumps(payload).replace("<", "\\u003c")


def _kpi_assistant_messages_html(proposal: dict[str, Any] | None) -> str:
    if not proposal:
        return (
            '<p class="pack-card-lead">'
            "Describe the KPI you want — natural language in, Athena SQL out."
            "</p>"
        )

    history = proposal.get("chat_history") or []
    if history:
        html = ""
        for entry in history:
            role = str(entry.get("role") or "user").strip().lower()
            text = str(entry.get("text") or "").strip()
            if not text:
                continue
            if role == "user":
                html += (
                    f'<div class="assistant-bubble user">'
                    f'<div class="assistant-bubble-label">You</div>'
                    f'<div class="assistant-bubble-text">{escape(text)}</div>'
                    f"</div>"
                )
            else:
                html += (
                    f'<div class="assistant-bubble">'
                    f'<div class="assistant-bubble-label">Assistant</div>'
                    f'<div class="assistant-bubble-text">{escape(text)}</div>'
                    f"</div>"
                )
        return html or (
            '<p class="pack-card-lead">'
            "Describe the KPI you want — natural language in, Athena SQL out."
            "</p>"
        )

    prompt = str(proposal.get("prompt") or "").strip()
    draft = proposal.get("draft") or {}
    html = ""
    if prompt:
        html += (
            f'<div class="assistant-bubble user">'
            f'<div class="assistant-bubble-label">You</div>'
            f'<div class="assistant-bubble-text">{escape(prompt)}</div>'
            f"</div>"
        )

    assistant_text = str(draft.get("summary") or draft.get("calculation") or "").strip()
    if not assistant_text:
        assistant_text = "Draft KPI SQL is ready — review the proposal below."
    html += (
        f'<div class="assistant-bubble">'
        f'<div class="assistant-bubble-label">Assistant</div>'
        f'<div class="assistant-bubble-text">{escape(assistant_text)}</div>'
        f"</div>"
    )
    return html


def _kpi_compose_html(
    url: Callable[[str], str],
    *,
    usage_at_limit: bool = False,
    prior_proposal_id: str = "",
) -> str:
    if usage_at_limit:
        return (
            '<p class="pack-card-lead governance-usage-limit">'
            "Monthly Bedrock allowance reached. Review an existing proposal below "
            "or wait until next month to generate a new KPI."
            "</p>"
        )
    prior_field = ""
    if prior_proposal_id:
        prior_field = (
            f'<input type="hidden" name="prior_proposal_id" '
            f'value="{escape(prior_proposal_id)}" />'
        )
    return f"""
      <form method="post" action="{escape(url('/portal/dna/kpi-generator'))}" class="assistant-compose">
        <input type="hidden" name="action" value="generate" />
        {prior_field}
        <div class="form-field assistant-compose-field">
          <label for="kpi-prompt">Message</label>
          <textarea id="kpi-prompt" name="prompt" rows="2" required
            class="assistant-compose-input"
            placeholder="e.g. Net sales revenue as sum of posted invoice line amounts excluding credit memos"></textarea>
        </div>
        <button type="submit" class="btn btn-primary portal-submit-btn">Send</button>
      </form>
    """


def _kpi_scroll_script() -> str:
    return """
<script>
(function () {
  var target = document.getElementById("kpi-generator-validation");
  if (!target) return;
  var params = new URLSearchParams(window.location.search);
  if (
    window.location.hash === "#kpi-generator-validation"
    || params.get("validated") === "1"
  ) {
    target.scrollIntoView({ block: "start" });
  }
})();
</script>
"""


def _kpi_compose_script() -> str:
    return """
<script>
(function () {
  var form = document.querySelector("#kpi-generator-prompt form.assistant-compose");
  var box = document.getElementById("kpi-prompt");
  if (!form || !box || box.dataset.enterBound === "1") return;
  box.dataset.enterBound = "1";
  box.addEventListener("keydown", function (event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      if (typeof form.requestSubmit === "function") form.requestSubmit();
      else form.submit();
    }
  });
})();
</script>
"""


def _format_grain_columns_html(draft: dict[str, Any]) -> str:
    layer = str(draft.get("layer") or "").strip().lower()
    if layer != "gold":
        return ""
    columns = draft.get("grain_columns") or []
    if not columns:
        return '<div><dt>Grain</dt><dd><span class="muted">company total</span></dd></div>'
    chips = "".join(f'<li class="kpi-chip">{escape(str(col))}</li>' for col in columns)
    return f'<div><dt>Grain columns</dt><dd><ul class="kpi-chip-list">{chips}</ul></dd></div>'


def _silver_enhancement_notice_html(draft: dict[str, Any]) -> str:
    layer = str(draft.get("layer") or "").strip().lower()
    if layer != "silver":
        return ""
    target = str(draft.get("target_entity") or "").strip()
    if not target:
        return ""
    canonical = f"enhance__{target.strip().lower()}"
    return (
        '<p class="pack-card-lead">This KPI contributes columns to the single silver enhancement '
        f'<code>{escape(canonical)}</code> for entity <code>{escape(target)}</code>. '
        "On save, contributions are merged into one canonical entity transform.</p>"
    )


def _merged_enhancement_html(proposal: dict[str, Any] | None) -> str:
    if not proposal:
        return ""
    merged = str(proposal.get("merged_enhancement_sql") or "").strip()
    if not merged:
        return ""
    return f"""
          <h4 class="kpi-section-heading">Merged entity enhancement</h4>
          <p class="pack-card-lead">Read-only preview of the canonical silver transform after merge.</p>
          <pre class="kpi-sql-block">{escape(format_kpi_sql(merged))}</pre>
    """


def _kpi_chip_list_html(items: list[Any]) -> str:
    if not items:
        return '<span class="muted">—</span>'
    chips = "".join(
        f'<li class="kpi-chip">{escape(str(item))}</li>' for item in items
    )
    return f'<ul class="kpi-chip-list">{chips}</ul>'


def _kpi_proposal_results_html(
    url: Callable[[str], str],
    *,
    proposal_id: str,
    draft: dict[str, Any],
    last_val: dict[str, Any] | None,
) -> str:
    fields = draft.get("fields_used") or []
    filters = draft.get("filters_applied") or []
    calc = str(draft.get("calculation") or draft.get("summary") or "").strip()
    sql = format_kpi_sql(str(draft.get("sql") or ""))
    layer = escape(str(draft.get("layer") or "—"))
    mode = escape(str(draft.get("mode") or "—"))
    tid = escape(str(draft.get("id") or "—"))
    target = escape(str(draft.get("target_entity") or draft.get("output_id") or "—"))
    grain_html = _format_grain_columns_html(draft)
    silver_notice = _silver_enhancement_notice_html(draft)
    sql_heading = "Contribution SQL" if str(draft.get("layer") or "").lower() == "silver" else "Athena SQL"
    return f"""
        <section class="card pack-card" id="kpi-generator-results">
          <h2>Proposed calculation</h2>
          <p class="pack-card-lead">Review the draft SQL, validate against sample filters, then save as a DNA draft for review.</p>
          {silver_notice}
          <dl class="pack-meta">
            <div><dt>Layer</dt><dd>{layer}</dd></div>
            <div><dt>Mode</dt><dd>{mode}</dd></div>
            <div><dt>Transform id</dt><dd><code>{tid}</code></dd></div>
            <div><dt>Target</dt><dd><code>{target}</code></dd></div>
            {grain_html}
          </dl>
          <div class="assistant-pack-block">
            <h3 class="kpi-section-heading">Fields &amp; filters</h3>
            <dl class="pack-meta">
              <div><dt>Fields used</dt><dd>{_kpi_chip_list_html(fields)}</dd></div>
              <div><dt>SQL filters</dt><dd>{_kpi_chip_list_html(filters)}</dd></div>
            </dl>
          </div>
          <div class="assistant-pack-block">
            <h3 class="kpi-section-heading">Calculation</h3>
            <p class="kpi-calculation">{escape(calc) or "—"}</p>
          </div>
          <div class="assistant-pack-block" id="kpi-generator-validation">
            <h3 class="kpi-section-heading">Validation</h3>
            {_validation_table_html(last_val)}
            <form method="post" action="{escape(url('/portal/dna/kpi-generator'))}" style="margin-top:0.75rem">
              <input type="hidden" name="action" value="validate" />
              <input type="hidden" name="proposal_id" value="{proposal_id}" />
              <p class="pack-card-lead">Applies the validation criteria filters above to this query.</p>
              <button type="submit" class="btn btn-secondary" id="kpi-run-validate">Run validation</button>
            </form>
          </div>
          <div class="assistant-pack-block">
            <h3 class="kpi-section-heading">{sql_heading}</h3>
            <p class="pack-card-lead">Edit the query before validating or saving. Changes are applied when you run validation or save the draft.</p>
            <textarea id="kpi-draft-sql" class="kpi-sql-block kpi-sql-editor" rows="14" spellcheck="false">{escape(sql)}</textarea>
          </div>
          <form method="post" action="{escape(url('/portal/dna/kpi-generator'))}" class="assistant-approve-form" id="kpi-save-draft-form">
            <input type="hidden" name="proposal_id" value="{proposal_id}" />
            <div class="assistant-approve-actions">
              <button type="submit" name="action" value="save_draft" class="btn btn-primary" id="kpi-save-draft">Save Draft</button>
              <button type="submit" name="action" value="discard_draft" class="btn btn-secondary" id="kpi-discard-draft" formnovalidate>Discard Draft</button>
            </div>
          </form>
        </section>
        """


def _integrity_status_html(proposals: list[dict[str, Any]], *, target_key: str) -> str:
    status = group_integrity_status(proposals, target_key=target_key)
    validation: dict[str, Any] = {}
    for proposal in proposals:
        candidate = proposal.get("integrity_validation") or {}
        if isinstance(candidate, dict) and candidate:
            recorded = str(candidate.get("target_key") or "").strip()
            if not recorded and candidate.get("target_entity"):
                recorded = f"silver:{candidate.get('target_entity')}"
            if recorded and recorded != target_key:
                continue
            validation = candidate
            break
    if status == "passed":
        return (
            '<p class="pack-card-lead"><strong>Integrity:</strong> '
            '<span class="kpi-integrity-passed">Passed</span> for '
            f"<code>{escape(target_key)}</code>. Approval is enabled.</p>"
        )
    if status == "failed":
        errors = validation.get("errors") or ["Validation failed"]
        err_text = "; ".join(escape(str(err)) for err in errors)
        repair_note = ""
        if validation.get("repair_attempted"):
            repair_note = " An automatic LLM repair was attempted."
        return (
            '<p class="pack-card-lead"><strong>Integrity:</strong> '
            f'<span class="kpi-integrity-failed">Failed</span> — {err_text}.{repair_note}</p>'
        )
    return (
        '<p class="pack-card-lead"><strong>Integrity:</strong> '
        "Not run yet. Run integrity validation before approving this group.</p>"
    )


def _kpi_draft_group_html(
    url: Callable[[str], str],
    *,
    target_key: str,
    proposals: list[dict[str, Any]],
    base_version: str,
) -> str:
    label = escape(draft_target_label(target_key))
    proposal_ids = [
        str(proposal.get("proposal_id") or "").strip()
        for proposal in proposals
        if str(proposal.get("proposal_id") or "").strip()
    ]
    hidden_ids = "".join(
        f'<input type="hidden" name="proposal_ids" value="{escape(pid)}" />'
        for pid in proposal_ids
    )
    integrity_html = _integrity_status_html(proposals, target_key=target_key)
    can_approve = group_integrity_passed(proposals, target_key=target_key)
    approve_button = (
        '<button type="submit" name="action" value="approve_group" class="btn btn-primary">'
        "Approve group</button>"
        if can_approve
        else (
            '<button type="button" class="btn btn-primary" disabled '
            'title="Run integrity validation and ensure it passes before approving">'
            "Approve group</button>"
        )
    )
    items = "".join(
        _kpi_draft_review_item_html(url, proposal, base_version=base_version, grouped=True)
        for proposal in proposals
    )
    next_patch = bump_patch_version(base_version)
    return f"""
    <section class="card pack-card kpi-draft-group">
      <div class="kpi-draft-group-header">
        <h3>{label}</h3>
        <p class="pack-card-lead">Group <code>{escape(target_key)}</code> · {len(proposals)} draft(s)</p>
        {integrity_html}
        <form method="post" action="{escape(url('/portal/dna/kpi-generator'))}" class="kpi-draft-group-actions">
          <input type="hidden" name="target_key" value="{escape(target_key)}" />
          {hidden_ids}
          <button type="submit" name="action" value="validate_integrity" class="btn btn-secondary">
            Run integrity validation
          </button>
          {approve_button}
          <input type="hidden" name="next_sql_version" value="{escape(next_patch)}" />
        </form>
      </div>
      <div class="kpi-draft-list">
        {items}
      </div>
    </section>
    """


def _kpi_draft_review_item_html(
    url: Callable[[str], str],
    proposal: dict[str, Any],
    *,
    base_version: str,
    grouped: bool = False,
) -> str:
    snapshot = proposal.get("governance_snapshot") or {}
    draft = proposal.get("draft") or snapshot.get("draft") or {}
    last_val = proposal.get("last_validation") or snapshot.get("last_validation")
    proposal_id_raw = str(proposal.get("proposal_id") or "")
    proposal_id = escape(proposal_id_raw)
    tid = escape(str(draft.get("id") or "—"))
    layer = escape(str(draft.get("layer") or "—"))
    mode = escape(str(draft.get("mode") or "—"))
    target = escape(str(draft.get("target_entity") or draft.get("output_id") or "—"))
    calc = str(
        draft.get("calculation")
        or draft.get("summary")
        or snapshot.get("calculation")
        or ""
    ).strip()
    sql = format_kpi_sql(str(draft.get("sql") or snapshot.get("sql") or ""))
    prompt = escape(str(proposal.get("prompt") or snapshot.get("prompt") or ""))
    grain_html = _format_grain_columns_html(draft)
    silver_notice = _silver_enhancement_notice_html(draft) if not grouped else ""
    merged_html = _merged_enhancement_html(proposal)
    sql_heading = "Contribution SQL" if str(draft.get("layer") or "").lower() == "silver" else "Athena SQL"
    header_actions = ""
    if not grouped:
        header_actions = """
            <span class="semantic-builder-review-item kpi-draft-header-actions" data-kpi-draft-actions>
              <button type="submit" name="action" value="reject" formnovalidate
                class="btn btn-secondary btn-sm semantic-builder-review-choice semantic-builder-review-reject">Reject</button>
            </span>
        """
    return f"""
      <details class="semantic-builder-fk-section kpi-draft-section">
        <summary class="semantic-builder-fk-section-summary">
          <span class="semantic-builder-fk-section-summary-inner">
            <span class="semantic-builder-expand-icon" aria-hidden="true"></span>
            <span class="semantic-builder-fk-section-title"><code>{tid}</code></span>
            <span class="semantic-builder-fk-section-count">{layer} · {mode}</span>
            <span class="semantic-builder-fk-section-count">target <code>{target}</code></span>
            {header_actions}
          </span>
        </summary>
        <div class="semantic-builder-fk-section-body kpi-draft-section-body">
          <p class="pack-card-lead"><strong>Request:</strong> {prompt or "—"}</p>
          {silver_notice}
          <dl class="pack-meta">
            <div><dt>Layer</dt><dd>{layer}</dd></div>
            <div><dt>Mode</dt><dd>{mode}</dd></div>
            <div><dt>Target</dt><dd><code>{target}</code></dd></div>
            {grain_html}
          </dl>
          <h4 class="kpi-section-heading">Calculation</h4>
          <p class="kpi-calculation">{escape(calc) or "—"}</p>
          <h4 class="kpi-section-heading">Validation criteria</h4>
          {_validation_criteria_html(last_val if isinstance(last_val, dict) else None) or '<p class="muted">—</p>'}
          <h4 class="kpi-section-heading">Validation results</h4>
          {_validation_table_html(last_val if isinstance(last_val, dict) else None)}
          <h4 class="kpi-section-heading">{sql_heading}</h4>
          <pre class="kpi-sql-block">{escape(sql) or "—"}</pre>
          {merged_html}
          <form method="post" action="{escape(url('/portal/dna/kpi-generator'))}" class="kpi-draft-review-form">
            <input type="hidden" name="proposal_id" value="{proposal_id}" />
            <button type="submit" name="action" value="reject" formnovalidate class="btn btn-secondary btn-sm">Reject draft</button>
          </form>
        </div>
      </details>
    """


def _kpi_review_drafts_html(
    url: Callable[[str], str],
    pending_drafts: list[dict[str, Any]],
    *,
    base_version: str,
) -> str:
    if not pending_drafts:
        return (
            '<div class="card pack-card">'
            '<p class="pack-card-lead">No KPI drafts awaiting review. '
            "Generate a KPI and click <strong>Save Draft</strong> to queue it here.</p>"
            "</div>"
        )
    groups = group_pending_drafts(pending_drafts)
    items = "".join(
        _kpi_draft_group_html(
            url,
            target_key=target_key,
            proposals=group_proposals,
            base_version=base_version,
        )
        for target_key, group_proposals in groups.items()
    )
    return f"""
      <div class="kpi-draft-bulk-actions">
        <form method="post" action="{escape(url('/portal/dna/kpi-generator'))}" class="assistant-actions">
          <input type="hidden" name="action" value="reject_all" />
          <button type="submit" class="btn btn-secondary">Reject all</button>
        </form>
      </div>
      <div class="kpi-draft-groups">
        {items}
      </div>
    """


def _kpi_tabs_html(
    *,
    active_tab: str,
    pending_count: int,
) -> str:
    generator_active = active_tab != "review"
    review_active = active_tab == "review"
    review_label = f"Review Drafts ({pending_count})" if pending_count else "Review Drafts"
    return f"""
    <div class="semantic-builder-keys-tabs" role="tablist" aria-label="KPI Generator">
      <button type="button" class="semantic-builder-keys-tab{" active" if generator_active else ""}" role="tab"
        data-kpi-tab="generator" aria-selected="{"true" if generator_active else "false"}"
        aria-controls="kpi-generator-panel-generator">KPI Generator</button>
      <button type="button" class="semantic-builder-keys-tab{" active" if review_active else ""}" role="tab"
        data-kpi-tab="review" aria-selected="{"true" if review_active else "false"}"
        aria-controls="kpi-generator-panel-review">{escape(review_label)}</button>
    </div>
    """


def _kpi_tabs_script() -> str:
    return """
<script>
(function () {
  function activateKpiTab(name) {
    var section = document.getElementById("kpi-generator-tabs");
    if (!section) return;
    section.querySelectorAll("[data-kpi-tab]").forEach(function (tab) {
      var active = tab.getAttribute("data-kpi-tab") === name;
      tab.classList.toggle("active", active);
      tab.setAttribute("aria-selected", active ? "true" : "false");
    });
    section.querySelectorAll("[data-kpi-panel]").forEach(function (panel) {
      panel.hidden = panel.getAttribute("data-kpi-panel") !== name;
    });
    try {
      window.sessionStorage.setItem("kpiGeneratorTab", name);
    } catch (e) {}
  }

  function initKpiTabs() {
    var section = document.getElementById("kpi-generator-tabs");
    if (!section) return;
    var params = new URLSearchParams(window.location.search);
    var defaultTab = section.getAttribute("data-default-tab") || "generator";
    if (params.get("tab") === "review") {
      defaultTab = "review";
    } else if (!params.get("tab")) {
      try {
        var saved = window.sessionStorage.getItem("kpiGeneratorTab");
        if (saved === "generator" || saved === "review") defaultTab = saved;
      } catch (e) {}
    }
    section.querySelectorAll("[data-kpi-tab]").forEach(function (tab) {
      tab.addEventListener("click", function () {
        activateKpiTab(tab.getAttribute("data-kpi-tab") || "generator");
      });
    });
    section.querySelectorAll("[data-kpi-draft-actions]").forEach(function (actions) {
      actions.addEventListener("click", function (event) {
        event.stopPropagation();
      });
    });
    activateKpiTab(defaultTab);
  }

  initKpiTabs();
})();
</script>
"""


def _validation_criteria_html(last_val: dict[str, Any] | None) -> str:
    """Read-only validation filter chips from a prior run."""
    if not last_val:
        return ""
    filters = last_val.get("filters") or []
    if not filters:
        return ""
    chips = "".join(
        f'<li class="kpi-chip">{escape(str(f.get("fact") or ""))} · '
        f'{escape(str(f.get("field") or ""))} = {escape(str(f.get("value") or ""))}</li>'
        for f in filters
        if str(f.get("field") or "").strip() and str(f.get("value") or "").strip()
    )
    if not chips:
        return ""
    return f'<ul class="kpi-chip-list">{chips}</ul>'


def _kpi_filters_script(
    *,
    facts: list[dict[str, Any]],
    fields_by_fact: dict[str, list[str]],
    saved_filters: list[dict[str, str]] | None = None,
) -> str:
    facts_json = _json_for_script(facts)
    fields_json = _json_for_script(fields_by_fact)
    saved_json = _json_for_script(saved_filters or [])
    return f"""
<script>
(function () {{
  var facts = {facts_json};
  var fieldsByFact = {fields_json};
  var savedFilters = {saved_json};
  var root = document.getElementById("kpi-filter-rows");
  var section = document.getElementById("kpi-generator-validation-filters");
  if (!root || !section) return;

  function fillFieldSelect(factSel, fieldSel, preferredField) {{
    var fields = fieldsByFact[factSel.value] || [];
    fieldSel.textContent = "";
    fields.forEach(function (name) {{
      var opt = document.createElement("option");
      opt.value = name;
      opt.textContent = name;
      fieldSel.appendChild(opt);
    }});
    if (preferredField) {{
      fieldSel.value = preferredField;
      if (fieldSel.value !== preferredField) {{
        var extra = document.createElement("option");
        extra.value = preferredField;
        extra.textContent = preferredField;
        fieldSel.appendChild(extra);
        fieldSel.value = preferredField;
      }}
    }}
  }}

  function addRow(initial) {{
    var row = document.createElement("div");
    row.className = "kpi-filter-row";

    var factSel = document.createElement("select");
    factSel.name = "filter_fact";
    factSel.className = "kpi-filter-control kpi-fact";
    facts.forEach(function (fact) {{
      var opt = document.createElement("option");
      opt.value = fact.id || "";
      opt.textContent = fact.label || fact.id || "";
      factSel.appendChild(opt);
    }});

    var fieldSel = document.createElement("select");
    fieldSel.name = "filter_field";
    fieldSel.className = "kpi-filter-control kpi-field";

    var valueInput = document.createElement("input");
    valueInput.name = "filter_value";
    valueInput.type = "text";
    valueInput.placeholder = "value";
    valueInput.className = "kpi-filter-control";

    var removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "btn btn-secondary kpi-remove";
    removeBtn.textContent = "Remove";

    factSel.addEventListener("change", function () {{
      fillFieldSelect(factSel, fieldSel);
    }});

    if (initial) {{
      if (initial.fact) factSel.value = initial.fact;
      fillFieldSelect(factSel, fieldSel, initial.field || "");
      valueInput.value = initial.value || "";
    }} else {{
      fillFieldSelect(factSel, fieldSel);
    }}

    row.appendChild(factSel);
    row.appendChild(fieldSel);
    row.appendChild(valueInput);
    row.appendChild(removeBtn);
    root.appendChild(row);
  }}

  section.addEventListener("click", function (event) {{
    var target = event.target;
    if (!target || typeof target.closest !== "function") return;
    if (target.closest("#kpi-add-filter")) {{
      event.preventDefault();
      addRow();
      return;
    }}
    var removeBtn = target.closest(".kpi-remove");
    if (removeBtn) {{
      event.preventDefault();
      var row = removeBtn.closest(".kpi-filter-row");
      if (row) row.remove();
    }}
  }});

  function attachSqlToForm(formEl) {{
    var sqlBox = document.getElementById("kpi-draft-sql");
    if (!sqlBox || !formEl) return;
    formEl.querySelectorAll("input[data-kpi-sql-copy]").forEach(function (node) {{
      node.remove();
    }});
    var input = document.createElement("input");
    input.type = "hidden";
    input.name = "sql";
    input.value = sqlBox.value;
    input.setAttribute("data-kpi-sql-copy", "1");
    formEl.appendChild(input);
  }}

  function attachFiltersToForm(formEl) {{
    formEl.querySelectorAll("input[data-kpi-filter-copy]").forEach(function (node) {{
      node.remove();
    }});
    document.querySelectorAll("#kpi-filter-rows .kpi-filter-row").forEach(function (row) {{
      ["filter_fact", "filter_field", "filter_value"].forEach(function (name) {{
        var src = row.querySelector("[name='" + name + "']");
        if (!src) return;
        var input = document.createElement("input");
        input.type = "hidden";
        input.name = name;
        input.value = src.value;
        input.setAttribute("data-kpi-filter-copy", "1");
        formEl.appendChild(input);
      }});
    }});
  }}

  function bindDraftFormSubmit(buttonId) {{
    var button = document.getElementById(buttonId);
    if (!button) return;
    var formEl = button.closest("form");
    if (!formEl) return;
    formEl.addEventListener("submit", function (ev) {{
      attachFiltersToForm(ev.target);
      attachSqlToForm(ev.target);
    }});
  }}

  bindDraftFormSubmit("kpi-run-validate");
  bindDraftFormSubmit("kpi-save-draft");

  if (savedFilters.length) {{
    savedFilters.forEach(function (filter) {{
      addRow(filter);
    }});
  }} else {{
    addRow();
  }}
}})();
</script>
"""


def _format_datetime_minute(value: Any) -> str:
    text = str(value).strip()
    if not text:
        return ""
    normalized = text.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalized)
        has_time = (
            "T" in text
            or text.endswith("Z")
            or "+" in text[10:]
            or (len(text) > 10 and text[10] in {" ", "T"})
        )
        if has_time:
            return dt.strftime("%b %d, %Y %H:%M")
        return dt.strftime("%b %d, %Y")
    except ValueError:
        return text[:10] if len(text) >= 10 else text


def dna_refresh_status_html(
    *,
    form_path: str,
    refresh_status: dict[str, Any],
    quota: dict[str, Any],
) -> str:
    pinned = escape(str(refresh_status.get("pinned_version") or "???"))
    published = escape(str(refresh_status.get("published_version") or "???"))
    published_at_raw = str(refresh_status.get("published_at") or "").strip()
    published_at = escape(_format_datetime_minute(published_at_raw) if published_at_raw else "???")
    is_stale = bool(refresh_status.get("is_stale"))
    in_progress = bool(quota.get("in_progress"))
    at_limit = bool(quota.get("at_limit"))
    remaining = int(quota.get("remaining") or 0)
    monthly_limit = int(quota.get("monthly_limit") or 0)
    used = int(quota.get("used") or 0)
    month = escape(str(quota.get("month") or ""))

    if in_progress:
        state_label = "Refresh in progress"
        state_class = "dna-refresh-state in-progress"
        state_detail = (
            "Gold tables are being rebuilt from the pinned DNA pack. "
            "This page will reflect the new outputs when the run completes."
        )
    elif is_stale:
        state_label = "Refresh needed"
        state_class = "dna-refresh-state stale"
        state_detail = (
            f"Pinned DNA <code>v{pinned}</code> has not been written to gold yet "
            f"(gold is at <code>v{published}</code>). "
            "Run a manual refresh to update certified tables and portal charts."
        )
    else:
        state_label = "Gold tables current"
        state_class = "dna-refresh-state current"
        state_detail = (
            f"Certified gold outputs match pinned DNA <code>v{pinned}</code>. "
            f"Last gold refresh: {published_at}."
        )

    button_disabled = in_progress or at_limit
    disabled_reason = ""
    if in_progress:
        disabled_reason = "A refresh is already running."
    elif at_limit:
        disabled_reason = "Monthly manual refresh limit reached."

    button_attrs = ' disabled aria-disabled="true"' if button_disabled else ""
    limit_note = (
        f'<p class="dna-refresh-limit">Monthly manual refresh limit reached '
        f"({used} of {monthly_limit} used in {month}).</p>"
        if at_limit and not in_progress
        else ""
    )
    disabled_note = (
        f'<p class="dna-refresh-limit">{escape(disabled_reason)}</p>'
        if disabled_reason and not at_limit
        else ""
    )

    return f"""
      <div class="dna-refresh-status" aria-label="Gold refresh status">
        <div class="dna-refresh-status-head">
          <div>
            <span class="{state_class}">{escape(state_label)}</span>
            <p class="dna-refresh-status-detail">{state_detail}</p>
          </div>
          <form method="post" action="{escape(form_path)}" class="dna-refresh-form">
            <input type="hidden" name="action" value="manual_dna_refresh" />
            <button type="submit" class="btn btn-primary"{button_attrs}>
              Refresh gold tables
            </button>
          </form>
        </div>
        <p class="dna-refresh-quota-meta">
          Manual refreshes remaining: <strong>{remaining}</strong> of {monthly_limit} ({month})
        </p>
        {limit_note}
        {disabled_note}
      </div>
    """


def render_kpi_generator_body(
    *,
    settings: DnaSettings,
    url: Callable[[str], str],
    is_admin: bool,
    proposal: dict[str, Any] | None = None,
    validation: dict[str, Any] | None = None,
    message: str = "",
    error: str = "",
    usage: dict[str, Any] | None = None,
    refresh_status: dict[str, Any] | None = None,
    refresh_quota: dict[str, Any] | None = None,
    active_tab: str = "generator",
    pending_drafts: list[dict[str, Any]] | None = None,
) -> str:
    html = ""
    if message:
        html += f'<div class="form-success">{escape(message)}</div>'
    if error:
        html += f'<div class="form-error">{escape(error)}</div>'

    if usage:
        used = usage.get("estimated_cost_usd", 0)
        budget = usage.get("monthly_budget_usd", 0)
        html += (
            f'<p class="muted">Bedrock usage this month: '
            f"${escape(str(used))} / ${escape(str(budget))}</p>"
        )

    if refresh_status and refresh_quota:
        html += f"""
    <section class="card" id="kpi-generator-refresh">
      <h2>Gold refresh</h2>
      {dna_refresh_status_html(
          form_path=url("/portal/dna/kpi-generator"),
          refresh_status=refresh_status,
          quota=refresh_quota,
      )}
    </section>
    """

    if not is_admin:
        html += (
            '<div class="card"><p>KPI Generator is available to portal admins.</p></div>'
        )
        return html

    # One source-docs read for all validation dropdowns (avoid N+1 S3 fetches per table).
    entity_properties = load_source_docs_gold_artifact(settings, "entity_properties") or {}
    facts = list_fact_options(settings, entity_properties=entity_properties)
    fields_by_fact = build_fields_by_fact(settings, entity_properties=entity_properties)
    draft = (proposal or {}).get("draft") or {}
    last_val = validation or (proposal or {}).get("last_validation")
    saved_filters: list[dict[str, str]] = []
    if isinstance(last_val, dict):
        raw_filters = last_val.get("filters") or []
        saved_filters = [
            {
                "fact": str(f.get("fact") or ""),
                "field": str(f.get("field") or ""),
                "value": str(f.get("value") or ""),
            }
            for f in raw_filters
            if isinstance(f, dict)
            and str(f.get("field") or "").strip()
            and str(f.get("value") or "").strip()
        ]
    usage_at_limit = bool((usage or {}).get("at_limit"))
    drafts = pending_drafts or []
    tab = "review" if active_tab == "review" else "generator"
    prior_proposal_id = ""
    if proposal and str(proposal.get("status") or "").strip().lower() == "working":
        prior_proposal_id = str(proposal.get("proposal_id") or "").strip()
    workflow = load_workflow_state(settings, settings.dna_config_id)
    base_pack = load_production_pack(settings)
    base_version = str(workflow.get("active_version") or base_pack.version)

    html += f"""
    <section class="semantic-builder-keys-tabs-section" id="kpi-generator-tabs"
             data-default-tab="{escape(tab)}">
      {_kpi_tabs_html(active_tab=tab, pending_count=len(drafts))}
      <div class="semantic-builder-keys-panel" id="kpi-generator-panel-generator"
           data-kpi-panel="generator" role="tabpanel"{" hidden" if tab == "review" else ""}>
    """

    html += f"""
    <section class="card" id="kpi-generator-prompt">
      <h2>Describe the KPI</h2>
      <p class="muted">Live silver columns and Source Browser gold YAML are used as reference. Save drafts for review;
      approved SQL is replayed verbatim on refresh.</p>
      <div class="governance-update-panel">
        <div class="assistant-chat-shell">
          <div class="assistant-chat">
            {_kpi_assistant_messages_html(proposal)}
          </div>
          {_kpi_compose_html(url, usage_at_limit=usage_at_limit, prior_proposal_id=prior_proposal_id)}
        </div>
      </div>
    </section>
    """

    html += f"""
    <section class="card" id="kpi-generator-validation-filters">
      <h2>Validation criteria</h2>
      <p class="muted">Session-only filters for checking a calculation (e.g. one invoice or customer).
      These are not written into production SQL unless you include them in the calculation itself.</p>
      <div class="kpi-validation-shell">
        <div class="kpi-filter-header">
          <span>Fact</span>
          <span>Field</span>
          <span>Value</span>
          <span></span>
        </div>
        <div id="kpi-filter-rows"></div>
        <div class="kpi-filter-actions">
          <button type="button" class="btn btn-secondary" id="kpi-add-filter">Add filter</button>
        </div>
      </div>
    </section>
    """

    if proposal and draft:
        proposal_id = escape(str(proposal.get("proposal_id") or ""))
        html += _kpi_proposal_results_html(
            url,
            proposal_id=proposal_id,
            draft=draft,
            last_val=last_val,
        )

    html += """
      </div>
      <div class="semantic-builder-keys-panel" id="kpi-generator-panel-review"
           data-kpi-panel="review" role="tabpanel"""
    html += '" hidden>' if tab != "review" else ">"
    html += f"""
      <section class="card pack-card" id="kpi-generator-review">
        {_kpi_review_drafts_html(url, drafts, base_version=base_version)}
      </section>
      </div>
    </section>
    """

    html += _kpi_filters_script(
        facts=facts,
        fields_by_fact=fields_by_fact,
        saved_filters=saved_filters,
    )
    html += _kpi_tabs_script()
    html += version_bump_script()
    html += _kpi_scroll_script()
    html += _kpi_compose_script()
    return html


def _validation_table_html(last_val: dict[str, Any] | None) -> str:
    if not last_val:
        return '<p class="muted">No validation run yet.</p>'
    result = last_val.get("result") or {}
    columns = result.get("columns") or []
    rows = result.get("rows") or []
    if not columns:
        return f'<p class="muted">Validation finished (execution {escape(str(result.get("execution_id") or ""))}).</p>'
    head = "".join(f"<th>{escape(str(c))}</th>" for c in columns)
    body_rows = []
    for row in rows[:50]:
        cells = "".join(f"<td>{escape(str(row.get(c, '')))}</td>" for c in columns)
        body_rows.append(f"<tr>{cells}</tr>")
    return (
        f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead>'
        f"<tbody>{''.join(body_rows)}</tbody></table></div>"
    )
