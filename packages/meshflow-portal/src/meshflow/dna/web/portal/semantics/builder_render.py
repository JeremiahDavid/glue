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
from meshflow.dna.web.portal.dna_nav import SEMANTIC_BUILDER_ROOT, SEMANTICS_ROOT
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


def _builder_process_steps(workflow: dict[str, Any], step_summary: dict[str, Any], source_reference: dict[str, Any] | None = None) -> str:
    current = str(workflow.get("current_step") or BUILDER_STEPS[0])
    completed = workflow.get("steps_completed") or {}
    items = ""
    for step in BUILDER_STEPS:
        number, title, subtitle = _BUILDER_STEP_LABELS[step]
        if completed.get(step):
            state, state_label = "done", "Completed"
        elif step == current:
            state, state_label = "active", "In progress"
        else:
            state, state_label = "pending", "Up next"
        items += f"""
        <li class="semantic-builder-step semantic-builder-step-{state}">
          <span class="semantic-builder-step-num">{escape(number)}</span>
          <div class="semantic-builder-step-body">
            <strong>{escape(title)}</strong>
            <span class="semantic-builder-step-sub">{escape(subtitle)}</span>
            <span class="semantic-builder-step-state">{escape(state_label)}</span>
          </div>
        </li>
        """
    keys = step_summary.get("keys") or {}
    rels = step_summary.get("relationships") or {}
    tags = step_summary.get("tags") or {}
    ref = source_reference or {}
    ref_line = ""
    if int(ref.get("approved_build_count") or 0) > 0:
        ref_line = (
            f'<p class="pack-card-lead">Reference library: '
            f'{int(ref.get("approved_build_count") or 0)} approved '
            f'{escape(str(ref.get("source") or ""))} build(s) inform profiling consensus.</p>'
        )
    return f"""
    <section class="section semantic-builder-process">
      <div class="section-title">Semantic builder process</div>
      <p class="pack-card-lead">
        Meshflow qualifies silver in three review steps. Profiling proposes keys first;
        connector documentation and approved-build consensus are merged afterward.
      </p>
      {ref_line}
      <ol class="semantic-builder-steps">{items}</ol>
      <div class="semantic-builder-step-metrics">
        <span>PK approved: {keys.get("primary_keys_approved", 0)}</span>
        <span>FK approved: {keys.get("foreign_keys_approved", 0)}</span>
        <span>Joins approved: {rels.get("approved", 0)}</span>
        <span>Tags approved: {tags.get("approved", 0)}</span>
      </div>
    </section>
    """


