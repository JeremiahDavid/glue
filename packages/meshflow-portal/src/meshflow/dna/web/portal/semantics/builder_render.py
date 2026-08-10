"""Semantic Builder portal — overview, join review, and publish workflow."""

from __future__ import annotations

import html
import json
from typing import Any, Callable

from werkzeug.wrappers import Request, Response

from meshflow.dna.semantic_join_stats import format_join_stats_summary, format_pk_stats_summary
from meshflow.dna.semantic_model import (
    BUILDER_STEPS,
    build_semantic_builder_options,
    builder_step_summary,
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
from meshflow.dna.web.portal.dna_nav import BUILDER_STEP_PATHS, SEMANTIC_BUILDER_ROOT
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
    "deferred": "semantics-status-proposed",
}

_BUILDER_STEP_LABELS = {
    "keys": ("1", "Primary & foreign keys", "Profile silver data and confirm keys per table"),
    "relationships": ("2", "Relationships", "Review joins built from approved keys"),
    "tags": ("3", "Semantic tags", "Map columns to operational concepts"),
}

_QUESTION_ACTION_LABELS = {
    "primary_key": "Primary key",
    "foreign_key": "Foreign key",
    "relationship": "Relationship",
    "column_tag": "Column tag",
    "acknowledge": "Decision",
}


def _attr_escape(value: str) -> str:
    return html.escape(value, quote=True)


_BUILDER_STEP_PREREQUISITES: dict[str, tuple[str, str]] = {
    "keys": (
        "start",
        "Start profiling from the Semantic Builder home page to scan silver tables and propose keys.",
    ),
    "relationships": (
        "keys",
        "Complete step 1 — review and approve primary and foreign keys — before reviewing relationships.",
    ),
    "tags": (
        "relationships",
        "Complete step 2 — review and approve table relationships — before tagging columns.",
    ),
}


def _step_is_accessible(step: str, workflow: dict[str, Any]) -> bool:
    if not workflow.get("init_completed"):
        return False
    if step == "keys":
        return True
    completed = workflow.get("steps_completed") or {}
    if completed.get(step):
        return True
    current = str(workflow.get("current_step") or BUILDER_STEPS[0])
    try:
        current_idx = BUILDER_STEPS.index(current)
        step_idx = BUILDER_STEPS.index(step)
    except ValueError:
        return False
    if step_idx < current_idx:
        return True
    prereq = _BUILDER_STEP_PREREQUISITES.get(step)
    if not prereq:
        return True
    prereq_step = prereq[0]
    if prereq_step == "start":
        return True
    return bool(completed.get(prereq_step))


def _builder_step_nav(
    workflow: dict[str, Any],
    *,
    url: Callable[[str], str],
    active_page: str | None,
) -> str:
    completed = workflow.get("steps_completed") or {}
    current = str(workflow.get("current_step") or BUILDER_STEPS[0])
    items = ""
    for step in BUILDER_STEPS:
        number, title, subtitle = _BUILDER_STEP_LABELS[step]
        step_href = escape(url(BUILDER_STEP_PATHS[step]))
        if completed.get(step):
            state, state_label = "done", "Completed · revisit"
        elif step == current:
            state, state_label = "active", "In progress"
        else:
            state, state_label = "pending", "Up next"
        if active_page == step:
            state = "current"
            state_label = "Revisiting" if completed.get(step) else "In progress"
        accessible = _step_is_accessible(step, workflow)
        locked_class = "" if accessible else " semantic-builder-step-nav-locked"
        revisitable_class = " semantic-builder-step-nav-revisitable" if completed.get(step) and accessible else ""
        items += f"""
        <a class="semantic-builder-step-nav-item semantic-builder-step-nav-{state}{locked_class}{revisitable_class}"
           href="{step_href}">
          <span class="semantic-builder-step-num">{escape(number)}</span>
          <div class="semantic-builder-step-body">
            <strong>{escape(title)}</strong>
            <span class="semantic-builder-step-sub">{escape(subtitle)}</span>
            <span class="semantic-builder-step-state">{escape(state_label)}</span>
          </div>
        </a>
        """
    return f'<nav class="semantic-builder-step-nav" aria-label="Semantic builder steps">{items}</nav>'


