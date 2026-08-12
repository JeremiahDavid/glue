"""KPI Generator portal page markup."""

from __future__ import annotations

import json
import re
from html import escape
from typing import Any, Callable

from meshflow.dna.settings import DnaSettings
from meshflow.dna.source_docs_reference import load_source_docs_gold_artifact
from meshflow.dna.web.portal.kpi_generator.service import (
    build_fields_by_fact,
    list_fact_options,
)


_SQL_BREAK_KEYWORDS: tuple[str, ...] = (
    "UNION ALL",
    "UNION",
    "LEFT OUTER JOIN",
    "RIGHT OUTER JOIN",
    "FULL OUTER JOIN",
    "LEFT JOIN",
    "RIGHT JOIN",
    "INNER JOIN",
    "OUTER JOIN",
    "JOIN",
    "GROUP BY",
    "ORDER BY",
    "HAVING",
    "WHERE",
    "FROM",
    "SELECT",
)


def _format_sql_for_display(sql: str) -> str:
    """Lightweight SQL pretty-printer for portal display (no extra dependencies)."""
    text = re.sub(r"\s+", " ", sql.strip().rstrip(";"))
    if not text:
        return ""
    for kw in _SQL_BREAK_KEYWORDS:
        pattern = re.compile(
            r"(?<!\w)" + kw.replace(" ", r"\s+") + r"(?=\s|$)",
            re.IGNORECASE,
        )
        text = pattern.sub("\n" + kw.upper(), text)
    lines: list[str] = []
    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        upper = line.upper()
        if upper.startswith("AND ") or upper.startswith("OR "):
            lines.append(f"  {line}")
        else:
            lines.append(line)
    return "\n".join(lines)


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
) -> str:
    if usage_at_limit:
        return (
            '<p class="pack-card-lead governance-usage-limit">'
            "Monthly Bedrock allowance reached. Review an existing proposal below "
            "or wait until next month to generate a new KPI."
            "</p>"
        )
    return f"""
      <form method="post" action="{escape(url('/portal/dna/kpi-generator'))}" class="assistant-compose">
        <input type="hidden" name="action" value="generate" />
        <div class="form-field assistant-compose-field">
          <label for="kpi-prompt">Message</label>
          <textarea id="kpi-prompt" name="prompt" rows="2" required
            class="assistant-compose-input"
            placeholder="e.g. Net sales revenue as sum of posted invoice line amounts excluding credit memos"></textarea>
        </div>
        <button type="submit" class="btn btn-primary portal-submit-btn">Send</button>
      </form>
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
    sql = _format_sql_for_display(str(draft.get("sql") or ""))
    layer = escape(str(draft.get("layer") or "—"))
    mode = escape(str(draft.get("mode") or "—"))
    tid = escape(str(draft.get("id") or "—"))
    target = escape(str(draft.get("target_entity") or draft.get("output_id") or "—"))
    return f"""
        <section class="card pack-card" id="kpi-generator-results">
          <h2>Proposed calculation</h2>
          <p class="pack-card-lead">Review the draft SQL, validate against sample filters, then save as a DNA draft for review.</p>
          <dl class="pack-meta">
            <div><dt>Layer</dt><dd>{layer}</dd></div>
            <div><dt>Mode</dt><dd>{mode}</dd></div>
            <div><dt>Transform id</dt><dd><code>{tid}</code></dd></div>
            <div><dt>Target</dt><dd><code>{target}</code></dd></div>
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
          <div class="assistant-pack-block">
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
            <h3 class="kpi-section-heading">Athena SQL</h3>
            <details class="kpi-sql-details">
              <summary>Show SQL</summary>
              <pre class="kpi-sql-block">{escape(sql)}</pre>
            </details>
          </div>
          <form method="post" action="{escape(url('/portal/dna/kpi-generator'))}" class="assistant-approve-form">
            <input type="hidden" name="action" value="save_draft" />
            <input type="hidden" name="proposal_id" value="{proposal_id}" />
            <div class="assistant-approve-actions">
              <button type="submit" class="btn btn-primary">Save Draft</button>
            </div>
          </form>
        </section>
        """


def _kpi_draft_review_item_html(
    url: Callable[[str], str],
    proposal: dict[str, Any],
) -> str:
    snapshot = proposal.get("governance_snapshot") or {}
    draft = proposal.get("draft") or snapshot.get("draft") or {}
    last_val = proposal.get("last_validation") or snapshot.get("last_validation")
    proposal_id = escape(str(proposal.get("proposal_id") or ""))
    tid = escape(str(draft.get("id") or "—"))
    layer = escape(str(draft.get("layer") or "—"))
    mode = escape(str(draft.get("mode") or "—"))
    target = escape(str(draft.get("target_entity") or draft.get("output_id") or "—"))
    version = escape(str(proposal.get("governance_version") or "—"))
    calc = str(
        draft.get("calculation")
        or draft.get("summary")
        or snapshot.get("calculation")
        or ""
    ).strip()
    sql = _format_sql_for_display(str(draft.get("sql") or snapshot.get("sql") or ""))
    prompt = escape(str(proposal.get("prompt") or snapshot.get("prompt") or ""))
    return f"""
    <div class="kpi-draft-item" data-proposal-id="{proposal_id}">
      <div class="kpi-draft-top">
        <details class="kpi-draft-section">
          <summary class="kpi-draft-section-summary">
            <span class="kpi-draft-section-summary-inner">
              <span class="kpi-draft-expand-icon" aria-hidden="true"></span>
              <span class="kpi-draft-section-title"><code>{tid}</code></span>
              <span class="kpi-draft-section-meta">{layer} · {mode}</span>
              <span class="kpi-draft-section-meta">target <code>{target}</code></span>
              <span class="kpi-draft-section-meta">v{version}</span>
            </span>
          </summary>
          <div class="kpi-draft-section-body">
            <p class="pack-card-lead"><strong>Request:</strong> {prompt or "—"}</p>
            <h4 class="kpi-section-heading">Calculation</h4>
            <p class="kpi-calculation">{escape(calc) or "—"}</p>
            <h4 class="kpi-section-heading">Validation</h4>
            {_validation_table_html(last_val if isinstance(last_val, dict) else None)}
            <h4 class="kpi-section-heading">Athena SQL</h4>
            <pre class="kpi-sql-block">{escape(sql) or "—"}</pre>
          </div>
        </details>
        <div class="kpi-draft-item-actions">
          <form method="post" action="{escape(url('/portal/dna/kpi-generator?tab=review'))}">
            <input type="hidden" name="action" value="approve" />
            <input type="hidden" name="proposal_id" value="{proposal_id}" />
            <button type="submit" class="btn btn-primary">Approve</button>
          </form>
          <form method="post" action="{escape(url('/portal/dna/kpi-generator?tab=review'))}">
            <input type="hidden" name="action" value="reject" />
            <input type="hidden" name="proposal_id" value="{proposal_id}" />
            <button type="submit" class="btn btn-secondary">Reject</button>
          </form>
        </div>
      </div>
    </div>
    """


def _kpi_review_drafts_html(
    url: Callable[[str], str],
    pending_drafts: list[dict[str, Any]],
) -> str:
    if not pending_drafts:
        return (
            '<div class="card pack-card">'
            '<p class="pack-card-lead">No KPI drafts awaiting review. '
            "Generate a KPI and click <strong>Save Draft</strong> to queue it here.</p>"
            "</div>"
        )
    items = "".join(_kpi_draft_review_item_html(url, proposal) for proposal in pending_drafts)
    return f"""
    <section class="card pack-card" id="kpi-generator-review">
      <div class="kpi-draft-bulk-actions">
        <form method="post" action="{escape(url('/portal/dna/kpi-generator?tab=review'))}" class="assistant-actions">
          <input type="hidden" name="action" value="approve_all" />
          <button type="submit" class="btn btn-primary">Approve all</button>
        </form>
        <form method="post" action="{escape(url('/portal/dna/kpi-generator?tab=review'))}" class="assistant-actions">
          <input type="hidden" name="action" value="reject_all" />
          <button type="submit" class="btn btn-secondary">Reject all</button>
        </form>
      </div>
      <div class="table-wrap kpi-draft-list">
        {items}
      </div>
    </section>
    """


def _kpi_tabs_html(
    url: Callable[[str], str],
    *,
    active_tab: str,
    pending_count: int,
) -> str:
    generator_active = active_tab != "review"
    review_active = active_tab == "review"
    review_label = f"Review Drafts ({pending_count})" if pending_count else "Review Drafts"
    return f"""
    <section class="semantic-builder-keys-tabs-section" id="kpi-generator-tabs">
      <div class="kpi-generator-tabs" role="tablist">
        <a class="kpi-generator-tab{" active" if generator_active else ""}"
           role="tab" href="{escape(url('/portal/dna/kpi-generator'))}"
           aria-selected="{"true" if generator_active else "false"}">KPI Generator</a>
        <a class="kpi-generator-tab{" active" if review_active else ""}"
           role="tab" href="{escape(url('/portal/dna/kpi-generator?tab=review'))}"
           aria-selected="{"true" if review_active else "false"}">{escape(review_label)}</a>
      </div>
    </section>
    """


def _kpi_filters_script(
    *,
    facts: list[dict[str, Any]],
    fields_by_fact: dict[str, list[str]],
) -> str:
    facts_json = _json_for_script(facts)
    fields_json = _json_for_script(fields_by_fact)
    return f"""