def _keys_step_section(
    entities: list[dict[str, Any]],
    attributes: list[dict[str, Any]],
    *,
    is_admin: bool,
    current_step: str,
    builder_options: dict[str, Any] | None = None,
) -> str:
    if current_step != "keys":
        return ""
    fk_by_entity: dict[str, list[dict[str, Any]]] = {}
    for attribute in attributes:
        if not isinstance(attribute, dict):
            continue
        if str(attribute.get("role") or "") != "foreign_key":
            continue
        entity = str(attribute.get("entity") or "")
        fk_by_entity.setdefault(entity, []).append(attribute)

    rows = ""
    for entity in sorted(entities, key=lambda item: str(item.get("silver_entity") or "")):
        if not isinstance(entity, dict):
            continue
        ent_id = str(entity.get("id") or "")
        silver = str(entity.get("silver_entity") or "")
        pk = str(entity.get("primary_key") or "—")
        pk_status = str(entity.get("primary_key_status") or "proposed")
        pk_stats = entity.get("pk_stats") if isinstance(entity.get("pk_stats"), dict) else {}
        pk_stats_label = format_pk_stats_summary(pk_stats)
        pk_stats_html = (
            f'<div class="semantic-builder-stat-sub">{escape(pk_stats_label)}</div>'
            if pk_stats_label
            else ""
        )
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
            target = str(fk.get("fk_target_entity") or fk.get("to_entity") or "")
            target_col = str(fk.get("fk_target_column") or fk.get("to_column") or "id")
            status = str(fk.get("status") or "proposed")
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
              <td>{_status_badge(status)}</td>
              <td>{fk_actions}</td>
            </tr>
            """
        if fk_list:
            fk_count = len(fk_list)
            fk_label = f"{fk_count} foreign key{'s' if fk_count != 1 else ''}"
            rows += f"""
        <tr class="semantic-builder-group-row">
          <td colspan="4" class="semantic-builder-group-cell">
            <details class="semantic-builder-group-details">
              <summary class="semantic-builder-group-summary semantic-builder-group-summary-4">
                <span class="semantic-builder-col semantic-builder-col-table">
                  <span class="semantic-builder-expand-icon" aria-hidden="true"></span>
                  <code>{escape(silver)}</code>
                </span>
                <span class="semantic-builder-col semantic-builder-col-pk"><code>{escape(pk)}</code>{pk_stats_html}</span>
                <span class="semantic-builder-col semantic-builder-col-status">{_status_badge(pk_status)}</span>
                <span class="semantic-builder-col semantic-builder-col-actions semantic-builder-actions">{pk_actions}</span>
              </summary>
              <div class="semantic-builder-nested-panel">
                <div class="semantic-builder-nested-heading">{escape(fk_label)}</div>
                <table class="semantic-builder-table semantic-builder-nested-table">
                  <thead><tr><th>FK column</th><th>Target</th><th>Status</th><th></th></tr></thead>
                  <tbody>{fk_rows}</tbody>
                </table>
              </div>
            </details>
          </td>
        </tr>
            """
        else:
            rows += f"""
        <tr class="semantic-builder-group-row semantic-builder-group-row-flat">
          <td><code>{escape(silver)}</code></td>
          <td><code>{escape(pk)}</code>{pk_stats_html}</td>
          <td>{_status_badge(pk_status)}</td>
          <td class="semantic-builder-actions">{pk_actions}</td>
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
        complete_btn = (
            '<button type="button" class="btn btn-primary semantic-complete-step-btn" '
            'data-complete-step="keys">Complete keys step → build relationships</button>'
        )
    return f"""
    <section class="section">
      <div class="section-title">Step 1 — Primary &amp; foreign keys</div>
      <p class="pack-card-lead">
        Keys are inferred from silver profiling (column names, then value cardinality).
        {pk_proposed} PK proposed · {pk_approved} PK approved ·
        {fk_proposed} FK proposed · {fk_approved} FK approved.
        Approve or reject each proposal; documentation conflicts are listed below.
        {bulk}
      </p>
      <div class="table-wrap semantic-builder-scroll">
        <table class="semantic-builder-table semantic-builder-compact-table">
          <thead>
            <tr><th>Table</th><th>Primary key</th><th>PK status</th><th></th></tr>
          </thead>
          <tbody>{rows}</tbody>
        </table>
      </div>
      {_keys_manual_builder(is_admin=is_admin, options=builder_options or {})}
      <p style="margin-top:0.75rem">{complete_btn}</p>
    </section>
    """