def _pending_decision_questions(questions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    pending = [
        q
        for q in questions
        if isinstance(q, dict) and str(q.get("status") or "open") in ("open", "deferred")
    ]
    return sorted(
        pending,
        key=lambda item: (
            0 if str(item.get("status") or "open") == "open" else 1,
            str(item.get("id") or ""),
        ),
    )


def _builder_decisions_nav(
    workflow: dict[str, Any],
    *,
    url: Callable[[str], str],
    active_page: str | None,
    pending_count: int,
) -> str:
    if not workflow.get("init_completed"):
        return ""
    href = escape(url(BUILDER_STEP_PATHS["decisions"]))
    active = " semantic-builder-sub-nav-current" if active_page == "decisions" else ""
    badge = (
        f'<span class="semantic-builder-sub-nav-badge">{pending_count}</span>'
        if pending_count
        else ""
    )
    return f"""
    <nav class="semantic-builder-sub-nav" aria-label="Open decisions">
      <a class="semantic-builder-sub-nav-item{active}" href="{href}">
        Open decisions{badge}
      </a>
    </nav>
    """


def _step_gate_message(
    page_step: str,
    workflow: dict[str, Any],
    *,
    url: Callable[[str], str],
) -> str:
    if _step_is_accessible(page_step, workflow):
        return ""
    prereq = _BUILDER_STEP_PREREQUISITES.get(page_step)
    if not prereq:
        return ""
    prereq_step, message = prereq
    if prereq_step == "start":
        action = (
            f'<a class="btn btn-secondary btn-sm" href="{escape(url(SEMANTIC_BUILDER_ROOT))}">'
            "Go to Semantic Builder home</a>"
        )
    else:
        action = (
            f'<a class="btn btn-secondary btn-sm" href="{escape(url(BUILDER_STEP_PATHS[prereq_step]))}">'
            f"Go to step {BUILDER_STEPS.index(prereq_step) + 1}</a>"
        )
    return f"""
    <div class="semantic-builder-gate">
      <p class="pack-card-lead">{escape(message)}</p>
      <p>{action}</p>
    </div>
    """


def _step_revisit_notice(page_step: str, workflow: dict[str, Any]) -> str:
    completed = workflow.get("steps_completed") or {}
    if not completed.get(page_step):
        return ""
    messages = {
        "keys": (
            "You completed this step earlier. Update key approvals here if needed, "
            "then re-complete to regenerate joins from your keys."
        ),
        "relationships": (
            "You completed this step earlier. Update join approvals here if needed, "
            "then re-complete to refresh semantic tagging."
        ),
        "tags": (
            "You completed this step earlier. You can still update column tags before publishing."
        ),
    }
    message = messages.get(page_step, "")
    if not message:
        return ""
    return f"""
    <div class="semantic-builder-revisit">
      <p class="pack-card-lead">{escape(message)}</p>
    </div>
    """


def _landing_page_content(
    workflow: dict[str, Any],
    *,
    url: Callable[[str], str],
    is_admin: bool,
    source_reference: dict[str, Any] | None = None,
) -> str:
    init_completed = bool(workflow.get("init_completed"))
    ref = source_reference or {}
    ref_line = ""
    if int(ref.get("approved_build_count") or 0) > 0:
        ref_line = (
            f'<p class="pack-card-lead">Reference library: '
            f'{int(ref.get("approved_build_count") or 0)} approved '
            f'{escape(str(ref.get("source") or ""))} build(s) inform profiling consensus.</p>'
        )
    if init_completed:
        current = str(workflow.get("current_step") or BUILDER_STEPS[0])
        continue_href = escape(url(BUILDER_STEP_PATHS.get(current, BUILDER_STEP_PATHS["keys"])))
        number, title, _ = _BUILDER_STEP_LABELS.get(current, _BUILDER_STEP_LABELS["keys"])
        action = (
            f'<a class="btn semantic-builder-start-btn" href="{continue_href}">'
            f"Continue to step {escape(number)} — {escape(title)}</a>"
        )
        lead = "Profiling has started. Continue where you left off or jump to any step above."
    elif is_admin:
        action = (
            '<button type="button" class="btn semantic-builder-start-btn" id="semantic-init-btn">'
            "Start semantic build</button>"
        )
        lead = (
            "Profile silver tables to propose primary and foreign keys, then review relationships "
            "and tag columns before gold compile."
        )
    else:
        action = ""
        lead = "An administrator must start the semantic build before you can review keys, joins, and tags."
    return f"""
    <section class="section semantic-builder-landing">
      <p class="pack-card-lead">{escape(lead)}</p>
      {ref_line}
      <div class="semantic-builder-landing-action">{action}</div>
      <p class="pack-card-lead semantic-builder-landing-hint">
        Meshflow qualifies silver in three review steps. Use the step links above to jump directly
        to keys, relationships, or column tags once profiling has started.
      </p>
    </section>
    """


def _pk_key_display(entity: dict[str, Any]) -> tuple[str, str]:
    """Return primary-key column label and stats label for step 1."""
    pk_raw = str(entity.get("primary_key") or "").strip()
    pk_stats = entity.get("pk_stats") if isinstance(entity.get("pk_stats"), dict) else {}
    if pk_stats.get("pk_unique") and pk_raw:
        return pk_raw, format_pk_stats_summary(pk_stats)
    if pk_raw and pk_stats:
        return "—", "No known PK"
    if pk_raw:
        return pk_raw, "—"
    return "—", "No known PK"


def _fk_target_entity(attribute: dict[str, Any]) -> str:
    return str(attribute.get("fk_target_entity") or attribute.get("to_entity") or "").strip().lower()


def _fk_target_column(attribute: dict[str, Any]) -> str:
    return str(attribute.get("fk_target_column") or attribute.get("to_column") or "id").strip() or "id"


def _keys_entity_row_summary_html(
    *,
    silver: str,
    pk_display: str,
    pk_stats_label: str,
    pk_status: str,
    pk_actions: str,
    expandable: bool,
) -> str:
    icon = (
        '<span class="semantic-builder-expand-icon" aria-hidden="true"></span>'
        if expandable
        else '<span class="semantic-builder-expand-icon semantic-builder-expand-icon-spacer" aria-hidden="true"></span>'
    )
    return f"""
                <span class="semantic-builder-col semantic-builder-col-table">
                  {icon}
                  <code>{escape(silver)}</code>
                </span>
                <span class="semantic-builder-col semantic-builder-col-pk"><code>{escape(pk_display)}</code></span>
                <span class="semantic-builder-col semantic-builder-col-stats">{escape(pk_stats_label)}</span>
                <span class="semantic-builder-col semantic-builder-col-status">{_status_badge(pk_status)}</span>
                <span class="semantic-builder-col semantic-builder-col-actions semantic-builder-actions">{pk_actions}</span>
    """


def _keys_step_section(
    entities: list[dict[str, Any]],
    attributes: list[dict[str, Any]],
    *,
    is_admin: bool,
    builder_options: dict[str, Any] | None = None,
    keys_step_completed: bool = False,
) -> str:
    fk_by_entity: dict[str, list[dict[str, Any]]] = {}
    for attribute in attributes:
        if not isinstance(attribute, dict):
            continue
        if str(attribute.get("role") or "") != "foreign_key":
            continue
        if not _fk_target_entity(attribute):
            continue
        entity = str(attribute.get("entity") or "")
        fk_by_entity.setdefault(entity, []).append(attribute)

    rows = ""
    for entity in sorted(entities, key=lambda item: str(item.get("silver_entity") or "")):
        if not isinstance(entity, dict):
            continue
        ent_id = str(entity.get("id") or "")
        silver = str(entity.get("silver_entity") or "")
        pk_status = str(entity.get("primary_key_status") or "proposed")
        pk_display, pk_stats_label = _pk_key_display(entity)
        pk_actions = _item_review_actions(
            item_id=ent_id,
            status=pk_status,
            is_admin=is_admin,
            approve_attr="data-pk-approve",
            reject_attr="data-pk-reject",
            propose_attr="data-pk-propose",
        )
        fk_list = fk_by_entity.get(silver, [])
        fk_rows = ""
        for fk in fk_list:
            column = str(fk.get("column") or "")
            target = _fk_target_entity(fk)
            target_col = _fk_target_column(fk)
            status = str(fk.get("status") or "proposed")
            join_stats = fk.get("join_stats") if isinstance(fk.get("join_stats"), dict) else {}
            fk_stats_label = format_join_stats_summary(join_stats) or "—"
            attr_key = f"{silver}::{column}"
            fk_actions = _item_review_actions(
                item_id=attr_key,
                status=status,
                is_admin=is_admin,
                approve_attr="data-fk-approve",
                reject_attr="data-fk-reject",
                propose_attr="data-fk-propose",
            )
            fk_rows += f"""
            <tr>
              <td><code>{escape(column)}</code></td>
              <td><code>{escape(target)}.{escape(target_col)}</code></td>
              <td class="semantic-builder-stat-cell">{escape(fk_stats_label)}</td>
              <td>{_status_badge(status)}</td>
              <td class="semantic-builder-actions">{fk_actions}</td>
            </tr>
            """
        if fk_list:
            fk_count = len(fk_list)
            fk_label = f"{fk_count} foreign key{'s' if fk_count != 1 else ''}"
            summary_cells = _keys_entity_row_summary_html(
                silver=silver,
                pk_display=pk_display,
                pk_stats_label=pk_stats_label,
                pk_status=pk_status,
                pk_actions=pk_actions,
                expandable=True,
            )
            rows += f"""
        <tr class="semantic-builder-group-row">
          <td colspan="5" class="semantic-builder-group-cell">
            <details class="semantic-builder-group-details">
              <summary class="semantic-builder-group-summary semantic-builder-group-summary-keys">
                {summary_cells}
              </summary>
              <div class="semantic-builder-nested-panel">
                <div class="semantic-builder-nested-heading">{escape(fk_label)}</div>
                <table class="semantic-builder-table semantic-builder-nested-table semantic-builder-keys-nested-table">
                  <colgroup>
                    <col class="semantic-builder-keys-col-table">
                    <col class="semantic-builder-keys-col-pk">
                    <col class="semantic-builder-keys-col-stats">
                    <col class="semantic-builder-keys-col-status">
                    <col class="semantic-builder-keys-col-actions">
                  </colgroup>
                  <thead><tr><th>FK column</th><th>Target</th><th>Stats</th><th>Status</th><th></th></tr></thead>
                  <tbody>{fk_rows}</tbody>
                </table>
              </div>
            </details>
          </td>
        </tr>
            """
        else:
            summary_cells = _keys_entity_row_summary_html(
                silver=silver,
                pk_display=pk_display,
                pk_stats_label=pk_stats_label,
                pk_status=pk_status,
                pk_actions=pk_actions,
                expandable=False,
            )
            rows += f"""
        <tr class="semantic-builder-group-row semantic-builder-group-row-flat">
          <td colspan="5" class="semantic-builder-group-cell">
            <div class="semantic-builder-group-summary semantic-builder-group-summary-keys semantic-builder-group-summary-static">
              {summary_cells}
            </div>
          </td>
        </tr>
            """
    pk_proposed = sum(
        1
        for entity in entities
        if isinstance(entity, dict)
        and str(entity.get("primary_key_status") or "proposed") == "proposed"
        and str(entity.get("primary_key") or "").strip()
    )
    fk_proposed = sum(
        1
        for attribute in attributes
        if isinstance(attribute, dict)
        and str(attribute.get("role") or "") == "foreign_key"
        and str(attribute.get("status") or "proposed") == "proposed"
    )
    pk_approved = sum(
        1
        for entity in entities
        if isinstance(entity, dict) and str(entity.get("primary_key_status") or "") == "approved"
    )
    fk_approved = sum(
        1
        for attribute in attributes
        if isinstance(attribute, dict)
        and str(attribute.get("role") or "") == "foreign_key"
        and str(attribute.get("status") or "") == "approved"
    )
    bulk = ""
    if is_admin and (pk_proposed or fk_proposed):
        bulk = (
            '<button type="button" class="btn btn-secondary btn-sm" '
            'id="semantic-approve-all-keys">Approve all proposed keys</button>'
        )
    complete_btn = ""
    if is_admin:
        complete_label = (
            "Regenerate relationships from keys"
            if keys_step_completed
            else "Complete keys step → build relationships"
        )
        complete_btn = (
            f'<button type="button" class="btn btn-primary semantic-complete-step-btn" '
            f'data-complete-step="keys">{escape(complete_label)}</button>'
        )
    return f"""
    <section class="section">
      <div class="section-title">Step 1 — Primary &amp; foreign keys</div>
      <p class="pack-card-lead">
        Keys are inferred from silver profiling (column names, then value cardinality).
        {pk_proposed} PK proposed · {pk_approved} PK approved ·
        {fk_proposed} FK proposed · {fk_approved} FK approved.
        Pick approve or reject for each proposal, then submit your review together.
        Documentation conflicts are listed below. {bulk}
      </p>
      <div class="table-wrap semantic-builder-scroll">
        <table class="semantic-builder-table semantic-builder-compact-table semantic-builder-keys-table">
          <colgroup>
            <col class="semantic-builder-keys-col-table">
            <col class="semantic-builder-keys-col-pk">
            <col class="semantic-builder-keys-col-stats">
            <col class="semantic-builder-keys-col-status">
            <col class="semantic-builder-keys-col-actions">
          </colgroup>
          <thead>
            <tr><th>Table</th><th>Primary key</th><th>Stats</th><th>PK status</th><th></th></tr>
          </thead>
          <tbody>{rows}</tbody>
        </table>
      </div>
      {_keys_manual_builder(is_admin=is_admin, options=builder_options or {})}
      {_review_submit_bar(is_admin=is_admin)}
      <p style="margin-top:0.75rem">{complete_btn}</p>
    </section>
    """


def _step_complete_button(
    *,
    step: str,
    label: str,
    is_admin: bool,
    hidden: bool = False,
    completed_label: str | None = None,
    step_completed: bool = False,
) -> str:
    if not is_admin or hidden:
        return ""
    button_label = completed_label if step_completed and completed_label else label
    return (
        f'<button type="button" class="btn btn-primary semantic-complete-step-btn" '
        f'data-complete-step="{escape(step)}">{escape(button_label)}</button>'
    )


def _entity_select_options_html(options: dict[str, Any]) -> str:
    entities = options.get("entities") or []
    opts = ""
    for entity in entities:
        if not isinstance(entity, dict):
            continue
        silver = str(entity.get("silver_entity") or "").strip()
        if not silver:
            continue
        label = str(entity.get("label") or silver)
        opts += f'<option value="{escape(silver)}">{escape(label)}</option>'
    if not opts:
        return '<option value="">No tables available</option>'
    return opts


def _cardinality_select_options_html(options: dict[str, Any]) -> str:
    cards = options.get("cardinalities") or ["many_to_one"]
    return "".join(f'<option value="{escape(str(c))}">{escape(str(c).replace("_", " "))}</option>' for c in cards)


def _concept_select_options_html(options: dict[str, Any]) -> str:
    concepts = options.get("concepts") or []
    opts = ""
    for concept in concepts:
        if not isinstance(concept, dict):
            continue
        concept_id = str(concept.get("id") or "").strip()
        if not concept_id:
            continue
        label = str(concept.get("label") or concept_id)
        opts += f'<option value="{escape(concept_id)}">{escape(label)}</option>'
    if not opts:
        return '<option value="">No concepts loaded</option>'
    return opts


def _keys_manual_builder(*, is_admin: bool, options: dict[str, Any]) -> str:
    if not is_admin or not options.get("entities"):
        return ""
    entity_opts = _entity_select_options_html(options)
    return f"""
    <div class="semantic-builder-manual-panel">
      <div class="semantic-builder-manual-title">Build keys manually</div>
      <p class="pack-card-lead">Assign a primary key or foreign key from silver column options.</p>
      <div class="semantic-builder-manual-grid">
        <form id="semantic-build-pk-form" class="semantic-builder-manual-form">
          <div class="semantic-builder-manual-heading">Primary key</div>
          <label class="form-field">
            <span>Table</span>
            <select id="semantic-pk-entity" class="governance-role-select semantic-builder-select" required>{entity_opts}</select>
          </label>
          <label class="form-field">
            <span>PK column</span>
            <select id="semantic-pk-column" class="governance-role-select semantic-builder-select semantic-builder-column-select" data-entity-select="semantic-pk-entity" required>
              <option value="">Select table first</option>
            </select>
          </label>
          <button type="submit" class="btn btn-secondary btn-sm">Add primary key</button>
        </form>
        <form id="semantic-build-fk-form" class="semantic-builder-manual-form">
          <div class="semantic-builder-manual-heading">Foreign key</div>
          <label class="form-field">
            <span>From table</span>
            <select id="semantic-fk-entity" class="governance-role-select semantic-builder-select" required>{entity_opts}</select>
          </label>
          <label class="form-field">
            <span>FK column</span>
            <select id="semantic-fk-column" class="governance-role-select semantic-builder-select semantic-builder-column-select" data-entity-select="semantic-fk-entity" required>
              <option value="">Select table first</option>
            </select>
          </label>
          <label class="form-field">
            <span>To table</span>
            <select id="semantic-fk-to-entity" class="governance-role-select semantic-builder-select semantic-builder-target-entity-select" required>{entity_opts}</select>
          </label>
          <label class="form-field">
            <span>To column</span>
            <input id="semantic-fk-to-column" class="semantic-builder-target-column-input" type="text" value="id" required />
          </label>
          <button type="submit" class="btn btn-secondary btn-sm">Add foreign key</button>
        </form>
      </div>
    </div>
    """


def _relationship_manual_builder(*, is_admin: bool, options: dict[str, Any]) -> str:
    if not is_admin or not options.get("entities"):
        return ""
    entity_opts = _entity_select_options_html(options)
    card_opts = _cardinality_select_options_html(options)
    return f"""
    <div class="semantic-builder-manual-panel">
      <div class="semantic-builder-manual-title">Build relationship manually</div>
      <p class="pack-card-lead">Define a join between two silver tables using available columns.</p>
      <form id="semantic-build-rel-form" class="semantic-builder-manual-form semantic-builder-manual-form-wide">
        <label class="form-field">
          <span>From table</span>
          <select id="semantic-rel-from-entity" class="governance-role-select semantic-builder-select" required>{entity_opts}</select>
        </label>
        <label class="form-field">
          <span>From column</span>
          <select id="semantic-rel-from-column" class="governance-role-select semantic-builder-select semantic-builder-column-select" data-entity-select="semantic-rel-from-entity" required>
            <option value="">Select table first</option>
          </select>
        </label>
        <label class="form-field">
          <span>To table</span>
          <select id="semantic-rel-to-entity" class="governance-role-select semantic-builder-select semantic-builder-target-entity-select" required>{entity_opts}</select>
        </label>
        <label class="form-field">
          <span>To column</span>
          <input id="semantic-rel-to-column" class="semantic-builder-target-column-input" type="text" value="id" required />
        </label>
        <label class="form-field">
          <span>Cardinality</span>
          <select id="semantic-rel-cardinality" class="governance-role-select semantic-builder-select" required>{card_opts}</select>
        </label>
        <button type="submit" class="btn btn-primary">Add relationship</button>
      </form>
    </div>
    """


def _tags_manual_builder(*, is_admin: bool, options: dict[str, Any]) -> str:
    if not is_admin or not options.get("entities"):
        return ""
    entity_opts = _entity_select_options_html(options)
    concept_opts = _concept_select_options_html(options)
    return f"""
    <div class="semantic-builder-manual-panel">
      <div class="semantic-builder-manual-title">Assign column tag manually</div>
      <p class="pack-card-lead">Map a silver column to an operational concept from the catalog.</p>
      <form id="semantic-build-tag-form" class="semantic-builder-manual-form semantic-builder-manual-form-wide">
        <label class="form-field">
          <span>Table</span>
          <select id="semantic-tag-entity" class="governance-role-select semantic-builder-select" required>{entity_opts}</select>
        </label>
        <label class="form-field">
          <span>Column</span>
          <select id="semantic-tag-column" class="governance-role-select semantic-builder-select semantic-builder-column-select" data-entity-select="semantic-tag-entity" required>
            <option value="">Select table first</option>
          </select>
        </label>
        <label class="form-field">
          <span>Concept</span>
          <select id="semantic-tag-concept" class="governance-role-select semantic-builder-select" required>{concept_opts}</select>
        </label>
        <button type="submit" class="btn btn-secondary btn-sm">Assign tag</button>
      </form>
    </div>
    """


def _status_badge(status: str) -> str:
    key = status.strip().lower()
    css = _STATUS_CLASS.get(key, "semantics-status-proposed")
    return f'<span class="semantics-status-badge {css}">{escape(key)}</span>'


def _join_rate_pct(stats: dict[str, Any], key: str) -> int:
    if not stats:
        return 0
    return int(round(float(stats.get(key) or 0.0) * 100))


def _group_status_summary(items: list[dict[str, Any]], *, status_key: str = "status") -> str:
    counts: dict[str, int] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        key = str(item.get(status_key) or "proposed").strip().lower()
        counts[key] = counts.get(key, 0) + 1
    if not counts:
        return "—"
    parts: list[str] = []
    for status in ("proposed", "approved", "rejected"):
        count = counts.get(status, 0)
        if count:
            parts.append(f"{count} {status}")
    return ", ".join(parts) if parts else "—"


def _item_review_actions(
    *,
    item_id: str,
    status: str,
    is_admin: bool,
    approve_attr: str,
    reject_attr: str,
    propose_attr: str,
) -> str:
    """Approve / reject / undo buttons for draft items not yet published."""
    if not is_admin:
        return ""
    key = status.strip().lower()
    parts: list[str] = []
    if key != "approved":
        parts.append(
            f'<button type="button" class="btn btn-primary btn-sm semantic-builder-review-choice" '
            f'{approve_attr}="{escape(item_id)}" aria-pressed="false">Approve</button>'
        )
    if key != "rejected":
        parts.append(
            f'<button type="button" class="btn btn-secondary btn-sm semantic-builder-review-choice" '
            f'{reject_attr}="{escape(item_id)}" aria-pressed="false">Reject</button>'
        )
    if key != "proposed":
        parts.append(
            f'<button type="button" class="btn btn-secondary btn-sm semantic-builder-review-choice" '
            f'{propose_attr}="{escape(item_id)}" aria-pressed="false">Undo</button>'
        )
    return f'<span class="semantic-builder-review-item">{chr(10).join(parts)}</span>'


def _review_submit_bar(*, is_admin: bool) -> str:
    if not is_admin:
        return ""
    return """
      <div class="semantic-builder-decisions-submit">
        <button type="button" class="btn btn-primary" id="semantic-submit-reviews" disabled>Submit review</button>
      </div>
    """


def _profiling_status_banner(workflow: dict[str, Any]) -> str:
    status = str(workflow.get("profiling_status") or "idle").strip().lower()
    if status == "in_progress":
        return (
            '<div class="form-success semantic-profiling-banner">'
            "Profiling silver tables and inferring keys — this runs in the background. "
            "The page will refresh automatically when complete."
            "</div>"
        )
    if status == "error":
        error = str(workflow.get("profiling_error") or "Profiling failed")
        return f'<div class="form-error semantic-profiling-banner">{escape(error)}</div>'
    return ""


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
        actions = _item_review_actions(
            item_id=ent_id,
            status=status,
            is_admin=is_admin,
            approve_attr="data-entity-approve",
            reject_attr="data-entity-reject",
            propose_attr="data-entity-propose",
        )
        rows += f"""
        <tr>
          <td><code>{escape(silver)}</code></td>
          <td>{escape(role)}</td>
          <td>{_status_badge(status)}</td>
          <td>{escape(desc)}</td>
          <td class="semantic-builder-actions">{actions}</td>
        </tr>
        """
    return f"""
    <section class="section">
      <div class="section-title">Entities ({len([e for e in entities if isinstance(e, dict)])})</div>
      <div class="table-wrap semantic-builder-scroll">
        <table class="semantic-builder-table semantic-builder-compact-table">
          <thead>
            <tr><th>Silver table</th><th>Role</th><th>Status</th><th>Description</th><th></th></tr>
          </thead>
          <tbody>{rows}</tbody>
        </table>
      </div>
    </section>
    """


def _relationships_table(
    relationships: list[dict[str, Any]],
    *,
    is_admin: bool,
    complete_html: str = "",
    builder_options: dict[str, Any] | None = None,
    keys_step_completed: bool = False,
) -> str:
    rels_by_entity: dict[str, list[dict[str, Any]]] = {}
    for rel in relationships:
        if not isinstance(rel, dict):
            continue
        from_entity = str(rel.get("from_entity") or "")
        rels_by_entity.setdefault(from_entity, []).append(rel)

    match_100_actionable = 0
    orphan_100_actionable = 0
    rows = ""
    for from_entity in sorted(
        rels_by_entity,
        key=lambda entity: (-len(rels_by_entity[entity]), entity),
    ):
        entity_rels = rels_by_entity[from_entity]
        rel_rows = ""
        for rel in entity_rels:
            rel_id = str(rel.get("id") or "")
            label = (
                f"{rel.get('from_entity')}.{rel.get('from_column')} → "
                f"{rel.get('to_entity')}.{rel.get('to_column')}"
            )
            status = str(rel.get("status") or "proposed")
            citation = str(rel.get("citation") or rel.get("description") or "")
            join_stats = rel.get("join_stats") if isinstance(rel.get("join_stats"), dict) else {}
            join_stats_label = format_join_stats_summary(join_stats)
            match_pct = _join_rate_pct(join_stats, "match_rate")
            orphan_pct = _join_rate_pct(join_stats, "orphan_rate")
            if status != "approved" and match_pct == 100:
                match_100_actionable += 1
            if status != "rejected" and orphan_pct == 100:
                orphan_100_actionable += 1
            actions = _item_review_actions(
                item_id=rel_id,
                status=status,
                is_admin=is_admin,
                approve_attr="data-rel-approve",
                reject_attr="data-rel-reject",
                propose_attr="data-rel-propose",
            )
            rel_rows += f"""
            <tr data-rel-match-pct="{match_pct}" data-rel-orphan-pct="{orphan_pct}">
              <td><code>{escape(label)}</code></td>
              <td>{escape(str(rel.get("cardinality") or ""))}</td>
              <td>{escape(join_stats_label or "—")}</td>
              <td>{_status_badge(status)}</td>
              <td class="semantic-builder-citation">{escape(citation)}</td>
              <td class="semantic-builder-actions">{actions}</td>
            </tr>
            """
        rel_count = len(entity_rels)
        rel_label = f"{rel_count} join{'s' if rel_count != 1 else ''}"
        status_summary = _group_status_summary(entity_rels)
        rows += f"""
        <tr class="semantic-builder-group-row">
          <td colspan="6" class="semantic-builder-group-cell">
            <details class="semantic-builder-group-details">
              <summary class="semantic-builder-group-summary semantic-builder-group-summary-relationships">
                <span class="semantic-builder-col semantic-builder-col-table">
                  <span class="semantic-builder-expand-icon" aria-hidden="true"></span>
                  <code>{escape(from_entity)}</code>
                </span>
                <span class="semantic-builder-col">{escape(rel_label)}</span>
                <span class="semantic-builder-col semantic-builder-group-status">{escape(status_summary)}</span>
                <span class="semantic-builder-col">—</span>
                <span class="semantic-builder-col">—</span>
                <span class="semantic-builder-col semantic-builder-col-actions"></span>
              </summary>
              <div class="semantic-builder-nested-panel">
                <div class="semantic-builder-nested-heading">{escape(rel_label)}</div>
                <table class="semantic-builder-table semantic-builder-nested-table semantic-builder-relationships-nested-table">
                  <colgroup>
                    <col class="semantic-builder-rel-col-join">
                    <col class="semantic-builder-rel-col-cardinality">
                    <col class="semantic-builder-rel-col-stats">
                    <col class="semantic-builder-rel-col-status">
                    <col class="semantic-builder-rel-col-source">
                    <col class="semantic-builder-rel-col-actions">
                  </colgroup>
                  <thead><tr><th>Join</th><th>Cardinality</th><th>Join stats</th><th>Status</th><th>Source</th><th></th></tr></thead>
                  <tbody>{rel_rows}</tbody>
                </table>
              </div>
            </details>
          </td>
        </tr>
        """
    if not rows:
        if keys_step_completed:
            empty_msg = (
                "No joins were generated from your keys yet. "
                "Approve foreign keys on step 1, or generate joins from the keys you configured."
            )
            regen_btn = ""
            if is_admin:
                regen_btn = (
                    '<p style="margin-top:0.65rem">'
                    '<button type="button" class="btn btn-secondary btn-sm" '
                    'id="semantic-generate-relationships-btn">Generate joins from keys</button>'
                    "</p>"
                )
            rows = f'<tr><td colspan="6">{escape(empty_msg)}</td></tr>'
        else:
            rows = (
                '<tr><td colspan="6">Complete step 1 to generate relationship proposals from your keys.</td></tr>'
            )
            regen_btn = ""
    else:
        regen_btn = ""
    bulk_parts: list[str] = []
    if is_admin and match_100_actionable:
        bulk_parts.append(
            '<button type="button" class="btn btn-secondary btn-sm" '
            'id="semantic-approve-all-100-matches">Approve all 100% matches</button>'
        )
    if is_admin and orphan_100_actionable:
        bulk_parts.append(
            '<button type="button" class="btn btn-secondary btn-sm" '
            'id="semantic-reject-all-100-orphans">Reject all 100% orphans</button>'
        )
    bulk = " ".join(bulk_parts)
    bulk_lead = f" {bulk}" if bulk else ""
    return f"""
    <section class="section">
      <div class="section-title">Step 2 — Relationships</div>
      <p class="pack-card-lead">Review proposed joins between silver tables. Pick approve or reject for each join, then submit your review together.{bulk_lead}</p>
      {complete_html}
      <div class="table-wrap semantic-builder-scroll">
        <table class="semantic-builder-table semantic-builder-compact-table semantic-builder-relationships-table">
          <colgroup>
            <col class="semantic-builder-rel-col-table">
            <col class="semantic-builder-rel-col-joins">
            <col class="semantic-builder-rel-col-status">
            <col class="semantic-builder-rel-col-stats">
            <col class="semantic-builder-rel-col-source">
            <col class="semantic-builder-rel-col-actions">
          </colgroup>
          <thead>
            <tr><th>Table</th><th>Joins</th><th>Status</th><th>Join stats</th><th>Source</th><th></th></tr>
          </thead>
          <tbody>{rows}</tbody>
        </table>
      </div>
      {regen_btn}
      {_relationship_manual_builder(is_admin=is_admin, options=builder_options or {})}
      {_review_submit_bar(is_admin=is_admin)}
    </section>
    """


def _graph_section_lazy(*, api_root: str) -> str:
    """Defer SVG layout to the browser so builder-ui stays under API Gateway limits."""
    return f"""
    <section class="section semantic-graph-section" id="semantic-graph-section" data-api-root="{escape(api_root)}">
      <div class="section-title">Model graph</div>
      <p class="pack-card-lead semantic-graph-lead">Loading graph…</p>
      <div class="semantic-graph-controls">
        <label class="semantic-graph-label" for="semantic-graph-fact-select">Inspect fact</label>
        <select id="semantic-graph-fact-select" class="governance-role-select semantic-graph-select" data-api-root="{escape(api_root)}">
          <option value="">All facts (overview)</option>
        </select>
      </div>
      <div class="semantic-graph-wrap" id="semantic-graph-view">
        <p class="semantic-builder-loading">Loading model graph…</p>
      </div>
    </section>
    """


def _attributes_section(
    attributes: list[dict[str, Any]],
    *,
    is_admin: bool,
    complete_html: str = "",
    builder_options: dict[str, Any] | None = None,
    on_tags_page: bool = False,
) -> str:
    """Semantic tag proposals (step 3) — excludes pure FK key rows."""
    status_order = {"proposed": 0, "approved": 1, "rejected": 2}
    visible = [
        item
        for item in attributes
        if isinstance(item, dict)
        and str(item.get("role") or "") != "foreign_key"
        and (
            item.get("concepts")
            or str(item.get("status") or "proposed").strip().lower() in {"approved", "rejected"}
        )
    ]
    if not visible:
        if on_tags_page:
            return f"""
            <section class="section">
              <div class="section-title">Step 3 — Semantic tags</div>
              <p class="pack-card-lead">Complete step 2 to run AI concept tagging, or assign tags manually below.</p>
              {complete_html}
              {_tags_manual_builder(is_admin=is_admin, options=builder_options or {})}
            </section>
            """
        return ""
    visible.sort(
        key=lambda item: (
            status_order.get(str(item.get("status") or "proposed").strip().lower(), 9),
            str(item.get("entity") or ""),
            str(item.get("column") or ""),
        )
    )
    proposed_count = sum(
        1 for item in visible if str(item.get("status") or "") == "proposed"
    )
    approved_count = sum(
        1 for item in visible if str(item.get("status") or "") == "approved"
    )
    rejected_count = sum(
        1 for item in visible if str(item.get("status") or "") == "rejected"
    )
    rows = ""
    tags_by_entity: dict[str, list[dict[str, Any]]] = {}
    for item in visible:
        entity = str(item.get("entity") or "")
        tags_by_entity.setdefault(entity, []).append(item)

    for entity in sorted(tags_by_entity):
        entity_items = tags_by_entity[entity]
        tag_rows = ""
        for item in entity_items:
            column = str(item.get("column") or "")
            status = str(item.get("status") or "proposed")
            concept_list = item.get("concepts") or []
            concepts = ", ".join(str(c) for c in concept_list) if concept_list else "—"
            attr_key = f"{entity}::{column}"
            actions = _item_review_actions(
                item_id=attr_key,
                status=status,
                is_admin=is_admin,
                approve_attr="data-attr-approve",
                reject_attr="data-attr-reject",
                propose_attr="data-attr-propose",
            )
            tag_rows += f"""
            <tr>
              <td><code>{escape(column)}</code></td>
              <td>{escape(concepts)}</td>
              <td>{_status_badge(status)}</td>
              <td class="semantic-builder-actions">{actions}</td>
            </tr>
            """
        tag_count = len(entity_items)
        tag_label = f"{tag_count} column{'s' if tag_count != 1 else ''}"
        status_summary = _group_status_summary(entity_items)
        rows += f"""
        <tr class="semantic-builder-group-row">
          <td colspan="4" class="semantic-builder-group-cell">
            <details class="semantic-builder-group-details">
              <summary class="semantic-builder-group-summary semantic-builder-group-summary-tags">
                <span class="semantic-builder-col semantic-builder-col-table">
                  <span class="semantic-builder-expand-icon" aria-hidden="true"></span>
                  <code>{escape(entity)}</code>
                </span>
                <span class="semantic-builder-col">{escape(tag_label)}</span>
                <span class="semantic-builder-col semantic-builder-group-status">{escape(status_summary)}</span>
                <span class="semantic-builder-col"></span>
              </summary>
              <div class="semantic-builder-nested-panel">
                <div class="semantic-builder-nested-heading">{escape(tag_label)}</div>
                <table class="semantic-builder-table semantic-builder-nested-table">
                  <thead><tr><th>Column</th><th>Concepts</th><th>Status</th><th></th></tr></thead>
                  <tbody>{tag_rows}</tbody>
                </table>
              </div>
            </details>
          </td>
        </tr>
        """
    bulk = ""
    if is_admin and proposed_count:
        bulk = (
            '<button type="button" class="btn btn-secondary btn-sm" '
            'id="semantic-approve-all-tags">Approve all proposed tags</button>'
        )
    return f"""
    <section class="section">
      <div class="section-title">Step 3 — Semantic tags ({len(visible)})</div>
      <p class="pack-card-lead">
        {proposed_count} proposed · {approved_count} approved · {rejected_count} rejected
        (draft only — publish locks production). Pick approve or reject for each tag, then submit your review together. {bulk}
      </p>
      {complete_html}
      <div class="table-wrap semantic-builder-scroll">
        <table class="semantic-builder-table semantic-builder-compact-table">
          <thead><tr><th>Table</th><th>Columns</th><th>Status</th><th></th></tr></thead>
          <tbody>{rows}</tbody>
        </table>
      </div>
      {_tags_manual_builder(is_admin=is_admin, options=builder_options or {})}
      {_review_submit_bar(is_admin=is_admin)}
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


def _question_action_buttons(
    question: dict[str, Any],
    *,
    is_admin: bool,
    profiling_in_progress: bool = False,
) -> str:
    status = str(question.get("status") or "open")
    if not is_admin or status not in ("open", "deferred"):
        return ""
    if profiling_in_progress:
        return '<span class="semantic-builder-question-actions muted">Wait for profiling to finish</span>'
    qid = _attr_escape(str(question.get("id") or ""))
    action = question.get("action") if isinstance(question.get("action"), dict) else {}
    choices = action.get("choices") or []
    if choices:
        buttons = ""
        for choice in choices:
            if not isinstance(choice, dict):
                continue
            choice_id = _attr_escape(str(choice.get("id") or choice.get("value") or ""))
            label = escape(str(choice.get("label") or choice_id))
            buttons += (
                f'<button type="button" class="btn btn-secondary btn-sm semantic-builder-question-choice" '
                f'data-question-id="{qid}" data-question-choice="{choice_id}" '
                f'aria-pressed="false">{label}</button> '
            )
        buttons += (
            f'<button type="button" class="btn btn-secondary btn-sm semantic-builder-question-choice '
            f'semantic-builder-question-document-later" '
            f'data-question-id="{qid}" data-question-choice="document_later" '
            f'aria-pressed="false">Document later</button> '
        )
        return f'<span class="semantic-builder-question-actions">{buttons}</span>'
    return (
        f'<button type="button" class="btn btn-secondary btn-sm semantic-builder-question-ack" '
        f'data-question-id="{qid}" aria-pressed="false">Acknowledge</button>'
    )


def _question_type_badge(question: dict[str, Any]) -> str:
    action = question.get("action") if isinstance(question.get("action"), dict) else {}
    action_type = str(action.get("type") or "").strip().lower()
    if not action_type:
        return ""
    label = _QUESTION_ACTION_LABELS.get(action_type, action_type.replace("_", " "))
    return f'<span class="semantic-builder-question-type">{escape(label)}</span>'


def _questions_section(
    questions: list[dict[str, Any]],
    *,
    is_admin: bool,
    profiling_in_progress: bool = False,
    standalone: bool = False,
) -> str:
    pending_questions = _pending_decision_questions(questions)
    if not pending_questions:
        if standalone:
            return """
    <section class="section">
      <div class="section-title">Open decisions</div>
      <p class="pack-card-lead">No open decisions right now. Blocking questions from connector hints appear here after profiling.</p>
    </section>
            """
        return ""
    items = ""
    for question in pending_questions:
        qid = str(question.get("id") or "")
        text = str(question.get("text") or "")
        status = str(question.get("status") or "open")
        blocking = " · blocks publish" if question.get("blocks_publish") else ""
        deferred_note = (
            '<p class="semantic-builder-question-deferred-note">Previously marked document later</p>'
            if status == "deferred"
            else ""
        )
        action_buttons = _question_action_buttons(
            question,
            is_admin=is_admin,
            profiling_in_progress=profiling_in_progress,
        )
        items += f"""
        <li class="semantic-builder-question" data-question-id="{escape(qid)}">
          <div class="semantic-builder-question-head">
            {_question_type_badge(question)}
            {_status_badge(status)}{blocking}
            <span class="semantic-builder-question-text">{escape(text)}</span>
          </div>
          {deferred_note}
          <div class="semantic-builder-question-foot">{action_buttons}</div>
        </li>
        """
    submit_bar = ""
    if is_admin and not profiling_in_progress:
        submit_bar = """
      <div class="semantic-builder-decisions-submit">
        <button type="button" class="btn btn-primary" id="semantic-submit-decisions" disabled>Submit decisions</button>
      </div>
        """
    lead = (
        "Review connector and profiling questions. Pick an option for each item, then submit all decisions together."
        if standalone
        else "Pick an option for each item, then submit all decisions together."
    )
    return f"""
    <section class="section">
      <div class="section-title">Open decisions</div>
      <p class="pack-card-lead">{lead}</p>
      <ul class="semantic-builder-questions">{items}</ul>
      {submit_bar}
    </section>
    """


def _admin_actions(
    *,
    is_admin: bool,
    init_completed: bool,
    differs: bool,
    readiness: dict[str, Any],
    page_step: str | None,
) -> str:
    if not is_admin:
        return ""
    publish_disabled = "" if readiness.get("ready") else " disabled"
    publish_hint = "" if readiness.get("ready") else ' title="Resolve readiness issues before publishing"'
    show_structure = init_completed and page_step in {"relationships", "tags"}
    return f"""
    <div class="semantic-builder-actions-bar">
      <button type="button" class="btn btn-secondary" id="semantic-reinit-btn"{" hidden" if not init_completed else ""}>Re-run profiling</button>
      <button type="button" class="btn btn-secondary" id="semantic-approve-all-structure"{" hidden" if not show_structure else ""}>Approve all entities &amp; joins</button>
      <button type="button" class="btn btn-primary" id="semantic-publish-btn"{publish_disabled}{publish_hint}>Publish semantic model</button>
      <button type="button" class="btn btn-secondary" id="semantic-discard-btn"{" disabled" if not differs else ""}>Discard draft changes</button>
    </div>
    """


def _builder_styles() -> str:
    return """
<style>
.semantic-builder-page { display: flex; flex-direction: column; gap: 1.25rem; }
.semantic-builder-step-nav {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.65rem;
}
.semantic-builder-step-nav-item {
  display: flex;
  gap: 0.75rem;
  align-items: flex-start;
  padding: 0.75rem 0.9rem;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: rgba(8, 18, 40, 0.35);
  text-decoration: none;
  color: inherit;
  transition: border-color 0.15s ease, background 0.15s ease;
}
.semantic-builder-step-nav-item:hover {
  border-color: rgba(56, 189, 248, 0.45);
  background: rgba(56, 189, 248, 0.06);
}
.semantic-builder-step-nav-current {
  border-color: #38bdf8;
  background: rgba(56, 189, 248, 0.08);
}
.semantic-builder-step-nav-done { border-color: rgba(52, 211, 153, 0.45); }
.semantic-builder-step-nav-pending { opacity: 0.82; }
.semantic-builder-step-nav-locked { opacity: 0.72; }
.semantic-builder-step-nav-current .semantic-builder-step-num { background: rgba(56, 189, 248, 0.25); color: #7dd3fc; }
.semantic-builder-step-nav-done .semantic-builder-step-num { background: rgba(52, 211, 153, 0.2); color: #6ee7b7; }
.semantic-builder-step-num {
  width: 1.75rem;
  height: 1.75rem;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  background: rgba(148, 163, 184, 0.2);
  flex-shrink: 0;
}
.semantic-builder-step-body { display: flex; flex-direction: column; gap: 0.15rem; }
.semantic-builder-step-sub { font-size: 0.82rem; color: var(--text-muted); }
.semantic-builder-step-state { font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.04em; }
.semantic-builder-step-metrics {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
  margin-top: 0.25rem;
  font-size: 0.82rem;
  color: var(--text-muted);
}
.semantic-builder-landing-action {
  margin: 1.25rem 0 0.75rem;
}
.semantic-builder-start-btn {
  background: #059669;
  border: 1px solid #10b981;
  color: #ecfdf5;
  font-size: 1.05rem;
  padding: 0.75rem 1.5rem;
  border-radius: var(--radius);
  font-weight: 600;
  text-decoration: none;
  display: inline-block;
}
.semantic-builder-start-btn:hover {
  background: #10b981;
  border-color: #34d399;
  color: #fff;
}
.semantic-builder-landing-hint { margin-top: 1rem; }
.semantic-builder-gate {
  margin-top: 0.5rem;
  padding: 1rem 1.1rem;
  border: 1px solid rgba(251, 191, 36, 0.35);
  border-radius: var(--radius);
  background: rgba(251, 191, 36, 0.08);
}
.semantic-builder-revisit {
  margin-top: 0.5rem;
  padding: 0.85rem 1rem;
  border: 1px solid rgba(56, 189, 248, 0.35);
  border-radius: var(--radius);
  background: rgba(56, 189, 248, 0.08);
}
.semantic-builder-step-nav-revisitable { cursor: pointer; }
.semantic-builder-sub-nav {
  display: flex;
  gap: 0.65rem;
  margin-top: -0.35rem;
}
.semantic-builder-sub-nav-item {
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
  padding: 0.45rem 0.75rem;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: rgba(8, 18, 40, 0.35);
  text-decoration: none;
  color: inherit;
  font-size: 0.88rem;
}
.semantic-builder-sub-nav-item:hover {
  border-color: rgba(56, 189, 248, 0.45);
  background: rgba(56, 189, 248, 0.06);
}
.semantic-builder-sub-nav-current {
  border-color: #38bdf8;
  background: rgba(56, 189, 248, 0.08);
}
.semantic-builder-sub-nav-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 1.25rem;
  height: 1.25rem;
  padding: 0 0.35rem;
  border-radius: 999px;
  background: rgba(251, 191, 36, 0.2);
  color: #fcd34d;
  font-size: 0.72rem;
  font-weight: 700;
}
@media (max-width: 900px) {
  .semantic-builder-step-nav { grid-template-columns: 1fr; }
}
.semantic-builder-scroll thead th { position: static; }
.semantic-builder-compact-table thead th,
.semantic-builder-compact-table tbody td {
  padding: 0.35rem 0.6rem;
}
.semantic-builder-group-cell {
  padding: 0 !important;
  border-bottom: none !important;
}
.semantic-builder-group-details {
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
}
.semantic-builder-group-summary {
  display: grid;
  gap: 0.5rem;
  align-items: center;
  padding: 0.35rem 0.6rem;
  cursor: pointer;
  list-style: none;
}
.semantic-builder-group-summary::-webkit-details-marker { display: none; }
.semantic-builder-group-summary::marker { content: ""; }
.semantic-builder-group-summary-4 {
  grid-template-columns: minmax(8rem, 1.4fr) minmax(5rem, 1fr) minmax(5rem, 0.8fr) auto;
}
.semantic-builder-keys-table,
.semantic-builder-keys-nested-table {
  table-layout: fixed;
  width: 100%;
}
.semantic-builder-keys-col-table { width: 32%; }
.semantic-builder-keys-col-pk { width: 12%; }
.semantic-builder-keys-col-stats { width: 22%; }
.semantic-builder-keys-col-status { width: 14%; }
.semantic-builder-keys-col-actions { width: auto; }
.semantic-builder-relationships-table,
.semantic-builder-relationships-nested-table {
  table-layout: fixed;
  width: 100%;
}
.semantic-builder-rel-col-table { width: 26%; }
.semantic-builder-rel-col-joins { width: 12%; }
.semantic-builder-rel-col-status { width: 14%; }
.semantic-builder-rel-col-stats { width: 18%; }
.semantic-builder-rel-col-source { width: 18%; }
.semantic-builder-rel-col-actions { width: auto; }
.semantic-builder-rel-col-join { width: 30%; }
.semantic-builder-rel-col-cardinality { width: 12%; }
.semantic-builder-group-summary-keys {
  grid-template-columns: 32% 12% 22% 14% auto;
  gap: 0;
}
.semantic-builder-group-summary-relationships {
  grid-template-columns: 26% 12% 14% 18% 18% auto;
  gap: 0;
}
.semantic-builder-group-summary-static {
  cursor: default;
}
.semantic-builder-expand-icon-spacer::before {
  visibility: hidden;
}
.semantic-builder-col-pk,
.semantic-builder-col-stats,
.semantic-builder-col-status {
  min-width: 0;
}
.semantic-builder-col-actions {
  justify-self: end;
}
.semantic-builder-group-summary-5 {
  grid-template-columns: minmax(8rem, 1.2fr) minmax(4rem, 0.7fr) minmax(5rem, 0.9fr) minmax(5rem, 1fr) auto;
}
.semantic-builder-group-summary-tags {
  grid-template-columns: minmax(8rem, 1.4fr) minmax(4rem, 0.7fr) minmax(5rem, 1fr) auto;
}
.semantic-builder-expand-icon::before {
  content: "▸";
  display: inline-block;
  width: 0.85rem;
  flex-shrink: 0;
  color: var(--text-muted);
  transition: transform 0.15s ease;
}
.semantic-builder-group-details[open] .semantic-builder-expand-icon::before {
  transform: rotate(90deg);
}
.semantic-builder-col-table {
  display: inline-flex;
  align-items: center;
  gap: 0.15rem;
  min-width: 0;
}
.semantic-builder-col-stats,
.semantic-builder-stat-cell {
  font-size: 0.76rem;
  color: var(--text-muted);
}
.semantic-builder-group-status {
  font-size: 0.76rem;
  color: var(--text-muted);
}
.semantic-builder-nested-panel {
  padding: 0 0.6rem 0.35rem 1.45rem;
}
.semantic-builder-nested-heading {
  font-size: 0.7rem;
  color: var(--text-dim);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: 0.2rem;
}
.semantic-builder-nested-table { margin-top: 0; }
.semantic-builder-compact-table .semantic-builder-nested-table thead th,
.semantic-builder-compact-table .semantic-builder-nested-table tbody td {
  padding: 0.2rem 0.45rem;
  font-size: 0.76rem;
}
.semantic-builder-compact-table .semantics-status-badge {
  font-size: 0.65rem;
  padding: 0.05rem 0.35rem;
}
.semantic-builder-compact-table code { font-size: 0.76rem; }
.semantic-builder-compact-table .btn-sm {
  padding: 0.12rem 0.4rem;
  font-size: 0.7rem;
  line-height: 1.25;
}
.semantic-builder-compact-table .semantic-builder-actions .btn { margin-right: 0.2rem; }
.semantic-builder-group-row-flat .semantic-builder-group-cell {
  padding: 0 !important;
}
.semantic-builder-group-row-flat td { padding: 0.35rem 0.6rem; }
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
.semantic-builder-question-text {
  flex: 1 1 12rem;
}
.semantic-builder-question-foot {
  margin-top: 0.5rem;
}
.semantic-builder-question-deferred-note {
  margin: 0.35rem 0 0;
  font-size: 0.78rem;
  color: var(--text-muted);
}
.semantic-builder-question-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
}
.semantic-builder-question-choice-selected,
.semantic-builder-question-ack-selected,
.semantic-builder-review-choice-selected {
  border-color: #38bdf8;
  background: rgba(56, 189, 248, 0.15);
  color: #7dd3fc;
}
.semantic-builder-review-item {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 0.35rem;
}
.semantic-builder-question-document-later.semantic-builder-question-choice-selected {
  border-color: rgba(251, 191, 36, 0.55);
  background: rgba(251, 191, 36, 0.12);
  color: #fcd34d;
}
.semantic-builder-decisions-submit {
  margin-top: 0.85rem;
  display: flex;
  justify-content: flex-end;
}
.semantic-builder-question-type {
  font-size: 0.72rem;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--text-muted);
  background: var(--surface-2, #f1f5f9);
  border-radius: 4px;
  padding: 0.1rem 0.45rem;
}
.semantic-builder-resolution {
  margin: 0.5rem 0 0;
  font-size: 0.84rem;
  color: var(--text-muted);
}
.semantic-builder-errors ul { margin: 0.25rem 0 0; padding-left: 1.1rem; }
.semantic-builder-manual-panel {
  margin-top: 1rem;
  padding: 1rem 1.1rem;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: rgba(255, 255, 255, 0.02);
}
.semantic-builder-manual-title {
  font-weight: 600;
  margin-bottom: 0.25rem;
  color: var(--text);
}
.semantic-builder-manual-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(16rem, 1fr));
  gap: 1rem;
  margin-top: 0.75rem;
}
.semantic-builder-manual-form {
  display: flex;
  flex-direction: column;
  gap: 0.65rem;
}
.semantic-builder-manual-form-wide {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(11rem, 1fr));
  gap: 0.65rem;
  align-items: end;
}
.semantic-builder-manual-form .form-field {
  margin-bottom: 0;
}
.semantic-builder-manual-heading {
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--text);
}
.semantic-builder-manual-form .semantic-builder-select {
  width: 100%;
  min-width: 0;
  background: rgba(8, 18, 40, 0.95);
  color: var(--text);
  color-scheme: dark;
}
.semantic-builder-manual-form .semantic-builder-select option {
  background: #0a1628;
  color: var(--text);
}
.semantic-builder-target-column-input {
  width: 100%;
  padding: 0.6rem 0.75rem;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.04);
  color: var(--text);
  font: inherit;
}
.semantic-builder-target-column-input:focus {
  outline: none;
  border-color: rgba(56, 189, 248, 0.45);
  box-shadow: 0 0 0 3px rgba(56, 189, 248, 0.12);
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
.semantic-builder-status {
  padding: 0.65rem 0.85rem;
  border-radius: var(--radius);
  border: 1px solid var(--border);
  background: rgba(56, 189, 248, 0.08);
  color: #bae6fd;
  font-size: 0.88rem;
}
.semantic-builder-status.is-error {
  background: rgba(248, 113, 113, 0.1);
  border-color: rgba(248, 113, 113, 0.35);
  color: #fecaca;
}
.semantic-builder-status.is-success {
  background: rgba(52, 211, 153, 0.1);
  border-color: rgba(52, 211, 153, 0.35);
  color: #a7f3d0;
}
.semantic-builder-content-loading {
  min-height: 8rem;
  display: flex;
  align-items: center;
  justify-content: center;
}
.semantic-builder-loading {
  color: var(--text-muted);
  font-size: 0.92rem;
  margin: 0;
}
button.is-working { opacity: 0.72; cursor: wait; }
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


def _builder_script(
    api_root: str,
    *,
    profiling_in_progress: bool = False,
    defer_content_load: bool = False,
    page_step: str | None = None,
    script_root: str = "",
) -> str:
    page_step_json = json.dumps(page_step)
    keys_path = json.dumps(f"{script_root}/portal/semantics/builder/keys")
    rel_path = json.dumps(f"{script_root}/portal/semantics/builder/relationships")
    tags_path = json.dumps(f"{script_root}/portal/semantics/builder/tags")
    return f"""
<script>
(function() {{
  var apiRoot = {json.dumps(api_root)};
  var deferContentLoad = {json.dumps(defer_content_load)};
  var pageStep = {page_step_json};
  var keysPagePath = {keys_path};
  var relationshipsPagePath = {rel_path};
  var tagsPagePath = {tags_path};
  var stepNextPage = {{ keys: relationshipsPagePath, relationships: tagsPagePath }};

  function setBuilderStatus(message, kind) {{
    var node = document.getElementById("semantic-builder-status");
    if (!node) return;
    if (!message) {{
      node.hidden = true;
      node.textContent = "";
      node.className = "semantic-builder-status";
      return;
    }}
    node.hidden = false;
    node.textContent = message;
    node.className = "semantic-builder-status" + (kind ? " is-" + kind : "");
  }}

  function beginButtonAction(btn, label) {{
    if (!btn) return function() {{}};
    var original = btn.textContent;
    btn.disabled = true;
    btn.classList.add("is-working");
    btn.setAttribute("aria-busy", "true");
    if (label) btn.textContent = label;
    setBuilderStatus(label || "Working…");
    return function end(successMessage) {{
      btn.disabled = false;
      btn.classList.remove("is-working");
      btn.removeAttribute("aria-busy");
      btn.textContent = original;
      if (successMessage) {{
        setBuilderStatus(successMessage, "success");
        window.setTimeout(function() {{ setBuilderStatus(""); }}, 2400);
      }}
    }};
  }}

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

  function storeBuilderOptions(options) {{
    if (!options || typeof options !== "object") return;
    window.semanticBuilderOptions = options;
    var page = document.querySelector(".semantic-builder-page");
    var optionsNode = document.getElementById("semantic-builder-options");
    if (!optionsNode && page) {{
      optionsNode = document.createElement("script");
      optionsNode.type = "application/json";
      optionsNode.id = "semantic-builder-options";
      page.appendChild(optionsNode);
    }}
    if (optionsNode) optionsNode.textContent = JSON.stringify(options);
  }}

  function loadSemanticGraph() {{
    var section = document.getElementById("semantic-graph-section");
    if (!section) return Promise.resolve();
    var graphApi = section.getAttribute("data-api-root") || apiRoot;
    var view = document.getElementById("semantic-graph-view");
    var lead = section.querySelector(".semantic-graph-lead");
    if (!graphApi || !view) return Promise.resolve();
    return fetch(graphApi + "/graph", {{
      credentials: "same-origin",
      headers: {{ "Accept": "application/json" }}
    }}).then(function(r) {{
      return r.json().then(function(data) {{
        if (!r.ok) throw new Error(data.error || "Failed to load graph");
        return data;
      }});
    }}).then(function(data) {{
      if (typeof data.svg === "string") view.innerHTML = data.svg;
      var graph = data.graph || {{}};
      var nodeCount = (graph.nodes || []).length;
      var edgeCount = (graph.edges || []).length;
      if (lead) {{
        lead.textContent = nodeCount
          ? (nodeCount + " entities · " + edgeCount + " relationships (approved joins shown in green). Drag to pan.")
          : "No graph nodes yet.";
      }}
      var select = document.getElementById("semantic-graph-fact-select");
      if (select && Array.isArray(data.facts)) {{
        var current = select.value;
        select.innerHTML = '<option value="">All facts (overview)</option>';
        data.facts.forEach(function(fact) {{
          if (!fact || !fact.id) return;
          var opt = document.createElement("option");
          opt.value = fact.id;
          opt.textContent = fact.label || fact.id;
          select.appendChild(opt);
        }});
        if (current) select.value = current;
        if (window.bindSemanticGraphFactSelect) window.bindSemanticGraphFactSelect();
      }}
    }}).catch(function(err) {{
      view.innerHTML = '<p class="form-error">' + err.message + '</p>';
      if (lead) lead.textContent = "Graph could not be loaded.";
    }});
  }}

  function refreshBuilderContent(options) {{
    var opts = options || {{}};
    var scrollY = window.scrollY;
    var assistantLog = document.getElementById("semantic-assistant-log");
    var assistantHtml = assistantLog ? assistantLog.innerHTML : "";
    var el = document.getElementById("semantic-builder-content");
    if (el && opts.showLoading) {{
      el.setAttribute("aria-busy", "true");
      el.innerHTML = '<div class="semantic-builder-content-loading"><p class="semantic-builder-loading">Loading semantic builder…</p></div>';
    }} else if (el && opts.showLoading === false) {{
      el.setAttribute("aria-busy", "true");
    }}
    if (!opts.quiet) setBuilderStatus("Refreshing builder…");
    var uiUrl = apiRoot + "/builder-ui";
    if (pageStep) uiUrl += "?page=" + encodeURIComponent(pageStep);
    return fetch(uiUrl, {{
      credentials: "same-origin",
      headers: {{ "Accept": "application/json" }}
    }}).then(function(r) {{
      return r.json().then(function(data) {{
        if (!r.ok) {{
          throw new Error(data.error || data.message || "Failed to refresh builder");
        }}
        return data;
      }}, function() {{
        throw new Error("Failed to refresh builder (" + r.status + ")");
      }});
    }}).then(function(data) {{
      if (!el || typeof data.html !== "string") {{
        throw new Error("Builder refresh returned no content");
      }}
      el.innerHTML = data.html;
      el.removeAttribute("aria-busy");
      storeBuilderOptions(data.builder_options);
      syncBuilderDropdowns();
      updateDecisionsSubmitState();
      updateReviewSubmitState();
      var restoredLog = document.getElementById("semantic-assistant-log");
      if (restoredLog && assistantHtml) restoredLog.innerHTML = assistantHtml;
      return loadSemanticGraph().then(function() {{ return data; }});
    }}).then(function(data) {{
      window.scrollTo(0, scrollY);
      if (!opts.quiet) setBuilderStatus("");
      return data;
    }}).catch(function(err) {{
      if (el) {{
        el.removeAttribute("aria-busy");
        el.innerHTML = '<div class="form-error">' + err.message + '</div>';
      }}
      setBuilderStatus(err.message, "error");
      throw err;
    }});
  }}

  function afterReviewAction(promise, btn, labels) {{
    var end = beginButtonAction(btn, (labels && labels.working) || "Saving…");
    return promise.then(function(data) {{
      return refreshBuilderContent({{ quiet: true }}).then(function() {{
        end((labels && labels.success) || "Saved.");
        return data;
      }});
    }}).catch(function(err) {{
      end();
      setBuilderStatus(err.message, "error");
      alert(err.message);
      throw err;
    }});
  }}

  function updateReviewSubmitState() {{
    var submitBtn = document.getElementById("semantic-submit-reviews");
    if (!submitBtn) return;
    submitBtn.disabled = !document.querySelector(".semantic-builder-review-choice-selected");
  }}

  function selectReviewChoice(btn) {{
    var item = btn.closest(".semantic-builder-review-item");
    if (!item) return;
    item.querySelectorAll(".semantic-builder-review-choice").forEach(function(other) {{
      other.classList.remove("semantic-builder-review-choice-selected");
      other.setAttribute("aria-pressed", "false");
    }});
    btn.classList.add("semantic-builder-review-choice-selected");
    btn.setAttribute("aria-pressed", "true");
    updateReviewSubmitState();
  }}

  function bulkSelectRelationshipReviews(mode) {{
    var rows = document.querySelectorAll(".semantic-builder-relationships-nested-table tbody tr");
    var count = 0;
    rows.forEach(function(row) {{
      var matchPct = parseInt(row.getAttribute("data-rel-match-pct") || "0", 10);
      var orphanPct = parseInt(row.getAttribute("data-rel-orphan-pct") || "0", 10);
      var btn = null;
      if (mode === "approve-100-match" && matchPct === 100) {{
        btn = row.querySelector("[data-rel-approve]");
      }} else if (mode === "reject-100-orphan" && orphanPct === 100) {{
        btn = row.querySelector("[data-rel-reject]");
      }}
      if (btn) {{
        selectReviewChoice(btn);
        count += 1;
      }}
    }});
    if (count) {{
      setBuilderStatus("Selected " + count + " join(s) — click Submit review to save.");
    }} else {{
      setBuilderStatus("No matching joins to select.", "error");
    }}
  }}

  function reviewChoicePost(btn) {{
    var pkApprove = btn.getAttribute("data-pk-approve");
    if (pkApprove) return post("/entities/" + pkApprove + "/primary-key/approve");
    var pkReject = btn.getAttribute("data-pk-reject");
    if (pkReject) return post("/entities/" + pkReject + "/primary-key/reject");
    var pkPropose = btn.getAttribute("data-pk-propose");
    if (pkPropose) return post("/entities/" + pkPropose + "/primary-key/propose");

    var fkRaw = btn.getAttribute("data-fk-approve") || btn.getAttribute("data-fk-reject") || btn.getAttribute("data-fk-propose");
    if (fkRaw) {{
      var fkParts = fkRaw.split("::");
      var fkAction = btn.hasAttribute("data-fk-approve") ? "approve" : (btn.hasAttribute("data-fk-reject") ? "reject" : "propose");
      return post("/attributes/" + encodeURIComponent(fkParts[0]) + "/" + encodeURIComponent(fkParts[1]) + "/foreign-key/" + fkAction);
    }}

    var relId = btn.getAttribute("data-rel-approve") || btn.getAttribute("data-rel-reject") || btn.getAttribute("data-rel-propose");
    if (relId) {{
      var relAction = btn.hasAttribute("data-rel-approve") ? "approve" : (btn.hasAttribute("data-rel-reject") ? "reject" : "propose");
      return post("/relationships/" + relId + "/" + relAction);
    }}

    var entId = btn.getAttribute("data-entity-approve") || btn.getAttribute("data-entity-reject") || btn.getAttribute("data-entity-propose");
    if (entId) {{
      var entAction = btn.hasAttribute("data-entity-approve") ? "approve" : (btn.hasAttribute("data-entity-reject") ? "reject" : "propose");
      return post("/entities/" + entId + "/" + entAction);
    }}

    var attrRaw = btn.getAttribute("data-attr-approve") || btn.getAttribute("data-attr-reject") || btn.getAttribute("data-attr-propose");
    if (attrRaw) {{
      var attrParts = attrRaw.split("::");
      var attrAction = btn.hasAttribute("data-attr-approve") ? "approve" : (btn.hasAttribute("data-attr-reject") ? "reject" : "propose");
      return post("/attributes/" + encodeURIComponent(attrParts[0]) + "/" + encodeURIComponent(attrParts[1]) + "/" + attrAction);
    }}
    return null;
  }}

  function submitAllReviews(btn) {{
    var choices = document.querySelectorAll(".semantic-builder-review-choice-selected");
    if (!choices.length) return;
    var end = beginButtonAction(btn, "Submitting review…");
    var chain = Promise.resolve();
    choices.forEach(function(choiceBtn) {{
      chain = chain.then(function() {{
        var request = reviewChoicePost(choiceBtn);
        return request || Promise.resolve();
      }});
    }});
    return chain.then(function() {{
      return refreshBuilderContent({{ quiet: true }});
    }}).then(function() {{
      end("Review saved.");
    }}).catch(function(err) {{
      end();
      setBuilderStatus(err.message, "error");
      alert(err.message);
      throw err;
    }});
  }}

  function updateDecisionsSubmitState() {{
    var submitBtn = document.getElementById("semantic-submit-decisions");
    if (!submitBtn) return;
    var items = document.querySelectorAll(".semantic-builder-question");
    if (!items.length) {{
      submitBtn.disabled = true;
      return;
    }}
    var allReady = true;
    items.forEach(function(item) {{
      if (!item.querySelector(".semantic-builder-question-choice-selected, .semantic-builder-question-ack-selected")) {{
        allReady = false;
      }}
    }});
    submitBtn.disabled = !allReady;
  }}

  function selectQuestionChoice(btn) {{
    var item = btn.closest(".semantic-builder-question");
    if (!item) return;
    item.querySelectorAll(".semantic-builder-question-choice").forEach(function(other) {{
      other.classList.remove("semantic-builder-question-choice-selected");
      other.setAttribute("aria-pressed", "false");
    }});
    btn.classList.add("semantic-builder-question-choice-selected");
    btn.setAttribute("aria-pressed", "true");
    updateDecisionsSubmitState();
  }}

  function toggleQuestionAck(btn) {{
    var selected = btn.classList.toggle("semantic-builder-question-ack-selected");
    btn.setAttribute("aria-pressed", selected ? "true" : "false");
    updateDecisionsSubmitState();
  }}

  function submitAllDecisions(btn) {{
    var items = document.querySelectorAll(".semantic-builder-question");
    var queue = [];
    items.forEach(function(item) {{
      var choiceBtn = item.querySelector(".semantic-builder-question-choice-selected");
      if (choiceBtn) {{
        queue.push({{
          questionId: choiceBtn.getAttribute("data-question-id"),
          body: {{ choice: choiceBtn.getAttribute("data-question-choice") || "" }}
        }});
        return;
      }}
      var ackBtn = item.querySelector(".semantic-builder-question-ack-selected");
      if (ackBtn) {{
        queue.push({{
          questionId: ackBtn.getAttribute("data-question-id"),
          body: {{}}
        }});
      }}
    }});
    if (!queue.length) return;
    var end = beginButtonAction(btn, "Submitting decisions…");
    var chain = Promise.resolve();
    queue.forEach(function(entry) {{
      chain = chain.then(function() {{
        return post("/questions/" + encodeURIComponent(entry.questionId) + "/resolve", entry.body);
      }});
    }});
    return chain.then(function() {{
      return refreshBuilderContent({{ quiet: true }});
    }}).then(function() {{
      end("Decisions applied.");
    }}).catch(function(err) {{
      end();
      setBuilderStatus(err.message, "error");
      alert(err.message);
      throw err;
    }});
  }}

  function pollProfilingStatus() {{
    var attempts = 0;
    var maxAttempts = 120;
    setBuilderStatus("Profiling silver tables in the background…");
    var timer = setInterval(function() {{
      attempts += 1;
      fetch(apiRoot + "/builder-ui" + (pageStep ? "?page=" + encodeURIComponent(pageStep) : ""), {{
        credentials: "same-origin",
        headers: {{ "Accept": "application/json" }}
      }}).then(function(r) {{
        return r.json();
      }}).then(function(data) {{
        var status = data && data.workflow && data.workflow.profiling_status;
        if (status && status !== "in_progress") {{
          clearInterval(timer);
          refreshBuilderContent().then(function() {{
            setBuilderStatus("Profiling complete.", "success");
            window.setTimeout(function() {{ setBuilderStatus(""); }}, 2400);
          }});
        }} else if (attempts >= maxAttempts) {{
          clearInterval(timer);
          setBuilderStatus("Profiling is taking longer than expected. Try refreshing again.", "error");
        }}
      }}).catch(function() {{
        if (attempts >= maxAttempts) clearInterval(timer);
      }});
    }}, 5000);
  }}

  function handleInitResponse(data, endAction) {{
    if (data && data.status === "enqueued") {{
      if (endAction) endAction("Profiling started.");
      if (keysPagePath) {{
        window.location.href = keysPagePath;
        return;
      }}
      refreshBuilderContent().then(pollProfilingStatus);
      return;
    }}
    if (data && data.status === "initialized") {{
      if (endAction) endAction("Profiling complete.");
      if (keysPagePath) {{
        window.location.href = keysPagePath;
        return;
      }}
      refreshBuilderContent();
      return;
    }}
    if (data && data.status === "skipped") {{
      var reason = String(data.reason || "unknown");
      var messages = {{
        profiling_in_progress: "Profiling is already running. Wait for it to finish, then refresh.",
        init_already_completed: "Profiling already completed. Use Re-run profiling to refresh from silver."
      }};
      if (endAction) endAction();
      setBuilderStatus(messages[reason] || ("Profiling was not started: " + reason), "error");
      refreshBuilderContent({{ quiet: true }});
      return;
    }}
    if (endAction) endAction();
    refreshBuilderContent();
  }}

  function loadBuilderOptions() {{
    var node = document.getElementById("semantic-builder-options");
    if (!node) return window.semanticBuilderOptions || {{}};
    try {{
      return JSON.parse(node.textContent || "{{}}");
    }} catch (err) {{
      return window.semanticBuilderOptions || {{}};
    }}
  }}

  window.semanticBuilderOptions = loadBuilderOptions();

  function primaryKeyForEntity(silverEntity) {{
    var ents = window.semanticBuilderOptions.entities || [];
    for (var i = 0; i < ents.length; i++) {{
      if (ents[i].silver_entity === silverEntity) return ents[i].primary_key || "id";
    }}
    return "id";
  }}

  function populateColumnSelect(entitySelect, columnSelect) {{
    if (!entitySelect || !columnSelect) return;
    var entity = entitySelect.value;
    var cols = (window.semanticBuilderOptions.columns_by_entity || {{}})[entity] || [];
    columnSelect.innerHTML = "";
    if (!cols.length) {{
      columnSelect.innerHTML = "<option value=\\"\\">No columns</option>";
      return;
    }}
    cols.forEach(function(col) {{
      var opt = document.createElement("option");
      opt.value = col;
      opt.textContent = col;
      columnSelect.appendChild(opt);
    }});
  }}

  function wireEntityColumnPair(entitySelect, columnSelect) {{
    if (!entitySelect || !columnSelect) return;
    populateColumnSelect(entitySelect, columnSelect);
    entitySelect.onchange = function() {{
      populateColumnSelect(entitySelect, columnSelect);
    }};
  }}

  function wireTargetEntityColumn(entitySelect, columnInput) {{
    if (!entitySelect || !columnInput) return;
    function sync() {{
      columnInput.value = primaryKeyForEntity(entitySelect.value);
    }}
    entitySelect.onchange = sync;
    sync();
  }}

  function syncBuilderDropdowns() {{
    window.semanticBuilderOptions = loadBuilderOptions();
    wireEntityColumnPair(document.getElementById("semantic-pk-entity"), document.getElementById("semantic-pk-column"));
    wireEntityColumnPair(document.getElementById("semantic-fk-entity"), document.getElementById("semantic-fk-column"));
    wireEntityColumnPair(document.getElementById("semantic-tag-entity"), document.getElementById("semantic-tag-column"));
    wireEntityColumnPair(document.getElementById("semantic-rel-from-entity"), document.getElementById("semantic-rel-from-column"));
    wireTargetEntityColumn(document.getElementById("semantic-fk-to-entity"), document.getElementById("semantic-fk-to-column"));
    wireTargetEntityColumn(document.getElementById("semantic-rel-to-entity"), document.getElementById("semantic-rel-to-column"));
  }}

  function bindSemanticBuilderEvents() {{
    if (window.semanticBuilderEventsBound) return;
    window.semanticBuilderEventsBound = true;

    document.addEventListener("click", function(event) {{
      var root = document.querySelector(".semantic-builder-page");
      if (!root || !root.contains(event.target)) return;
      var btn = event.target.closest("button");
      if (!btn || btn.disabled) return;
      if (btn.closest(".semantic-builder-group-summary")) {{
        event.stopPropagation();
        if (!btn.classList.contains("semantic-builder-review-choice")) {{
          return;
        }}
      }}

      if (btn.id === "semantic-generate-relationships-btn") {{
        afterReviewAction(
          post("/builder/generate-relationships", {{ approve_proposed: true }}).then(function(data) {{
            var result = data && data.result ? data.result : {{}};
            var added = Number(result.added || 0);
            var proposed = Number(result.proposed_count || 0);
            if (!added) {{
              var keyInfo = result.keys_approved || {{}};
              var pkApproved = Number(keyInfo.primary_keys_approved || 0);
              var fkApproved = Number(keyInfo.foreign_keys_approved || 0);
              if (!pkApproved && !fkApproved && !proposed) {{
                setBuilderStatus(
                  "No joins were generated. Approve keys on step 1 or add them manually.",
                  "error"
                );
              }} else {{
                setBuilderStatus("No new joins were added — existing joins may already cover your keys.", "error");
              }}
            }}
            return data;
          }}),
          btn,
          {{ working: "Generating joins…", success: "Join proposals updated." }}
        );
        return;
      }}

      if (btn.id === "semantic-init-btn") {{
        var endInit = beginButtonAction(btn, "Profiling silver…");
        post("/init").then(function(data) {{
          handleInitResponse(data, endInit);
        }}).catch(function(err) {{
          endInit();
          setBuilderStatus(err.message, "error");
          alert(err.message);
        }});
        return;
      }}
      if (btn.id === "semantic-reinit-btn") {{
        if (!confirm("Re-run profiling? Proposed (non-approved) keys and tags will be refreshed from silver data.")) return;
        var endReinit = beginButtonAction(btn, "Re-profiling silver…");
        post("/init", {{ force: true }}).then(function(data) {{
          handleInitResponse(data, endReinit);
        }}).catch(function(err) {{
          endReinit();
          setBuilderStatus(err.message, "error");
          alert(err.message);
        }});
        return;
      }}
      if (btn.id === "semantic-approve-all-100-matches") {{
        bulkSelectRelationshipReviews("approve-100-match");
        return;
      }}
      if (btn.id === "semantic-reject-all-100-orphans") {{
        bulkSelectRelationshipReviews("reject-100-orphan");
        return;
      }}
      if (btn.id === "semantic-approve-all-keys") {{
        if (!confirm("Approve all proposed primary and foreign keys?")) return;
        afterReviewAction(post("/approve-all-keys"), btn, {{
          working: "Approving keys…",
          success: "Keys approved."
        }});
        return;
      }}
      if (btn.id === "semantic-approve-all-tags") {{
        afterReviewAction(post("/approve-all-tags"), btn, {{
          working: "Approving tags…",
          success: "Tags approved."
        }});
        return;
      }}
      if (btn.id === "semantic-approve-all-structure") {{
        if (!confirm("Approve all proposed entities and relationships?")) return;
        afterReviewAction(post("/approve-all-structure"), btn, {{
          working: "Approving structure…",
          success: "Entities and joins approved."
        }});
        return;
      }}
      if (btn.id === "semantic-publish-btn") {{
        if (!confirm("Publish semantic model? Gold compile requires a published model.")) return;
        var endPublish = beginButtonAction(btn, "Publishing…");
        post("/publish").then(function() {{
          return refreshBuilderContent({{ quiet: true }}).then(function() {{
            endPublish("Semantic model published.");
          }});
        }}).catch(function(err) {{
          endPublish();
          setBuilderStatus(err.message, "error");
          alert(err.message);
        }});
        return;
      }}
      if (btn.id === "semantic-discard-btn") {{
        if (!confirm("Discard draft and revert to production pin?")) return;
        afterReviewAction(post("/discard"), btn, {{
          working: "Discarding draft…",
          success: "Draft discarded."
        }});
        return;
      }}
      if (btn.id === "semantic-submit-decisions") {{
        submitAllDecisions(btn);
        return;
      }}
      if (btn.id === "semantic-submit-reviews") {{
        submitAllReviews(btn);
        return;
      }}

      if (btn.classList.contains("semantic-complete-step-btn")) {{
        var step = btn.getAttribute("data-complete-step") || "keys";
        if (!confirm("Mark this step complete and continue to the next stage?")) return;
        afterReviewAction(post("/workflow/complete-step", {{ step: step }}), btn, {{
          working: "Completing step…",
          success: "Step completed."
        }}).then(function() {{
          var next = stepNextPage[step];
          if (next) window.location.href = next;
        }});
        return;
      }}

      if (btn.classList.contains("semantic-builder-review-choice")) {{
        selectReviewChoice(btn);
        return;
      }}

      if (btn.classList.contains("semantic-builder-question-choice")) {{
        selectQuestionChoice(btn);
        return;
      }}
      if (btn.classList.contains("semantic-builder-question-ack")) {{
        toggleQuestionAck(btn);
        return;
      }}
    }});

    document.addEventListener("submit", function(event) {{
      var root = document.querySelector(".semantic-builder-page");
      if (!root || !root.contains(event.target)) return;
      var form = event.target;
      if (!form || form.tagName !== "FORM") return;

      if (form.id === "semantic-assistant-form") {{
        event.preventDefault();
        var assistantInput = document.getElementById("semantic-assistant-input");
        var assistantLog = document.getElementById("semantic-assistant-log");
        if (!assistantInput || !assistantLog) return;
        var text = (assistantInput.value || "").trim();
        if (!text) return;
        assistantInput.value = "";
        assistantLog.innerHTML += '<p class="semantic-assistant-msg semantic-assistant-msg-user"><strong>You:</strong> ' + text.replace(/</g, "&lt;") + '</p>';
        setBuilderStatus("Assistant is thinking…");
        post("/assistant", {{ message: text }}).then(function(data) {{
          var reply = (data.reply || "").replace(/</g, "&lt;");
          assistantLog.innerHTML += '<p class="semantic-assistant-msg semantic-assistant-msg-bot"><strong>Assistant:</strong> ' + reply + '</p>';
          assistantLog.scrollTop = assistantLog.scrollHeight;
          setBuilderStatus("");
        }}).catch(function(err) {{
          assistantLog.innerHTML += '<p class="form-error">' + err.message + '</p>';
          setBuilderStatus(err.message, "error");
        }});
        return;
      }}

      if (form.id === "semantic-build-pk-form") {{
        event.preventDefault();
        afterReviewAction(
          post("/builder/primary-key", {{
            entity: document.getElementById("semantic-pk-entity").value,
            column: document.getElementById("semantic-pk-column").value
          }}),
          form.querySelector("button[type=submit]"),
          {{ working: "Saving primary key…", success: "Primary key saved." }}
        );
        return;
      }}
      if (form.id === "semantic-build-fk-form") {{
        event.preventDefault();
        afterReviewAction(
          post("/builder/foreign-key", {{
            entity: document.getElementById("semantic-fk-entity").value,
            column: document.getElementById("semantic-fk-column").value,
            to_entity: document.getElementById("semantic-fk-to-entity").value,
            to_column: document.getElementById("semantic-fk-to-column").value
          }}),
          form.querySelector("button[type=submit]"),
          {{ working: "Saving foreign key…", success: "Foreign key saved." }}
        );
        return;
      }}
      if (form.id === "semantic-build-rel-form") {{
        event.preventDefault();
        afterReviewAction(
          post("/builder/relationship", {{
            from_entity: document.getElementById("semantic-rel-from-entity").value,
            from_column: document.getElementById("semantic-rel-from-column").value,
            to_entity: document.getElementById("semantic-rel-to-entity").value,
            to_column: document.getElementById("semantic-rel-to-column").value,
            cardinality: document.getElementById("semantic-rel-cardinality").value
          }}),
          form.querySelector("button[type=submit]"),
          {{ working: "Saving relationship…", success: "Relationship saved." }}
        );
        return;
      }}
      if (form.id === "semantic-build-tag-form") {{
        event.preventDefault();
        afterReviewAction(
          post("/builder/column-tag", {{
            entity: document.getElementById("semantic-tag-entity").value,
            column: document.getElementById("semantic-tag-column").value,
            concept: document.getElementById("semantic-tag-concept").value
          }}),
          form.querySelector("button[type=submit]"),
          {{ working: "Saving tag…", success: "Tag saved." }}
        );
      }}
    }});
  }}

  try {{
    bindSemanticBuilderEvents();
    updateDecisionsSubmitState();
    updateReviewSubmitState();
    if (deferContentLoad) {{
      refreshBuilderContent({{ showLoading: true }})
        .then(function() {{
          if ({json.dumps(profiling_in_progress)}) pollProfilingStatus();
        }})
        .catch(function() {{}});
    }} else if ({json.dumps(profiling_in_progress)}) {{
      pollProfilingStatus();
    }}
  }} catch (err) {{
    console.error("Semantic builder init failed", err);
    setBuilderStatus("Semantic builder controls failed to initialize. Refresh the page.", "error");
  }}
}})();
</script>
"""


def render_semantic_builder_content_html(
    *,
    settings: DnaSettings,
    is_admin: bool,
    api_root: str = "",
    builder_options: dict[str, Any] | None = None,
    page_step: str | None = None,
    url: Callable[[str], str] | None = None,
) -> str:
    ensure_semantic_model_seed(settings)
    from meshflow.dna.semantic_source_reference import source_reference_summary

    link = url or (lambda path: path)
    draft = load_semantic_model_draft(settings)
    production = load_production_semantic_model(settings)
    workflow = load_semantic_model_workflow(settings)
    step_summary = builder_step_summary(settings)
    source_reference = source_reference_summary(settings)
    coverage = semantic_model_coverage(draft)
    readiness = evaluate_publish_readiness(draft)
    differs = draft_differs_from_production(settings)
    init_completed = bool(workflow.get("init_completed"))
    profiling_in_progress = str(workflow.get("profiling_status") or "") == "in_progress"

    active_version = workflow.get("active_version")
    pin_label = f"v{active_version}" if active_version else "Not published"

    if page_step is None:
        return _landing_page_content(
            workflow,
            url=link,
            is_admin=is_admin,
            source_reference=source_reference,
        )

    rel_complete = _step_complete_button(
        step="relationships",
        label="Complete relationships step → run semantic tagging",
        completed_label="Re-complete relationships step → refresh tagging",
        is_admin=is_admin,
        hidden=page_step != "relationships",
        step_completed=bool((workflow.get("steps_completed") or {}).get("relationships")),
    )
    tag_complete = _step_complete_button(
        step="tags",
        label="Complete tagging step",
        is_admin=is_admin,
        hidden=page_step != "tags",
        step_completed=bool((workflow.get("steps_completed") or {}).get("tags")),
    )
    if builder_options is None and init_completed and is_admin:
        builder_options = build_semantic_builder_options(settings)
    elif builder_options is None:
        builder_options = {}

    keys = step_summary.get("keys") or {}
    rels = step_summary.get("relationships") or {}
    tags = step_summary.get("tags") or {}

    html = f"""
      <p class="pack-card-lead">Production pin: <strong>{escape(pin_label)}</strong>
        · Source: <code>{escape(str(draft.get("source") or settings.source))}</code>
      </p>
      <div class="semantic-builder-step-metrics">
        <span>PK approved: {keys.get("primary_keys_approved", 0)}</span>
        <span>FK approved: {keys.get("foreign_keys_approved", 0)}</span>
        <span>Joins approved: {rels.get("approved", 0)}</span>
        <span>Tags approved: {tags.get("approved", 0)}</span>
      </div>
    """
    html += _profiling_status_banner(workflow)
    html += f"""
      {_coverage_cards(coverage, readiness)}
      {_readiness_errors(readiness)}
      {_admin_actions(
          is_admin=is_admin,
          init_completed=init_completed,
          differs=differs,
          readiness=readiness,
          page_step=page_step,
      )}
    """

    gate = _step_gate_message(page_step, workflow, url=link)
    if page_step == "decisions":
        if not init_completed:
            html += """
      <div class="semantic-builder-gate">
        <p class="pack-card-lead">Start profiling from the Semantic Builder home page to surface open decisions.</p>
      </div>
            """
        else:
            html += _questions_section(
                draft.get("questions") or [],
                is_admin=is_admin,
                profiling_in_progress=profiling_in_progress,
                standalone=True,
            )
    elif gate:
        html += gate
    else:
        html += _step_revisit_notice(page_step, workflow)
        if page_step == "keys":
            html += _keys_step_section(
                draft.get("entities") or [],
                draft.get("attributes") or [],
                is_admin=is_admin,
                builder_options=builder_options,
                keys_step_completed=bool((workflow.get("steps_completed") or {}).get("keys")),
            )
        elif page_step == "relationships":
            if (draft.get("entities") or []):
                html += _graph_section_lazy(api_root=api_root)
            html += _relationships_table(
                draft.get("relationships") or [],
                is_admin=is_admin,
                complete_html=rel_complete,
                builder_options=builder_options,
                keys_step_completed=bool((workflow.get("steps_completed") or {}).get("keys")),
            )
        elif page_step == "tags":
            if (draft.get("entities") or []):
                html += _graph_section_lazy(api_root=api_root)
            html += _attributes_section(
                draft.get("attributes") or [],
                is_admin=is_admin,
                complete_html=tag_complete,
                builder_options=builder_options,
                on_tags_page=True,
            )
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
    page_step: str | None = None,
) -> Response:
    ensure_semantic_model_seed(settings)

    if page_step and page_step in BUILDER_STEPS:
        from meshflow.dna.semantic_model import sync_builder_current_step

        sync_builder_current_step(settings, page_step)

    url: Callable[[str], str] = lambda path: f"{request.script_root}{path if path.startswith('/') else f'/{path}'}"
    api_root = url("/api/semantic-model")
    workflow = load_semantic_model_workflow(settings)
    profiling_in_progress = str(workflow.get("profiling_status") or "") == "in_progress"
    draft = load_semantic_model_draft(settings)
    pending_decisions = len(_pending_decision_questions(draft.get("questions") or []))

    step_nav = _builder_step_nav(workflow, url=url, active_page=page_step)
    decisions_nav = _builder_decisions_nav(
        workflow,
        url=url,
        active_page=page_step,
        pending_count=pending_decisions,
    )

    body = f"""
    <div class="semantic-builder-page" data-page-step="{escape(page_step or 'landing')}">
      {step_nav}
      {decisions_nav}
      {page_header(
          "Semantic Builder",
          "A three-step review: profile keys, confirm relationships, then tag columns before gold compile.",
          eyebrow="DNA",
      )}
    """
    if message:
        body += f'<div class="form-success">{escape(message)}</div>'
    if error:
        body += f'<div class="form-error">{escape(error)}</div>'

    if page_step is None:
        body += f"""
      <div id="semantic-builder-status" class="semantic-builder-status" hidden></div>
      <div id="semantic-builder-content">
        {render_semantic_builder_content_html(
            settings=settings,
            is_admin=is_admin,
            page_step=None,
            url=url,
        )}
      </div>
    """
        body += _builder_styles()
        body += _builder_script(
            api_root,
            profiling_in_progress=profiling_in_progress,
            defer_content_load=False,
            page_step=None,
            script_root=request.script_root,
        )
    else:
        body += """
      <div id="semantic-builder-status" class="semantic-builder-status" hidden></div>
      <div id="semantic-builder-content" aria-busy="true">
        <div class="semantic-builder-content-loading">
          <p class="semantic-builder-loading">Loading semantic builder…</p>
        </div>
      </div>
    """
        body += _builder_styles()
        body += _builder_script(
            api_root,
            profiling_in_progress=profiling_in_progress,
            defer_content_load=True,
            page_step=page_step,
            script_root=request.script_root,
        )

    body += "</div>"

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