<script>
(function () {{
  var facts = {facts_json};
  var fieldsByFact = {fields_json};
  var root = document.getElementById("kpi-filter-rows");
  var section = document.getElementById("kpi-generator-validation-filters");
  if (!root || !section) return;

  function fillFieldSelect(factSel, fieldSel) {{
    var fields = fieldsByFact[factSel.value] || [];
    fieldSel.textContent = "";
    fields.forEach(function (name) {{
      var opt = document.createElement("option");
      opt.value = name;
      opt.textContent = name;
      fieldSel.appendChild(opt);
    }});
  }}

  function addRow() {{
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
    fillFieldSelect(factSel, fieldSel);

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

  var validateBtn = document.getElementById("kpi-run-validate");
  if (validateBtn) {{
    var validateForm = validateBtn.closest("form");
    if (validateForm) {{
      validateForm.addEventListener("submit", function (ev) {{
        var formEl = ev.target;
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
      }});
    }}
  }}

  addRow();
}})();
</script>
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
    usage_at_limit = bool((usage or {}).get("at_limit"))
    drafts = pending_drafts or []
    tab = "review" if active_tab == "review" else "generator"

    html += _kpi_tabs_html(url, active_tab=tab, pending_count=len(drafts))

    if tab == "review":
        html += _kpi_review_drafts_html(url, drafts)
        return html

    html += f"""
    <section class="card" id="kpi-generator-prompt">
      <h2>Describe the KPI</h2>
      <p class="muted">Source Browser gold YAML is used as reference. Save drafts for review;
      approved SQL is replayed verbatim on refresh.</p>
      <div class="governance-update-panel">
        <div class="assistant-chat-shell">
          <div class="assistant-chat">
            {_kpi_assistant_messages_html(proposal)}
          </div>
          {_kpi_compose_html(url, usage_at_limit=usage_at_limit)}
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

    html += _kpi_filters_script(facts=facts, fields_by_fact=fields_by_fact)
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