def _step_complete_button(*, step: str, label: str, is_admin: bool, hidden: bool = False) -> str:
    if not is_admin or hidden:
        return ""
    return (
        f'<button type="button" class="btn btn-primary semantic-complete-step-btn" '
        f'data-complete-step="{escape(step)}">{escape(label)}</button>'
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
        <button type="submit" class="btn btn-secondary btn-sm">Add relationship</button>
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
            f'<button type="button" class="btn btn-primary btn-sm" '
            f'{approve_attr}="{escape(item_id)}">Approve</button>'
        )
    if key != "rejected":
        parts.append(
            f'<button type="button" class="btn btn-secondary btn-sm" '
            f'{reject_attr}="{escape(item_id)}">Reject</button>'
        )
    if key != "proposed":
        parts.append(
            f'<button type="button" class="btn btn-secondary btn-sm" '
            f'{propose_attr}="{escape(item_id)}">Undo</button>'
        )
    return "\n".join(parts)


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
    current_step: str = "",
    complete_html: str = "",
    builder_options: dict[str, Any] | None = None,
    keys_step_completed: bool = False,
) -> str:
    if current_step and current_step != "relationships":
        return ""
    rels_by_entity: dict[str, list[dict[str, Any]]] = {}
    for rel in relationships:
        if not isinstance(rel, dict):
            continue
        from_entity = str(rel.get("from_entity") or "")
        rels_by_entity.setdefault(from_entity, []).append(rel)

    rows = ""
    for from_entity in sorted(rels_by_entity):
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
            actions = _item_review_actions(
                item_id=rel_id,
                status=status,
                is_admin=is_admin,
                approve_attr="data-rel-approve",
                reject_attr="data-rel-reject",
                propose_attr="data-rel-propose",
            )
            rel_rows += f"""
            <tr>
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
              <summary class="semantic-builder-group-summary semantic-builder-group-summary-6">
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
                <table class="semantic-builder-table semantic-builder-nested-table">
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
    return f"""
    <section class="section">
      <div class="section-title">Step 2 — Relationships</div>
      <p class="pack-card-lead">Review proposed joins between silver tables before gold compile.</p>
      {complete_html}
      <div class="table-wrap semantic-builder-scroll">
        <table class="semantic-builder-table semantic-builder-compact-table">
          <thead>
            <tr><th>Table</th><th>Joins</th><th>Status</th><th>Join stats</th><th>Source</th><th></th></tr>
          </thead>
          <tbody>{rows}</tbody>
        </table>
      </div>
      {regen_btn}
      {_relationship_manual_builder(is_admin=is_admin, options=builder_options or {})}
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
    current_step: str = "",
    complete_html: str = "",
    builder_options: dict[str, Any] | None = None,
) -> str:
    """Semantic tag proposals (step 3) — excludes pure FK key rows."""
    if current_step and current_step != "tags":
        return ""
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
        if current_step == "tags":
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
        (draft only — publish locks production). {bulk}
      </p>
      {complete_html}
      <div class="table-wrap semantic-builder-scroll">
        <table class="semantic-builder-table semantic-builder-compact-table">
          <thead><tr><th>Table</th><th>Columns</th><th>Status</th><th></th></tr></thead>
          <tbody>{rows}</tbody>
        </table>
      </div>
      {_tags_manual_builder(is_admin=is_admin, options=builder_options or {})}
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
    if not is_admin or str(question.get("status") or "open") != "open":
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
                f'<button type="button" class="btn btn-secondary btn-sm" '
                f'data-question-apply="{qid}" data-question-choice="{choice_id}">{label}</button> '
            )
        return f'<span class="semantic-builder-question-actions">{buttons}</span>'
    return (
        f'<button type="button" class="btn btn-secondary btn-sm" '
        f'data-question-resolve="{qid}">Acknowledge</button>'
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
) -> str:
    open_questions = [
        q for q in questions if isinstance(q, dict) and str(q.get("status") or "open") == "open"
    ]
    if not open_questions:
        return ""
    items = ""
    for question in open_questions:
        qid = str(question.get("id") or "")
        text = str(question.get("text") or "")
        blocking = " · blocks publish" if question.get("blocks_publish") else ""
        action_buttons = _question_action_buttons(
            question,
            is_admin=is_admin,
            profiling_in_progress=profiling_in_progress,
        )
        items += f"""
        <li class="semantic-builder-question">
          <div class="semantic-builder-question-head">
            {_question_type_badge(question)}
            {_status_badge("open")}{blocking}
            <span class="semantic-builder-question-text">{escape(text)}</span>
          </div>
          <div class="semantic-builder-question-foot">{action_buttons}</div>
        </li>
        """
    return f"""
    <section class="section">
      <div class="section-title">Open decisions</div>
      <p class="pack-card-lead">Each item has a concrete action — assign keys, approve joins, or tag columns.</p>
      <ul class="semantic-builder-questions">{items}</ul>
    </section>
    """


