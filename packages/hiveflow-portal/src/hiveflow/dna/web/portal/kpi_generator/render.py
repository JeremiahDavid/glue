"""KPI Generator portal page markup."""

from __future__ import annotations

import json
from datetime import datetime
from meshflow.compat import UTC
from html import escape
from typing import Any, Callable

from markupsafe import Markup

from meshflow.dna.settings import DnaSettings
from meshflow.dna.web.portal.governance_helpers.proposals import (
    bump_major_version,
    bump_minor_version,
    bump_patch_version,
)
from meshflow.dna.web.portal.kpi_generator.catalog import (
    build_fields_by_fact,
    list_fact_options,
)
from meshflow.dna.web.portal.kpi_generator.drafts import (
    iter_proposal_drafts,
    primary_draft,
    proposal_generation_status,
    proposal_intent,
)
from meshflow.dna.web.portal.kpi_generator.integrity import (
    REVIEW_KANBAN_STAGES,
    draft_target_key,
    draft_target_label,
    group_pending_drafts,
    partition_proposals_by_stage,
    proposal_integrity_status,
)
from meshflow.dna.web.portal.kpi_generator.sql_format import format_kpi_sql
from meshflow.dna.web.portal.version_bump import (
    version_bump_field_html,
    version_bump_script,
)
from meshflow.dna.web.templating import render_template
from meshflow.dna.workflow import load_production_pack, load_workflow_state


def _json_for_script(payload: Any) -> str:
    """Serialize JSON for inline <script> without closing the HTML script element."""
    return json.dumps(payload).replace("<", "\\u003c")