def _admin_actions(
    *,
    is_admin: bool,
    init_completed: bool,
    differs: bool,
    readiness: dict[str, Any],
    current_step: str,
) -> str:
    if not is_admin:
        return ""
    init_btn = ""
    if not init_completed:
        init_btn = (
            '<button type="button" class="btn btn-primary" id="semantic-init-btn">'
            "Profile silver &amp; start builder</button>"
        )
    publish_disabled = "" if readiness.get("ready") else " disabled"
    publish_hint = "" if readiness.get("ready") else ' title="Resolve readiness issues before publishing"'
    show_structure = init_completed and current_step != "keys"
    return f"""
    <div class="semantic-builder-actions-bar">
      {init_btn}
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
.semantic-builder-process { margin-bottom: 0.25rem; }
.semantic-builder-steps {
  list-style: none;
  margin: 0.75rem 0 0;
  padding: 0;
  display: grid;
  gap: 0.65rem;
}
.semantic-builder-step {
  display: flex;
  gap: 0.75rem;
  align-items: flex-start;
  padding: 0.75rem 0.9rem;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: rgba(8, 18, 40, 0.35);
}
.semantic-builder-step-active { border-color: #38bdf8; background: rgba(56, 189, 248, 0.08); }
.semantic-builder-step-done { border-color: rgba(52, 211, 153, 0.45); }
.semantic-builder-step-pending { opacity: 0.72; }
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
.semantic-builder-step-active .semantic-builder-step-num { background: rgba(56, 189, 248, 0.25); color: #7dd3fc; }
.semantic-builder-step-done .semantic-builder-step-num { background: rgba(52, 211, 153, 0.2); color: #6ee7b7; }
.semantic-builder-step-body { display: flex; flex-direction: column; gap: 0.15rem; }
.semantic-builder-step-sub { font-size: 0.82rem; color: var(--text-muted); }
.semantic-builder-step-state { font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.04em; }
.semantic-builder-step-metrics {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
  margin-top: 0.75rem;
  font-size: 0.82rem;
  color: var(--text-muted);
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
.semantic-builder-question-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
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
) -> str:
    return f"""
<script>
(function() {{
  var apiRoot = {json.dumps(api_root)};
  var deferContentLoad = {json.dumps(defer_content_load)};

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
    return fetch(apiRoot + "/builder-ui", {{
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

  function removeResolvedQuestionFromUi(questionId) {{
    if (!questionId) return;
    var key = String(questionId).toLowerCase();
    document.querySelectorAll(".semantic-builder-question").forEach(function(item) {{
      var applyBtn = item.querySelector("[data-question-apply]");
      var resolveBtn = item.querySelector("[data-question-resolve]");
      var applyId = applyBtn ? String(applyBtn.getAttribute("data-question-apply") || "").toLowerCase() : "";
      var resolveId = resolveBtn ? String(resolveBtn.getAttribute("data-question-resolve") || "").toLowerCase() : "";
      if (applyId === key || resolveId === key) item.remove();
    }});
    var list = document.querySelector(".semantic-builder-questions");
    if (list && !list.querySelector(".semantic-builder-question")) {{
      var section = list.closest("section");
      if (section) section.remove();
    }}
  }}

  function resolveQuestion(questionId, body, btn, labels) {{
    return afterReviewAction(
      post("/questions/" + encodeURIComponent(questionId) + "/resolve", body).then(function(data) {{
        removeResolvedQuestionFromUi(questionId);
        return data;
      }}),
      btn,
      labels
    );
  }}

  function pollProfilingStatus() {{
    var attempts = 0;
    var maxAttempts = 120;
    setBuilderStatus("Profiling silver tables in the background…");
    var timer = setInterval(function() {{
      attempts += 1;
      fetch(apiRoot + "/builder-ui", {{
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
      refreshBuilderContent().then(pollProfilingStatus);
      return;
    }}
    if (data && data.status === "initialized") {{
      if (endAction) endAction("Profiling complete.");
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
        return;
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

      if (btn.classList.contains("semantic-complete-step-btn")) {{
        var step = btn.getAttribute("data-complete-step") || "keys";
        if (!confirm("Mark this step complete and continue to the next stage?")) return;
        afterReviewAction(post("/workflow/complete-step", {{ step: step }}), btn, {{
          working: "Completing step…",
          success: "Step completed."
        }});
        return;
      }}

      var pkApprove = btn.getAttribute("data-pk-approve");
      if (pkApprove) {{
        afterReviewAction(post("/entities/" + pkApprove + "/primary-key/approve"), btn);
        return;
      }}
      var pkReject = btn.getAttribute("data-pk-reject");
      if (pkReject) {{
        afterReviewAction(post("/entities/" + pkReject + "/primary-key/reject"), btn);
        return;
      }}
      var pkPropose = btn.getAttribute("data-pk-propose");
      if (pkPropose) {{
        afterReviewAction(post("/entities/" + pkPropose + "/primary-key/propose"), btn);
        return;
      }}

      var fkRaw = btn.getAttribute("data-fk-approve") || btn.getAttribute("data-fk-reject") || btn.getAttribute("data-fk-propose");
      if (fkRaw) {{
        var fkParts = fkRaw.split("::");
        var fkAction = btn.hasAttribute("data-fk-approve") ? "approve" : (btn.hasAttribute("data-fk-reject") ? "reject" : "propose");
        afterReviewAction(
          post("/attributes/" + encodeURIComponent(fkParts[0]) + "/" + encodeURIComponent(fkParts[1]) + "/foreign-key/" + fkAction),
          btn
        );
        return;
      }}

      var relId = btn.getAttribute("data-rel-approve") || btn.getAttribute("data-rel-reject") || btn.getAttribute("data-rel-propose");
      if (relId) {{
        var relAction = btn.hasAttribute("data-rel-approve") ? "approve" : (btn.hasAttribute("data-rel-reject") ? "reject" : "propose");
        afterReviewAction(post("/relationships/" + relId + "/" + relAction), btn);
        return;
      }}

      var entId = btn.getAttribute("data-entity-approve") || btn.getAttribute("data-entity-reject") || btn.getAttribute("data-entity-propose");
      if (entId) {{
        var entAction = btn.hasAttribute("data-entity-approve") ? "approve" : (btn.hasAttribute("data-entity-reject") ? "reject" : "propose");
        afterReviewAction(post("/entities/" + entId + "/" + entAction), btn);
        return;
      }}

      var attrRaw = btn.getAttribute("data-attr-approve") || btn.getAttribute("data-attr-reject") || btn.getAttribute("data-attr-propose");
      if (attrRaw) {{
        var attrParts = attrRaw.split("::");
        var attrAction = btn.hasAttribute("data-attr-approve") ? "approve" : (btn.hasAttribute("data-attr-reject") ? "reject" : "propose");
        afterReviewAction(
          post("/attributes/" + encodeURIComponent(attrParts[0]) + "/" + encodeURIComponent(attrParts[1]) + "/" + attrAction),
          btn
        );
        return;
      }}

      var questionResolve = btn.getAttribute("data-question-resolve");
      if (questionResolve) {{
        var resolution = prompt("Optional resolution note:") || "";
        resolveQuestion(
          questionResolve,
          {{ resolution: resolution }},
          btn,
          {{ working: "Saving decision…", success: "Decision saved." }}
        );
        return;
      }}
      var questionApply = btn.getAttribute("data-question-apply");
      if (questionApply) {{
        resolveQuestion(
          questionApply,
          {{ choice: btn.getAttribute("data-question-choice") || "" }},
          btn,
          {{ working: "Applying decision…", success: "Decision applied." }}
        );
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
) -> str:
    ensure_semantic_model_seed(settings)
    from meshflow.dna.semantic_source_reference import source_reference_summary

    draft = load_semantic_model_draft(settings)
    production = load_production_semantic_model(settings)
    workflow = load_semantic_model_workflow(settings)
    step_summary = builder_step_summary(settings)
    source_reference = source_reference_summary(settings)
    coverage = semantic_model_coverage(draft)
    readiness = evaluate_publish_readiness(draft)
    differs = draft_differs_from_production(settings)
    init_completed = bool(workflow.get("init_completed"))
    current_step = str(workflow.get("current_step") or BUILDER_STEPS[0])
    profiling_in_progress = str(workflow.get("profiling_status") or "") == "in_progress"

    active_version = workflow.get("active_version")
    pin_label = f"v{active_version}" if active_version else "Not published"

    rel_complete = _step_complete_button(
        step="relationships",
        label="Complete relationships step → run semantic tagging",
        is_admin=is_admin,
        hidden=current_step != "relationships",
    )
    tag_complete = _step_complete_button(
        step="tags",
        label="Complete tagging step",
        is_admin=is_admin,
        hidden=current_step != "tags",
    )
    if builder_options is None and init_completed and is_admin:
        builder_options = build_semantic_builder_options(settings)
    elif builder_options is None:
        builder_options = {}

    html = f"""
      <p class="pack-card-lead">Production pin: <strong>{escape(pin_label)}</strong>
        · Source: <code>{escape(str(draft.get("source") or settings.source))}</code>
      </p>
    """
    if init_completed:
        html += _builder_process_steps(workflow, step_summary, source_reference)
    html += _profiling_status_banner(workflow)
    html += f"""
      {_coverage_cards(coverage, readiness)}
      {_readiness_errors(readiness)}
      {_admin_actions(
          is_admin=is_admin,
          init_completed=init_completed,
          differs=differs,
          readiness=readiness,
          current_step=current_step,
      )}
    """

    if not init_completed:
        html += empty_state(
            "Semantic builder not started",
            "Run profiling to scan silver tables, propose primary and foreign keys from data, "
            "then merge connector documentation.",
        )
    else:
        html += _keys_step_section(
            draft.get("entities") or [],
            draft.get("attributes") or [],
            is_admin=is_admin,
            current_step=current_step,
            builder_options=builder_options,
        )
        if current_step in {"relationships", "tags"} and (draft.get("entities") or []):
            html += _graph_section_lazy(api_root=api_root)
        html += _relationships_table(
            draft.get("relationships") or [],
            is_admin=is_admin,
            current_step=current_step,
            complete_html=rel_complete,
            builder_options=builder_options,
            keys_step_completed=bool((workflow.get("steps_completed") or {}).get("keys")),
        )
        html += _attributes_section(
            draft.get("attributes") or [],
            is_admin=is_admin,
            current_step=current_step,
            complete_html=tag_complete,
            builder_options=builder_options,
        )
        html += _questions_section(
            draft.get("questions") or [],
            is_admin=is_admin,
            profiling_in_progress=profiling_in_progress,
        )
        if current_step == "tags":
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
    workflow = load_semantic_model_workflow(settings)
    profiling_in_progress = str(workflow.get("profiling_status") or "") == "in_progress"

    body = f"""
    <div class="semantic-builder-page">
      <div class="semantic-builder-nav">
        <a class="btn btn-secondary btn-sm" href="{escape(url(SEMANTIC_BUILDER_ROOT))}">Builder</a>
        <a class="btn btn-secondary btn-sm" href="{escape(url(SEMANTICS_ROOT))}">Column tags</a>
      </div>
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

    body += """
      <div id="semantic-builder-status" class="semantic-builder-status" hidden></div>
      <div id="semantic-builder-content" aria-busy="true">
        <div class="semantic-builder-content-loading">
          <p class="semantic-builder-loading">Loading semantic builder…</p>
        </div>
      </div>
    </div>
    """
    body += _builder_styles()
    body += _builder_script(
        api_root,
        profiling_in_progress=profiling_in_progress,
        defer_content_load=True,
    )

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