def _kpi_chat_entries(proposal: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not proposal:
        return []
    snapshot = proposal.get("governance_snapshot") or {}
    history = proposal.get("chat_history") or snapshot.get("chat_history") or []
    if not isinstance(history, list):
        return []
    return [entry for entry in history if isinstance(entry, dict)]


def _kpi_chat_transcript_html(proposal: dict[str, Any] | None) -> str:
    """Render every user/assistant turn, falling back to the last prompt."""
    entries = []
    for entry in _kpi_chat_entries(proposal):
        role = str(entry.get("role") or "user").strip().lower()
        text = str(entry.get("text") or "").strip()
        if not text:
            continue
        entries.append({"is_user": role == "user", "text": text})
    if entries:
        return render_template("portal/kpi_generator/_chat_bubbles.html", entries=entries)

    prompt = ""
    if proposal:
        snapshot = proposal.get("governance_snapshot") or {}
        prompt = str(proposal.get("prompt") or snapshot.get("prompt") or "").strip()
    if prompt:
        return render_template(
            "portal/kpi_generator/_chat_bubbles.html", entries=[{"is_user": True, "text": prompt}]
        )
    return ""


def _kpi_assistant_messages_html(proposal: dict[str, Any] | None) -> str:
    empty = (
        '<p class="pack-card-lead">'
        "Describe the KPI you want — natural language in, Athena SQL out."
        "</p>"
    )
    generating = proposal_generation_status(proposal) == "pending"
    if not proposal:
        return empty
    html = _kpi_chat_transcript_html(proposal)
    if not _kpi_chat_entries(proposal) and not generating:
        draft = proposal.get("draft") or {}
        assistant_text = str(draft.get("summary") or draft.get("calculation") or "").strip()
        if not assistant_text:
            assistant_text = "Draft KPI SQL is ready — review the proposal below."
        html += render_template(
            "portal/kpi_generator/_assistant_bubble.html", bubble_id=None, text=assistant_text
        )
    if generating:
        html += render_template(
            "portal/kpi_generator/_assistant_bubble.html",
            bubble_id="kpi-generator-generating",
            text="Working on this…",
        )
    return html or empty


def _kpi_compose_html(
    url: Callable[[str], str],
    *,
    usage_at_limit: bool = False,
    prior_proposal_id: str = "",
    generating: bool = False,
) -> str:
    if usage_at_limit:
        return (
            '<p class="pack-card-lead governance-usage-limit">'
            "Monthly Bedrock allowance reached. Review an existing proposal below "
            "or wait until next month to generate a new KPI."
            "</p>"
        )
    if generating:
        return '<p class="pack-card-lead">Hang tight — this usually takes under a minute.</p>'
    return render_template(
        "portal/kpi_generator/_compose_form.html",
        action_url=url("/portal/dna/kpi-generator"),
        prior_proposal_id=prior_proposal_id or None,
    )


def _kpi_scroll_script() -> str:
    return """
<script>
(function () {
  function scrollChatToBottom() {
    var chat = document.querySelector("#kpi-generator-prompt .assistant-chat");
    if (!chat) return;
    chat.scrollTop = chat.scrollHeight;
  }
  scrollChatToBottom();
  window.requestAnimationFrame(scrollChatToBottom);

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


def _kpi_generation_poll_script(status_url: str) -> str:
    url_json = _json_for_script(status_url)
    return f"""
<script>
(function () {{
  if (!document.getElementById("kpi-generator-generating")) return;
  var statusUrl = {url_json};
  var attempts = 0;
  var timer = setInterval(function () {{
    attempts += 1;
    if (attempts > 90) {{
      clearInterval(timer);
      return;
    }}
    fetch(statusUrl, {{ credentials: "same-origin", headers: {{ "Accept": "application/json" }} }})
      .then(function (response) {{ return response.json(); }})
      .then(function (data) {{
        var status = (data && data.generation_status) || "";
        if (status === "pending") return;
        clearInterval(timer);
        window.location.reload();
      }})
      .catch(function () {{}});
  }}, 2000);
}})();
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
    return render_template(
        "portal/kpi_generator/_grain_columns.html", columns=[str(col) for col in columns]
    )


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
    return render_template(
        "portal/kpi_generator/_chip_list.html", items=[str(item) for item in items]
    )


def _draft_layer_block_html(draft: dict[str, Any], *, editor_id: str) -> str:
    fields = draft.get("fields_used") or []
    filters = draft.get("filters_applied") or []
    calc = str(draft.get("calculation") or draft.get("summary") or "").strip()
    sql = format_kpi_sql(str(draft.get("sql") or ""))
    layer = str(draft.get("layer") or "").strip().lower()
    sql_heading = "Contribution SQL" if layer == "silver" else "Athena SQL"
    return render_template(
        "portal/kpi_generator/_draft_layer_block.html",
        layer_label=layer or "—",
        mode=str(draft.get("mode") or "—"),
        tid=str(draft.get("id") or "—"),
        target=str(draft.get("target_entity") or draft.get("output_id") or "—"),
        grain_html=Markup(_format_grain_columns_html(draft)),
        silver_notice=Markup(_silver_enhancement_notice_html(draft)),
        fields_html=Markup(_kpi_chip_list_html(fields)),
        filters_html=Markup(_kpi_chip_list_html(filters)),
        calc=calc or "—",
        sql_heading=sql_heading,
        editor_id=editor_id,
        sql=sql,
    )


def _kpi_discard_form_html(url: Callable[[str], str], proposal_id: str) -> str:
    return f"""
          <form method="post" action="{escape(url('/portal/dna/kpi-generator'))}" class="assistant-approve-form" id="kpi-save-draft-form">
            <input type="hidden" name="proposal_id" value="{escape(proposal_id)}" />
            <div class="assistant-approve-actions">
              <button type="submit" name="action" value="discard_draft" class="btn btn-secondary" id="kpi-discard-draft" formnovalidate>Discard Draft</button>
            </div>
          </form>
    """


def _kpi_reuse_results_html(
    url: Callable[[str], str],
    *,
    proposal: dict[str, Any],
    last_val: dict[str, Any] | None,
) -> str:
    proposal_id = escape(str(proposal.get("proposal_id") or ""))
    reuse = proposal.get("reuse") if isinstance(proposal.get("reuse"), dict) else {}
    reason = str(reuse.get("reason") or "").strip()
    output_id = str(reuse.get("output_id") or "").strip()
    column = str(reuse.get("column") or "").strip()
    sql = format_kpi_sql(str(reuse.get("sql") or ""))
    target = escape(output_id or column or "existing DNA")
    sql_block = ""
    validate_block = ""
    if sql:
        sql_block = f"""
          <div class="assistant-pack-block">
            <h3 class="kpi-section-heading">Preview SQL</h3>
            <textarea id="kpi-draft-sql" class="kpi-sql-block kpi-sql-editor" rows="10"
              spellcheck="false" data-kpi-sql-layer="gold">{escape(sql)}</textarea>
          </div>
        """
        validate_block = f"""
          <div class="assistant-pack-block" id="kpi-generator-validation">
            <h3 class="kpi-section-heading">Validation</h3>
            {_validation_table_html(last_val)}
            <form method="post" action="{escape(url('/portal/dna/kpi-generator'))}" style="margin-top:0.75rem">
              <input type="hidden" name="action" value="validate" />
              <input type="hidden" name="proposal_id" value="{proposal_id}" />
              <p class="pack-card-lead">Runs the preview query with the validation criteria filters above.</p>
              <button type="submit" class="btn btn-secondary" id="kpi-run-validate">Run validation</button>
            </form>
          </div>
        """
    return f"""
        <section class="card pack-card" id="kpi-generator-results">
          <h2>Existing DNA</h2>
          <p class="pack-card-lead">This request can be answered without a new transform.</p>
          <dl class="pack-meta">
            <div><dt>Reuse</dt><dd><code>{target}</code></dd></div>
          </dl>
          <div class="assistant-pack-block">
            <h3 class="kpi-section-heading">Why</h3>
            <p class="kpi-calculation">{escape(reason) or "—"}</p>
          </div>
          {sql_block}
          {validate_block}
          {_kpi_discard_form_html(url, proposal_id)}
        </section>
        """


def _kpi_proposal_results_html(
    url: Callable[[str], str],
    *,
    proposal_id: str,
    draft: dict[str, Any],
    last_val: dict[str, Any] | None,
    drafts: list[dict[str, Any]] | None = None,
) -> str:
    items = [item for item in (drafts or [draft]) if isinstance(item, dict) and item]
    if not items:
        items = [draft] if draft else []
    primary = primary_draft(items)
    layer_blocks = ""
    for item in items:
        layer = str(item.get("layer") or "").strip().lower() or "gold"
        is_primary = item is primary
        editor_id = "kpi-draft-sql" if is_primary else f"kpi-draft-sql-{layer}"
        layer_blocks += _draft_layer_block_html(item, editor_id=editor_id)
    lead = (
        "Review the draft SQL for each layer, validate against sample filters, then save as a DNA draft for review."
        if len(items) > 1
        else "Review the draft SQL, validate against sample filters, then save as a DNA draft for review."
    )
    return f"""
        <section class="card pack-card" id="kpi-generator-results">
          <h2>Proposed calculation</h2>
          <p class="pack-card-lead">{lead}</p>
          {layer_blocks}
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
          <form method="post" action="{escape(url('/portal/dna/kpi-generator'))}" class="assistant-approve-form" id="kpi-save-draft-form">
            <input type="hidden" name="proposal_id" value="{proposal_id}" />
            <div class="assistant-approve-actions">
              <button type="submit" name="action" value="save_draft" class="btn btn-primary" id="kpi-save-draft">Save Draft</button>
              <button type="submit" name="action" value="discard_draft" class="btn btn-secondary" id="kpi-discard-draft" formnovalidate>Discard Draft</button>
            </div>
          </form>
        </section>
        """


def _proposal_integrity_status_html(proposal: dict[str, Any]) -> str:
    status = proposal_integrity_status(proposal)
    validation = proposal.get("integrity_validation") or {}
    if status == "passed":
        return (
            '<p class="kpi-kanban-tile-status">'
            '<span class="kpi-integrity-passed">Integrity passed</span></p>'
        )
    if status == "failed":
        errors = validation.get("errors") or ["Validation failed"]
        err_text = "; ".join(escape(str(err)) for err in errors)
        return (
            '<p class="kpi-kanban-tile-status">'
            f'<span class="kpi-integrity-failed">Failed</span> — {err_text}</p>'
        )
    return (
        '<p class="kpi-kanban-tile-status">'
        '<span class="kpi-integrity-pending">Not validated</span></p>'
    )


_KANBAN_PILLAR_META: dict[str, dict[str, str]] = {
    "integrity": {
        "title": "Integrity Validation",
        "lead": "Run integrity checks on each KPI before it can be approved.",
    },
    "approve": {
        "title": "Approve",
        "lead": "Approve KPIs to pin SQL to production governance.",
    },
}


def _proposal_layers_label(proposal: dict[str, Any]) -> str:
    layers = [
        str(item.get("layer") or "").strip().lower()
        for item in iter_proposal_drafts(proposal)
        if str(item.get("layer") or "").strip()
    ]
    if not layers:
        draft = proposal.get("draft") or {}
        return str(draft.get("layer") or "—")
    return " + ".join(layers)


def _proposal_targets_label(proposal: dict[str, Any]) -> str:
    parts: list[str] = []
    for item in iter_proposal_drafts(proposal):
        target = str(item.get("target_entity") or item.get("output_id") or "").strip()
        if target:
            parts.append(target)
    if parts:
        return " / ".join(parts)
    draft = proposal.get("draft") or {}
    return str(draft.get("target_entity") or draft.get("output_id") or "—")


def _kpi_proposal_preview_html(
    proposal: dict[str, Any],
    *,
    show_approved_version: bool = False,
    show_validation_results: bool = False,
) -> str:
    """Shared details layout for the publish preview dialog and kanban View details."""
    snapshot = proposal.get("governance_snapshot") or {}
    drafts = iter_proposal_drafts(proposal)
    if not drafts:
        snapshot_drafts = snapshot.get("drafts")
        if isinstance(snapshot_drafts, list) and snapshot_drafts:
            drafts = [item for item in snapshot_drafts if isinstance(item, dict)]
    draft = primary_draft(drafts) or proposal.get("draft") or snapshot.get("draft") or {}
    last_val = proposal.get("last_validation") or snapshot.get("last_validation")
    calc = str(
        draft.get("calculation")
        or draft.get("summary")
        or snapshot.get("calculation")
        or ""
    ).strip()
    transcript = _kpi_chat_transcript_html(proposal)
    if not transcript:
        transcript = '<p class="kpi-preview-calc">—</p>'
    layer = escape(_proposal_layers_label(proposal))
    mode = escape(str(draft.get("mode") or "—"))
    target = escape(_proposal_targets_label(proposal))
    try:
        target_key = escape(draft_target_key(draft))
    except ValueError:
        target_key = "—"
    grain_html = "".join(_format_grain_columns_html(item) for item in drafts) or _format_grain_columns_html(draft)
    approved_version = str(proposal.get("approved_version") or "").strip()
    version_row = ""
    if show_approved_version and approved_version:
        version_row = (
            "<div><dt>Approved version</dt>"
            f"<dd><code>{escape(approved_version)}</code></dd></div>"
        )
    last_val_dict = last_val if isinstance(last_val, dict) else None
    criteria = _validation_criteria_html(last_val_dict)
    criteria_block = (
        f'<div class="kpi-preview-section"><h4>Validation criteria</h4>{criteria}</div>'
        if criteria
        else ""
    )
    results_block = ""
    if show_validation_results:
        results_block = (
            '<div class="kpi-preview-section"><h4>Validation results</h4>'
            f"{_validation_table_html(last_val_dict)}</div>"
        )
    merged = str(proposal.get("merged_enhancement_sql") or "").strip()
    merged_block = ""
    if merged:
        merged_block = (
            '<div class="kpi-preview-section">'
            "<h4>Merged entity enhancement</h4>"
            f'<pre class="kpi-preview-sql">{escape(format_kpi_sql(merged))}</pre>'
            "</div>"
        )
    sql_blocks = ""
    items = drafts or [draft]
    for item in items:
        sql = format_kpi_sql(str(item.get("sql") or ""))
        sql_label = (
            "Contribution SQL"
            if str(item.get("layer") or "").lower() == "silver"
            else "Athena SQL"
        )
        layer_name = escape(str(item.get("layer") or "gold"))
        sql_blocks += (
            '<div class="kpi-preview-section">'
            f"<h4>{sql_label} ({layer_name})</h4>"
            f'<pre class="kpi-preview-sql">{escape(sql) or "—"}</pre>'
            "</div>"
        )
    return f"""
      <div class="kpi-preview">
        <div class="kpi-preview-section">
          <h4>Conversation</h4>
          <div class="kpi-preview-chat">{transcript}</div>
        </div>
        <dl class="kpi-preview-meta">
          <div><dt>Layer</dt><dd>{layer}</dd></div>
          <div><dt>Mode</dt><dd>{mode}</dd></div>
          <div><dt>Target</dt><dd><code>{target}</code></dd></div>
          <div><dt>Target key</dt><dd><code>{target_key}</code></dd></div>
          {version_row}
          {grain_html}
        </dl>
        <div class="kpi-preview-section">
          <h4>Calculation</h4>
          <p class="kpi-preview-calc">{escape(calc) or "—"}</p>
        </div>
        {criteria_block}
        {results_block}
        {sql_blocks}
        {merged_block}
      </div>
    """


def _kpi_approved_chip_html(
    url: Callable[[str], str],
    proposal: dict[str, Any],
) -> str:
    draft = proposal.get("draft") or {}
    proposal_id = str(proposal.get("proposal_id") or "").strip()
    tid = escape(str(draft.get("id") or proposal_id or "—"))
    layer = escape(_proposal_layers_label(proposal))
    dialog_id = escape(f"kpi-approved-dialog-{proposal_id or tid}")
    body = _kpi_proposal_preview_html(
        proposal,
        show_approved_version=True,
        show_validation_results=False,
    )
    remove_form = ""
    if proposal_id:
        remove_form = f"""
          <form method="post" action="{escape(url('/portal/dna/kpi-generator'))}"
                class="kpi-approved-chip-remove">
            <input type="hidden" name="proposal_id" value="{escape(proposal_id)}" />
            <button type="submit" name="action" value="reject" formnovalidate
                    class="kpi-approved-chip-x" aria-label="Remove {tid} from publish queue"
                    title="Remove from publish queue">&times;</button>
          </form>
        """
    return f"""
      <li class="kpi-approved-chip">
        <button type="button" class="kpi-approved-chip-open" data-kpi-dialog="{dialog_id}"
                aria-haspopup="dialog">
          <code>{tid}</code> · {layer}
        </button>
        {remove_form}
        <dialog id="{dialog_id}" class="kpi-approved-dialog">
          <div class="kpi-approved-dialog-head">
            <h3><code>{tid}</code> · {layer}</h3>
            <form method="dialog">
              <button type="submit" class="btn btn-secondary btn-sm">Close</button>
            </form>
          </div>
          <div class="kpi-approved-dialog-body">{body}</div>
        </dialog>
      </li>
    """


def _kpi_approved_dialog_script() -> str:
    return """
<script>
(function () {
  if (window.__kpiApprovedDialogBound) return;
  window.__kpiApprovedDialogBound = true;
  document.addEventListener("click", function (event) {
    var btn = event.target && event.target.closest
      ? event.target.closest("[data-kpi-dialog]")
      : null;
    if (!btn) return;
    var id = btn.getAttribute("data-kpi-dialog");
    if (!id) return;
    var dialog = document.getElementById(id);
    if (dialog && typeof dialog.showModal === "function") {
      dialog.showModal();
    }
  });
})();
</script>
"""


def _group_merged_enhancement_sql(proposals: list[dict[str, Any]]) -> str:
    latest = ""
    latest_at = ""
    for proposal in proposals:
        sql = str(proposal.get("merged_enhancement_sql") or "").strip()
        if not sql:
            continue
        stamp = str(proposal.get("approved_at") or proposal.get("saved_at") or "")
        if not latest or stamp >= latest_at:
            latest = sql
            latest_at = stamp
    return latest


def _kpi_approved_group_html(
    url: Callable[[str], str],
    target_key: str,
    proposals: list[dict[str, Any]],
) -> str:
    layer, _, _ = target_key.partition(":")
    merged = _group_merged_enhancement_sql(proposals) if layer == "silver" else ""
    merge_block = None
    if merged:
        count = len(proposals)
        merge_block = {
            "count_label": "1 KPI" if count == 1 else f"{count} KPIs",
            "sql": format_kpi_sql(merged),
        }
    return render_template(
        "portal/kpi_generator/_approved_group.html",
        label=draft_target_label(target_key),
        chips=[Markup(_kpi_approved_chip_html(url, proposal)) for proposal in proposals],
        merge_block=merge_block,
    )


def _kpi_review_toolbar_html(
    url: Callable[[str], str],
    *,
    base_version: str,
    approved_drafts: list[dict[str, Any]],
) -> str:
    next_patch = bump_patch_version(base_version)
    next_minor = bump_minor_version(base_version)
    next_major = bump_major_version(base_version)
    approved_count = len(approved_drafts)
    publish_label = (
        f"Publish Approved KPIs ({approved_count})"
        if approved_count
        else "Publish Approved KPIs"
    )
    toolbar_class = "kpi-review-toolbar"
    group_items = None
    if approved_drafts:
        toolbar_class += " kpi-review-toolbar-with-queue"
        groups = group_pending_drafts(approved_drafts)
        group_items = [
            Markup(_kpi_approved_group_html(url, target_key, group))
            for target_key, group in groups.items()
        ]
    version_field = Markup(
        version_bump_field_html(
            input_id="kpi-review-next-version",
            input_name="next_sql_version",
            label="Next governance version",
            value=next_patch,
            base_version=base_version,
            next_patch=next_patch,
            next_minor=next_minor,
            next_major=next_major,
            field_class="form-field version-bump-field",
        )
    )
    return render_template(
        "portal/kpi_generator/_review_toolbar.html",
        toolbar_class=toolbar_class,
        action_url=url("/portal/dna/kpi-generator"),
        version_field=version_field,
        publish_disabled=not approved_count,
        publish_label=publish_label,
        group_items=group_items,
    )


def _kpi_kanban_tile_actions_html(
    url: Callable[[str], str],
    *,
    stage: str,
    proposal: dict[str, Any],
) -> str:
    proposal_id = str(proposal.get("proposal_id") or "")
    draft = primary_draft(iter_proposal_drafts(proposal)) or proposal.get("draft") or {}
    try:
        target_key = draft_target_key(draft)
    except ValueError:
        target_key = ""
    return render_template(
        "portal/kpi_generator/_kanban_tile_actions.html",
        action_url=url("/portal/dna/kpi-generator"),
        stage=stage,
        proposal_id=proposal_id,
        target_key=target_key,
    )


def _kpi_kanban_tile_html(
    url: Callable[[str], str],
    *,
    stage: str,
    proposal: dict[str, Any],
) -> str:
    draft = primary_draft(iter_proposal_drafts(proposal)) or proposal.get("draft") or {}
    try:
        target_key = draft_target_key(draft)
    except ValueError:
        target_key = ""
    status_html = (
        Markup(
            '<p class="kpi-kanban-tile-status">'
            '<span class="kpi-integrity-passed">Ready to approve</span></p>'
        )
        if stage == "approve"
        else Markup(_proposal_integrity_status_html(proposal))
    )
    return render_template(
        "portal/kpi_generator/_kanban_tile.html",
        proposal_id=str(proposal.get("proposal_id") or ""),
        stage=stage,
        tid=str(draft.get("id") or "—"),
        layer=_proposal_layers_label(proposal),
        mode=str(draft.get("mode") or "—"),
        target=_proposal_targets_label(proposal),
        target_key=target_key,
        status_html=status_html,
        actions=Markup(_kpi_kanban_tile_actions_html(url, stage=stage, proposal=proposal)),
        body=Markup(
            _kpi_proposal_preview_html(
                proposal, show_approved_version=False, show_validation_results=True
            )
        ),
    )


def _kpi_kanban_pillar_html(
    url: Callable[[str], str],
    *,
    stage: str,
    proposals: list[dict[str, Any]],
) -> str:
    meta = _KANBAN_PILLAR_META[stage]
    tiles = [
        Markup(_kpi_kanban_tile_html(url, stage=stage, proposal=proposal)) for proposal in proposals
    ]
    return render_template(
        "portal/kpi_generator/_kanban_pillar.html",
        stage=stage,
        title=meta["title"],
        lead=meta["lead"],
        count=len(proposals),
        tiles=tiles,
    )


def _kpi_review_drafts_html(
    url: Callable[[str], str],
    pending_drafts: list[dict[str, Any]],
    *,
    base_version: str,
    approved_drafts: list[dict[str, Any]] | None = None,
) -> str:
    approved = approved_drafts or []
    toolbar = _kpi_review_toolbar_html(
        url,
        base_version=base_version,
        approved_drafts=approved,
    )
    if not pending_drafts and not approved:
        return (
            f"{toolbar}"
            '<div class="kpi-kanban-empty-state">'
            '<p class="pack-card-lead">No KPI drafts awaiting review. '
            "Generate a KPI and click <strong>Save Draft</strong> to queue it here.</p>"
            "</div>"
        )
    staged = partition_proposals_by_stage(pending_drafts)
    pillars = "".join(
        _kpi_kanban_pillar_html(url, stage=stage, proposals=staged.get(stage, []))
        for stage in REVIEW_KANBAN_STAGES
    )
    return f"""
      {toolbar}
      <div class="kpi-kanban-board" role="region" aria-label="KPI review workflow">
        {pillars}
      </div>
    """


def _kpi_review_version_sync_script() -> str:
    return """
<script>
(function () {
  function syncReviewVersion() {
    var source = document.querySelector("#kpi-review-toolbar-form [data-version-input]");
    if (!source) return;
    var value = (source.value || "").trim();
    document.querySelectorAll("[data-review-version-sync]").forEach(function (input) {
      input.value = value;
    });
  }
  document.addEventListener("input", function (event) {
    if (event.target && event.target.matches("#kpi-review-toolbar-form [data-version-input]")) {
      syncReviewVersion();
    }
  });
  document.addEventListener("click", function (event) {
    var btn = event.target && event.target.closest
      ? event.target.closest("#kpi-review-toolbar-form [data-bump]")
      : null;
    if (btn) window.setTimeout(syncReviewVersion, 0);
  });
  syncReviewVersion();
})();
</script>
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
    <div class="semantic-builder-keys-tabs" role="tablist" aria-label="DNA Engine">
      <button type="button" class="semantic-builder-keys-tab{" active" if generator_active else ""}" role="tab"
        data-kpi-tab="generator" aria-selected="{"true" if generator_active else "false"}"
        aria-controls="kpi-generator-panel-generator">DNA Engine</button>
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
    if (!formEl) return;
    formEl.querySelectorAll("input[data-kpi-sql-copy]").forEach(function (node) {{
      node.remove();
    }});
    var editors = document.querySelectorAll("textarea[data-kpi-sql-layer]");
    if (editors.length) {{
      editors.forEach(function (box) {{
        var layer = box.getAttribute("data-kpi-sql-layer") || "";
        var named = document.createElement("input");
        named.type = "hidden";
        named.name = layer ? "sql_" + layer : "sql";
        named.value = box.value;
        named.setAttribute("data-kpi-sql-copy", "1");
        formEl.appendChild(named);
      }});
    }}
    var sqlBox = document.getElementById("kpi-draft-sql");
    if (sqlBox) {{
      var input = document.createElement("input");
      input.type = "hidden";
      input.name = "sql";
      input.value = sqlBox.value;
      input.setAttribute("data-kpi-sql-copy", "1");
      formEl.appendChild(input);
    }}
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
    pinned = str(refresh_status.get("pinned_version") or "???")
    published = str(refresh_status.get("published_version") or "???")
    published_at_raw = str(refresh_status.get("published_at") or "").strip()
    published_at = _format_datetime_minute(published_at_raw) if published_at_raw else "???"
    is_stale = bool(refresh_status.get("is_stale"))
    in_progress = bool(quota.get("in_progress"))
    at_limit = bool(quota.get("at_limit"))
    remaining = int(quota.get("remaining") or 0)
    monthly_limit = int(quota.get("monthly_limit") or 0)
    used = int(quota.get("used") or 0)
    month = str(quota.get("month") or "")

    if in_progress:
        state_label = "Refresh in progress"
        state_class = "dna-refresh-state in-progress"
        state_detail = Markup(
            "DNA silver and gold tables are being rebuilt from the pinned pack. "
            "This page will reflect the new outputs when the run completes."
        )
    elif is_stale:
        state_label = "Refresh needed"
        state_class = "dna-refresh-state stale"
        state_detail = Markup(
            f"Pinned DNA <code>v{escape(pinned)}</code> has not been fully written yet "
            f"(gold is at <code>v{escape(published)}</code>). "
            "Run a manual DNA refresh to update silver columns, certified tables, and charts."
        )
    else:
        state_label = "DNA tables current"
        state_class = "dna-refresh-state current"
        state_detail = Markup(
            f"Silver and gold match pinned DNA <code>v{escape(pinned)}</code>. "
            f"Last DNA refresh: {escape(published_at)}."
        )

    button_disabled = in_progress or at_limit
    disabled_reason = ""
    if in_progress:
        disabled_reason = "A refresh is already running."
    elif at_limit:
        disabled_reason = "Monthly manual refresh limit reached."

    return render_template(
        "portal/kpi_generator/_dna_refresh_status.html",
        form_path=form_path,
        state_class=state_class,
        state_label=state_label,
        state_detail=state_detail,
        button_disabled=button_disabled,
        remaining=remaining,
        monthly_limit=monthly_limit,
        month=month,
        show_limit_note=at_limit and not in_progress,
        used=used,
        disabled_reason=disabled_reason if disabled_reason and not at_limit else None,
    )


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
    approved_drafts: list[dict[str, Any]] | None = None,
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
    <div class="kpi-refresh-row">
    <section class="card kpi-refresh-card" id="kpi-generator-refresh">
      <h2>DNA refresh</h2>
      {dna_refresh_status_html(
          form_path=url("/portal/dna/kpi-generator"),
          refresh_status=refresh_status,
          quota=refresh_quota,
      )}
    </section>
    </div>
    """

    if not is_admin:
        html += (
            '<div class="card"><p>DNA Engine is available to portal admins.</p></div>'
        )
        return html

    generating = proposal_generation_status(proposal) == "pending"
    intent = proposal_intent(proposal) if proposal and not generating else ""
    implement_drafts = iter_proposal_drafts(proposal) if proposal and not generating else []
    reuse_sql = ""
    if proposal and intent == "reuse":
        reuse = proposal.get("reuse") if isinstance(proposal.get("reuse"), dict) else {}
        reuse_sql = str(reuse.get("sql") or "").strip()
    show_filters = (
        not generating
        and (intent == "implement" or (intent == "reuse" and bool(reuse_sql)))
    )
    facts: list[dict[str, Any]] = []
    fields_by_fact: dict[str, list[str]] = {}
    if show_filters:
        facts = list_fact_options(settings, entity_properties={})
        fields_by_fact = build_fields_by_fact(
            settings,
            entity_properties={},
            parquet_fallback=False,
        )
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
    approved = approved_drafts or []
    tab = "review" if active_tab == "review" else "generator"
    review_tab_count = len(drafts) + len(approved)
    prior_proposal_id = ""
    if proposal and str(proposal.get("status") or "").strip().lower() == "working":
        prior_proposal_id = str(proposal.get("proposal_id") or "").strip()
    workflow = load_workflow_state(settings, settings.dna_config_id)
    try:
        base_pack = load_production_pack(settings)
        base_version = str(workflow.get("active_version") or base_pack.version)
    except Exception:  # noqa: BLE001
        base_version = str(workflow.get("active_version") or "0.0.0")

    html += f"""
    <section class="semantic-builder-keys-tabs-section" id="kpi-generator-tabs"
             data-default-tab="{escape(tab)}">
      {_kpi_tabs_html(active_tab=tab, pending_count=review_tab_count)}
      <div class="semantic-builder-keys-panel" id="kpi-generator-panel-generator"
           data-kpi-panel="generator" role="tabpanel"{" hidden" if tab == "review" else ""}>
    """

    html += f"""
    <section class="card" id="kpi-generator-prompt">
      <h2>Describe the KPI</h2>
      <p class="muted">Ask for a metric the way you would in code review. The generator reuses existing DNA when it can, asks clarifying questions when it cannot, then drafts silver and/or gold SQL.</p>
      <div class="governance-update-panel">
        <div class="assistant-chat-shell">
          <div class="assistant-chat">
            {_kpi_assistant_messages_html(proposal)}
          </div>
          {_kpi_compose_html(
              url,
              usage_at_limit=usage_at_limit,
              prior_proposal_id=prior_proposal_id,
              generating=generating,
          )}
        </div>
      </div>
    </section>
    """

    if show_filters:
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

    if proposal and intent == "implement" and implement_drafts:
        proposal_id = escape(str(proposal.get("proposal_id") or ""))
        html += _kpi_proposal_results_html(
            url,
            proposal_id=proposal_id,
            draft=draft or implement_drafts[0],
            last_val=last_val,
            drafts=implement_drafts,
        )
    elif proposal and intent == "reuse":
        html += _kpi_reuse_results_html(
            url,
            proposal=proposal,
            last_val=last_val,
        )

    review_panel_attrs = " hidden" if tab != "review" else ""
    html += f"""
      </div>
      <div class="semantic-builder-keys-panel" id="kpi-generator-panel-review"
           data-kpi-panel="review" role="tabpanel"{review_panel_attrs}>
      <section class="card pack-card" id="kpi-generator-review">
        <h2>Review Drafts</h2>
        <p class="pack-card-lead">Move each KPI through integrity validation and approval.
        Use <strong>Publish Approved KPIs</strong> to materialize DNA silver and gold tables.</p>
        {_kpi_review_drafts_html(url, drafts, base_version=base_version, approved_drafts=approved)}
      </section>
      </div>
    </section>
    """

    if show_filters:
        html += _kpi_filters_script(
            facts=facts,
            fields_by_fact=fields_by_fact,
            saved_filters=saved_filters,
        )
    html += _kpi_tabs_script()
    html += version_bump_script()
    html += _kpi_review_version_sync_script()
    html += _kpi_approved_dialog_script()
    html += _kpi_scroll_script()
    html += _kpi_compose_script()
    if generating and prior_proposal_id:
        html += _kpi_generation_poll_script(
            url(f"/portal/dna/kpi-generator/status?proposal_id={prior_proposal_id}")
        )
    return html


def _validation_table_html(last_val: dict[str, Any] | None) -> str:
    if not last_val:
        return '<p class="muted">No validation run yet.</p>'
    result = last_val.get("result") or {}
    columns = result.get("columns") or []
    rows = result.get("rows") or []
    if not columns:
        return f'<p class="muted">Validation finished (execution {escape(str(result.get("execution_id") or ""))}).</p>'
    body_rows = [[str(row.get(c, "")) for c in columns] for row in rows[:50]]
    return render_template(
        "portal/kpi_generator/_validation_table.html",
        columns=[str(c) for c in columns],
        rows=body_rows,
    )
