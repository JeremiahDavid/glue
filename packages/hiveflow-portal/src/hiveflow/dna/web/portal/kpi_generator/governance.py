"""KPI Generator — draft → integrity-validate → approve → publish governance workflow."""

from __future__ import annotations

from datetime import datetime
from meshflow.compat import UTC
from typing import Any

from meshflow.athena import inject_validation_filters, normalize_athena_catalog_refs, run_query
from meshflow.dna.settings import DnaSettings
from meshflow.dna.silver_enhancement import (
    assert_preserves_silver_grain,
    assert_unique_gold_grain,
    canonical_enhancement_file,
    canonical_enhancement_id,
    collect_contributions,
    contribution_sql_relative_path,
    validate_gold_grain_columns,
    write_contribution_sql,
)
from meshflow.dna.sql_pack import build_sql_pack, save_sql_pack
from meshflow.dna.store import write_json_artifact
from meshflow.dna.web.portal.governance_helpers.proposals import (
    bump_patch_version,
    classify_manual_version_bump,
)
from meshflow.dna.web.portal.kpi_generator.catalog import (
    _columns_with_companion_aliases,
    _entity_primary_key,
    _normalize_sql_file_path,
    _prepare_implement_draft,
    _validate_layer_rules,
    _validate_sql_columns,
    _validate_sql_joins,
)
from meshflow.dna.web.portal.kpi_generator.drafts import (
    find_draft_by_layer,
    inline_silver_contribution_for_gold_sql,
    iter_proposal_drafts,
    ordered_drafts,
    primary_draft,
    proposal_intent,
)
from meshflow.dna.web.portal.kpi_generator.generation import (
    load_kpi_generator_workspace,
    load_kpi_proposal,
)
from meshflow.dna.web.portal.kpi_generator.merge import merge_silver_enhancement
from meshflow.dna.web.portal.kpi_generator.paths import kpi_generator_proposal_key
from meshflow.dna.web.portal.kpi_generator.sql_format import format_kpi_sql
from meshflow.dna.workflow import load_production_pack, load_workflow_state


def save_validation_criteria(
    settings: DnaSettings,
    *,
    proposal_id: str,
    filters: list[dict[str, str]],
) -> dict[str, Any]:
    """Persist session validation filters on the working proposal."""
    proposal = load_kpi_proposal(settings, proposal_id)
    if not proposal:
        raise FileNotFoundError(f"Unknown proposal {proposal_id}")
    last_val = dict(proposal.get("last_validation") or {})
    last_val["filters"] = filters
    last_val.pop("validation_sql", None)
    last_val.pop("result", None)
    last_val.pop("validated_at", None)
    proposal["last_validation"] = last_val
    write_json_artifact(
        settings,
        kpi_generator_proposal_key(settings.dna_config_id, proposal_id),
        proposal,
    )
    return proposal


def list_kpi_pending_drafts(settings: DnaSettings) -> list[dict[str, Any]]:
    """KPI proposals awaiting integrity validation or approval on the review kanban."""
    _, pending, _ = load_kpi_generator_workspace(settings)
    return pending


def list_kpi_approved_drafts(settings: DnaSettings) -> list[dict[str, Any]]:
    """Approved KPI proposals waiting to be published."""
    _, _, approved = load_kpi_generator_workspace(settings)
    return approved


def list_kpi_review_tab_drafts(settings: DnaSettings) -> list[dict[str, Any]]:
    """Pending + approved proposals shown on the Review Drafts tab badge."""
    return list_kpi_pending_drafts(settings) + list_kpi_approved_drafts(settings)


def _proposal_snapshot(proposal: dict[str, Any]) -> dict[str, Any]:
    """Persist full generator context on the proposal artifact."""
    drafts = iter_proposal_drafts(proposal)
    draft = primary_draft(drafts) or (proposal.get("draft") or {})
    return {
        "proposal_id": proposal.get("proposal_id"),
        "prompt": proposal.get("prompt"),
        "chat_history": list(proposal.get("chat_history") or []),
        "intent": proposal_intent(proposal),
        "questions": list(proposal.get("questions") or []),
        "reuse": proposal.get("reuse"),
        "drafts": drafts,
        "draft": draft,
        "last_validation": proposal.get("last_validation"),
        "created_at": proposal.get("created_at"),
        "username": proposal.get("username"),
        "fields_used": draft.get("fields_used") or [],
        "filters_applied": draft.get("filters_applied") or [],
        "calculation": draft.get("calculation") or draft.get("summary") or "",
        "sql": draft.get("sql") or "",
    }


def _persist_kpi_to_governance(
    settings: DnaSettings,
    *,
    proposal_id: str,
    username: str,
    pin_production: bool,
    version: str | None = None,
) -> dict[str, Any]:
    from meshflow.dna.governance import load_governance_reporting_payload, save_governance_version
    from meshflow.dna.schema import load_definition_pack
    from meshflow.dna.workflow import load_workflow_state
    from meshflow.dna.store import write_json_artifact as _write_json
    from meshflow.storage.paths import governance_workflow_key

    proposal = load_kpi_proposal(settings, proposal_id)
    if not proposal:
        raise FileNotFoundError(f"Unknown proposal {proposal_id}")
    status = str(proposal.get("status") or "").strip().lower()
    if pin_production and status not in {"working", "pending_review"}:
        raise ValueError(f"Proposal {proposal_id} is not eligible for approval")
    if not pin_production and status not in {"working", "pending_review"}:
        raise ValueError(f"Proposal {proposal_id} cannot be saved as draft")

    intent = proposal_intent(proposal)
    if intent in {"clarify", "reuse"}:
        raise ValueError("Only implement proposals can be saved as DNA drafts")

    drafts = ordered_drafts(iter_proposal_drafts(proposal))
    if not drafts:
        raise ValueError("Proposal has no SQL")
    for draft in drafts:
        _prepare_implement_draft(draft)
        if not str(draft.get("sql") or "").strip():
            raise ValueError("Proposal has no SQL")
    workflow = load_workflow_state(settings, settings.dna_config_id)
    base_pack = load_production_pack(settings)
    columns_by_table = _columns_with_companion_aliases(settings, drafts)
    for draft in drafts:
        extra = (
            columns_by_table
            if str(draft.get("layer") or "").strip().lower() == "gold"
            else None
        )
        _validate_layer_rules(
            draft,
            settings=settings,
            pack=base_pack,
            columns_by_table=extra,
        )

    active_version = str(workflow.get("active_version") or base_pack.version)
    existing_governance_version = str(proposal.get("governance_version") or "").strip()
    version_text = str(version or "").strip()

    if pin_production:
        if version_text:
            bump = classify_manual_version_bump(active_version, version_text)
            if bump.get("kind") == "invalid":
                raise ValueError(bump.get("error") or "Invalid SQL pack version")
            next_version = version_text
        else:
            next_version = bump_patch_version(active_version)
    elif status == "pending_review" and existing_governance_version:
        next_version = existing_governance_version
    else:
        next_version = bump_patch_version(active_version)

    primary = primary_draft(drafts)
    silver_draft = find_draft_by_layer({"drafts": drafts}, "silver")
    gold_draft = find_draft_by_layer({"drafts": drafts}, "gold")
    tid = str(primary.get("id") or f"kpi_{proposal_id}").strip()

    from meshflow.dna.sql_pack import load_sql_pack, load_transform_sql

    if pin_production:
        # Approve always merges from production — never a draft governance version that
        # may include other pending KPI transforms saved to the same semver.
        merge_from = load_sql_pack(settings)
    elif existing_governance_version and status == "pending_review":
        merge_from = load_sql_pack(settings, version=existing_governance_version)
    else:
        merge_from = load_sql_pack(settings)

    merge_version = merge_from.version if merge_from else active_version
    pack_id = settings.dna_config_id

    skip_silver_entities: set[str] = set()
    skip_transform_ids: set[str] = set()
    skip_output_ids: set[str] = set()
    if silver_draft:
        entity = str(silver_draft.get("target_entity") or "").strip().lower()
        if entity:
            skip_silver_entities.add(entity)
    if gold_draft:
        gold_id = str(gold_draft.get("id") or "").strip()
        gold_output = str(gold_draft.get("output_id") or gold_id).strip()
        if gold_id:
            skip_transform_ids.add(gold_id)
        if gold_output:
            skip_output_ids.add(gold_output)

    transforms: list[dict[str, Any]] = []
    sql_by_file: dict[str, str] = {}
    merged_sql_preview = ""
    sibling_proposals: list[dict[str, Any]] = []
    file_rel = ""

    if merge_from:
        for transform in merge_from.transforms:
            entity = str(transform.target_entity or "").strip().lower()
            output_id = str(transform.output_id or "").strip()
            if (
                transform.layer == "silver"
                and entity
                and entity in skip_silver_entities
            ):
                continue
            if transform.id in skip_transform_ids:
                continue
            if output_id and output_id in skip_output_ids:
                continue
            body = load_transform_sql(
                settings,
                transform,
                version=merge_from.version,
                verify_checksum=True,
            )
            sql_by_file[transform.file] = body
            transforms.append(transform.to_dict())

    if silver_draft:
        target_entity = str(silver_draft.get("target_entity") or "").strip()
        sql = str(silver_draft.get("sql") or "")
        silver_tid = str(silver_draft.get("id") or f"kpi_{proposal_id}").strip()
        assert_preserves_silver_grain(
            sql, primary_key=_entity_primary_key(base_pack, target_entity)
        )

        contributions = _collect_silver_contributions(
            settings,
            merge_from=merge_from,
            merge_version=merge_version,
            pack_id=pack_id,
            target_entity=target_entity,
        )
        sibling_statuses = ("approved",) if pin_production else ("pending_review",)
        sibling_proposals = _list_same_entity_proposals(
            settings,
            target_entity=target_entity,
            statuses=sibling_statuses,
            exclude_proposal_id=proposal_id,
        )
        contributions = _overlay_proposal_contributions(
            contributions,
            sibling_proposals,
            target_entity=target_entity,
        )
        if next_version != merge_version:
            later = collect_contributions(
                settings,
                pack_id=pack_id,
                version=next_version,
                target_entity=target_entity,
            )
            for kpi_id, body in later.items():
                cid = _normalize_contribution_id(kpi_id)
                if cid and body.strip() and cid not in contributions:
                    contributions[cid] = body.strip()
        contributions[_normalize_contribution_id(silver_tid)] = sql

        sql_by_file.update(
            _write_entity_contributions(
                settings,
                pack_id=pack_id,
                version=next_version,
                target_entity=target_entity,
                contributions=contributions,
            )
        )

        if merge_from and merge_version != next_version:
            _copy_other_entity_contributions(
                settings,
                pack_id=pack_id,
                from_version=merge_version,
                to_version=next_version,
                exclude_entity=target_entity,
            )

        merged_sql = _merge_entity_enhancement(
            settings,
            target_entity=target_entity,
            contributions=contributions,
            pack=base_pack,
        )
        merged_sql_preview = merged_sql
        canonical_id = canonical_enhancement_id(target_entity)
        canonical_file = canonical_enhancement_file(target_entity)
        sql_by_file[canonical_file] = merged_sql
        transforms.append(
            {
                "id": canonical_id,
                "layer": "silver",
                "mode": "add_columns",
                "target_entity": target_entity,
                "file": canonical_file,
                "description": (
                    f"Merged silver enhancement for {target_entity} "
                    f"({len(contributions)} contribution(s))"
                ),
            }
        )
        file_rel = contribution_sql_relative_path(
            target_entity, _normalize_contribution_id(silver_tid)
        )

    if gold_draft:
        gold_tid = str(gold_draft.get("id") or f"kpi_{proposal_id}").strip()
        gold_file = _normalize_sql_file_path(
            "gold",
            str(gold_draft.get("file") or ""),
            gold_tid,
        )
        output_id = str(gold_draft.get("output_id") or gold_tid).strip()
        grain_columns = validate_gold_grain_columns(gold_draft.get("grain_columns"))
        existing_transforms = [
            item for item in transforms if str(item.get("layer") or "") == "gold"
        ]
        assert_unique_gold_grain(
            existing_transforms,
            output_id=output_id,
            grain_columns=grain_columns,
        )
        sql_by_file[gold_file] = str(gold_draft.get("sql") or "")
        transforms.append(
            {
                "id": gold_tid,
                "layer": "gold",
                "mode": str(gold_draft.get("mode") or "").strip().lower(),
                "file": gold_file,
                "output_id": output_id,
                "grain_columns": grain_columns,
                "description": str(
                    gold_draft.get("summary") or gold_draft.get("calculation") or ""
                ),
            }
        )
        file_rel = gold_file

    sql_pack, sql_by_file = build_sql_pack(
        version=next_version,
        transforms=transforms,
        sql_by_file=sql_by_file,
    )

    pack_dict = base_pack.to_dict()
    pack_dict["version"] = next_version
    if pin_production:
        pack_dict["status"] = "production"
        pack_dict.setdefault("approval", {})
        pack_dict["approval"]["status"] = "production"
        pack_dict["approval"]["approver"] = username or "kpi_generator"
        pack_dict["approval"]["approved_at"] = datetime.now(UTC).date().isoformat()
    else:
        pack_dict["status"] = "draft"
        pack_dict.setdefault("approval", {})
        pack_dict["approval"]["status"] = "draft"

    new_pack = load_definition_pack(pack_dict)
    reporting = load_governance_reporting_payload(
        settings,
        settings.dna_config_id,
        active_version,
    )
    if isinstance(reporting, dict):
        reporting = dict(reporting)
        reporting["version"] = next_version

    save_governance_version(
        settings,
        pack=new_pack,
        reporting=reporting if isinstance(reporting, dict) else None,
    )
    save_sql_pack(settings, sql_pack, sql_by_file)

    workflow_payload = dict(workflow)
    history = list(workflow_payload.get("history") or [])
    history.append(
        {
            "version": next_version,
            "status": "production" if pin_production else "draft",
            "approver": username or "kpi_generator",
            "at": datetime.now(UTC).isoformat(),
            "notes": (
                f"KPI Generator approved transform {tid}"
                if pin_production
                else f"KPI Generator draft transform {tid}"
            ),
            "target": "dna",
            "proposal_id": proposal_id,
            "action": "kpi_generator_approve" if pin_production else "kpi_generator_draft",
        }
    )
    workflow_payload["history"] = history[-50:]
    if pin_production:
        workflow_payload["active_version"] = next_version
        if isinstance(reporting, dict):
            workflow_payload["active_reporting_version"] = next_version
    _write_json(
        settings,
        governance_workflow_key(settings.dna_config_id),
        workflow_payload,
    )

    now = datetime.now(UTC).isoformat()
    proposal["intent"] = "implement"
    proposal["drafts"] = drafts
    proposal["draft"] = primary
    proposal["governance_snapshot"] = _proposal_snapshot(proposal)
    proposal["governance_version"] = next_version
    if merged_sql_preview:
        proposal["merged_enhancement_sql"] = merged_sql_preview
    if pin_production:
        proposal["status"] = "approved"
        proposal["approved_version"] = next_version
        proposal["approved_at"] = now
    else:
        proposal["status"] = "pending_review"
        proposal["saved_at"] = now
    write_json_artifact(
        settings,
        kpi_generator_proposal_key(settings.dna_config_id, proposal_id),
        proposal,
    )
    if merged_sql_preview and sibling_proposals:
        _stamp_merged_enhancement_sql(settings, sibling_proposals, merged_sql_preview)
    return {
        "status": "approved" if pin_production else "pending_review",
        "version": next_version,
        "proposal_id": proposal_id,
        "sql_file": file_rel,
        "transform_id": tid,
        "merged_enhancement_sql": merged_sql_preview or None,
    }


def save_kpi_governance_draft(
    settings: DnaSettings,
    *,
    proposal_id: str,
    username: str = "",
) -> dict[str, Any]:
    """Save exact SQL into governance as a DNA draft (does not pin production)."""
    return _persist_kpi_to_governance(
        settings,
        proposal_id=proposal_id,
        username=username,
        pin_production=False,
    )


def update_kpi_draft_sql(
    settings: DnaSettings,
    *,
    proposal_id: str,
    sql: str = "",
    sql_by_layer: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Persist edited SQL on the working proposal draft(s)."""
    proposal = load_kpi_proposal(settings, proposal_id)
    if not proposal:
        raise FileNotFoundError(f"Unknown proposal {proposal_id}")
    intent = proposal_intent(proposal)
    if intent == "reuse":
        reuse = dict(proposal.get("reuse") or {})
        body = format_kpi_sql(
            str((sql_by_layer or {}).get("gold") or sql or reuse.get("sql") or "")
        )
        if body:
            reuse["sql"] = body
            proposal["reuse"] = reuse
            write_json_artifact(
                settings,
                kpi_generator_proposal_key(settings.dna_config_id, proposal_id),
                proposal,
            )
        return proposal
    if intent == "clarify":
        raise ValueError("Clarify turns have no SQL to edit")
    drafts = [dict(item) for item in iter_proposal_drafts(proposal)]
    if not drafts:
        raise ValueError("Proposal has no SQL")
    layer_sql = {
        str(layer).strip().lower(): format_kpi_sql(body)
        for layer, body in (sql_by_layer or {}).items()
        if str(body or "").strip()
    }
    if str(sql or "").strip() and "gold" not in layer_sql and "silver" not in layer_sql:
        primary = primary_draft(drafts)
        layer_sql[str(primary.get("layer") or "gold").strip().lower() or "gold"] = (
            format_kpi_sql(sql)
        )
    columns_by_table = _columns_with_companion_aliases(settings, drafts)
    pack = load_production_pack(settings)
    updated: list[dict[str, Any]] = []
    for draft in drafts:
        layer = str(draft.get("layer") or "").strip().lower()
        if layer in layer_sql:
            draft["sql"] = layer_sql[layer]
        _prepare_implement_draft(draft)
        extra = columns_by_table if layer == "gold" else None
        _validate_layer_rules(
            draft,
            settings=settings,
            pack=pack,
            columns_by_table=extra,
        )
        updated.append(draft)
    proposal["drafts"] = updated
    proposal["draft"] = primary_draft(updated)
    write_json_artifact(
        settings,
        kpi_generator_proposal_key(settings.dna_config_id, proposal_id),
        proposal,
    )
    return proposal


def run_validation(
    settings: DnaSettings,
    *,
    proposal_id: str,
    filters: list[dict[str, str]],
    company: str | None = None,
    environment: str | None = None,
    region: str | None = None,
) -> dict[str, Any]:
    """Run session-only validation SELECT; does not mutate approved SQL."""
    proposal = load_kpi_proposal(settings, proposal_id)
    if not proposal:
        raise FileNotFoundError(f"Unknown proposal {proposal_id}")
    intent = proposal_intent(proposal)
    reuse = proposal.get("reuse") if isinstance(proposal.get("reuse"), dict) else {}
    gold_draft = find_draft_by_layer(proposal, "gold")
    silver_draft = find_draft_by_layer(proposal, "silver")
    sql = ""
    if intent == "reuse":
        sql = str(reuse.get("sql") or "").strip()
    elif gold_draft:
        sql = str(gold_draft.get("sql") or "").strip()
        if silver_draft:
            sql = inline_silver_contribution_for_gold_sql(
                sql,
                source=settings.source or "",
                target_entity=str(silver_draft.get("target_entity") or ""),
                contribution_sql=str(silver_draft.get("sql") or ""),
            )
    elif silver_draft:
        sql = str(silver_draft.get("sql") or "").strip()
    if not sql:
        raise ValueError("Proposal has no SQL")
    from meshflow.project_config import (
        athena_workgroup_name,
        glue_database_name,
        resolve_selection,
    )

    resolved_company = (company or settings.company or "").strip()
    resolved_env = (environment or "").strip()
    if not resolved_company or not resolved_env:
        sel_c, sel_e = resolve_selection()
        resolved_company = resolved_company or sel_c
        resolved_env = resolved_env or sel_e
    database = glue_database_name(resolved_company, resolved_env)
    if silver_draft and not gold_draft and intent != "reuse":
        from meshflow.dna.silver_enhancement import retarget_silver_sql_to_stg

        sql = retarget_silver_sql_to_stg(sql, source=settings.source or "")
    sql = normalize_athena_catalog_refs(
        sql,
        source=settings.source or "",
        database=database,
    )
    wrapped = inject_validation_filters(sql, filters)
    workgroup = athena_workgroup_name(resolved_company, resolved_env)
    result = run_query(
        wrapped,
        database=database,
        workgroup=workgroup,
        region=region,
        max_rows=100,
    )
    proposal["last_validation"] = {
        "filters": filters,
        "validation_sql": wrapped,
        "result": {
            "columns": result.get("columns"),
            "rows": result.get("rows"),
            "execution_id": result.get("execution_id"),
        },
        "validated_at": datetime.now(UTC).isoformat(),
    }
    write_json_artifact(
        settings,
        kpi_generator_proposal_key(settings.dna_config_id, proposal_id),
        proposal,
    )
    return proposal["last_validation"]


def validate_kpi_draft_group(
    settings: DnaSettings,
    *,
    target_key: str,
    proposal_ids: list[str] | None = None,
    company: str | None = None,
    environment: str | None = None,
    region: str | None = None,
    attempt_repair: bool = True,
) -> dict[str, Any]:
    from meshflow.dna.web.portal.kpi_generator.integrity import (
        group_pending_drafts,
        load_proposals_by_ids,
        persist_group_integrity_validation,
        validate_draft_group_integrity,
    )

    if proposal_ids:
        proposals = load_proposals_by_ids(settings, proposal_ids)
    else:
        proposals = group_pending_drafts(list_kpi_pending_drafts(settings)).get(target_key, [])
    if not proposals:
        raise ValueError(f"No pending drafts for group {target_key!r}")
    validation = validate_draft_group_integrity(
        settings,
        target_key=target_key,
        proposals=proposals,
        company=company,
        environment=environment,
        region=region,
        attempt_repair=attempt_repair,
    )
    validation["target_key"] = target_key
    persist_group_integrity_validation(settings, proposals, validation)
    return validation


def _require_group_integrity_passed(proposals: list[dict[str, Any]], target_key: str) -> None:
    from meshflow.dna.web.portal.kpi_generator.integrity import group_integrity_passed

    if not group_integrity_passed(proposals, target_key=target_key):
        raise ValueError(
            f"Integrity validation has not passed for {target_key}. "
            "Run integrity validation for this table group before approving."
        )


def approve_kpi_draft_group(
    settings: DnaSettings,
    *,
    target_key: str,
    proposal_ids: list[str],
    username: str = "",
    version: str | None = None,
    company: str | None = None,
    environment: str | None = None,
    region: str | None = None,
) -> dict[str, Any]:
    from meshflow.dna.web.portal.kpi_generator.integrity import load_proposals_by_ids

    proposals = load_proposals_by_ids(settings, proposal_ids)
    if not proposals:
        raise ValueError(f"No proposals to approve for {target_key!r}")

    _require_group_integrity_passed(proposals, target_key)

    results: list[dict[str, Any]] = []
    for proposal in proposals:
        pid = str(proposal.get("proposal_id") or "").strip()
        if not pid:
            continue
        results.append(
            approve_kpi_proposal(
                settings,
                proposal_id=pid,
                username=username,
                version=version,
                skip_integrity_check=True,
            )
        )
    return {
        "status": "approved",
        "target_key": target_key,
        "approved": results,
    }


def approve_kpi_proposal(
    settings: DnaSettings,
    *,
    proposal_id: str,
    username: str = "",
    version: str | None = None,
    skip_integrity_check: bool = False,
    company: str | None = None,
    environment: str | None = None,
    region: str | None = None,
) -> dict[str, Any]:
    """Pin KPI SQL into production governance at the chosen semver."""
    if not skip_integrity_check:
        proposal = load_kpi_proposal(settings, proposal_id)
        if not proposal:
            raise FileNotFoundError(f"Unknown proposal {proposal_id}")
        draft = proposal.get("draft") or {}
        from meshflow.dna.web.portal.kpi_generator.integrity import (
            draft_target_key,
            proposal_integrity_passed,
        )

        target_key = draft_target_key(draft)
        if not proposal_integrity_passed(proposal):
            raise ValueError(
                f"Integrity validation has not passed for {target_key}. "
                "Run integrity validation before approving."
            )
    return _persist_kpi_to_governance(
        settings,
        proposal_id=proposal_id,
        username=username,
        pin_production=True,
        version=version,
    )


def reject_kpi_draft_group(
    settings: DnaSettings,
    *,
    target_key: str,
    proposal_ids: list[str],
    username: str = "",
) -> dict[str, Any]:
    from meshflow.dna.web.portal.kpi_generator.integrity import load_proposals_by_ids

    proposals = load_proposals_by_ids(settings, proposal_ids)
    if not proposals:
        raise ValueError(f"No proposals to reject for {target_key!r}")
    rejected: list[dict[str, Any]] = []
    for proposal in proposals:
        pid = str(proposal.get("proposal_id") or "").strip()
        if not pid:
            continue
        status = str(proposal.get("status") or "").strip().lower()
        if status != "pending_review":
            continue
        rejected.append(
            reject_kpi_proposal(settings, proposal_id=pid, username=username)
        )
    return {
        "status": "rejected",
        "target_key": target_key,
        "rejected": rejected,
    }


def reject_kpi_proposal(
    settings: DnaSettings,
    *,
    proposal_id: str,
    username: str = "",
) -> dict[str, Any]:
    proposal = load_kpi_proposal(settings, proposal_id)
    if not proposal:
        raise FileNotFoundError(f"Unknown proposal {proposal_id}")
    prior_status = str(proposal.get("status") or "").strip().lower()
    if prior_status not in {"pending_review", "approved"}:
        raise ValueError(
            f"Proposal {proposal_id} cannot be removed "
            f"(status={prior_status!r}; expected pending_review or approved)"
        )
    proposal["status"] = "rejected"
    proposal["rejected_at"] = datetime.now(UTC).isoformat()
    proposal["rejected_by"] = username
    write_json_artifact(
        settings,
        kpi_generator_proposal_key(settings.dna_config_id, proposal_id),
        proposal,
    )
    return {
        "status": "rejected",
        "proposal_id": proposal_id,
        "prior_status": prior_status,
    }


def discard_kpi_proposal(
    settings: DnaSettings,
    *,
    proposal_id: str,
    username: str = "",
) -> dict[str, Any]:
    """Discard a working generator session and clear chat context."""
    proposal = load_kpi_proposal(settings, proposal_id)
    if not proposal:
        raise FileNotFoundError(f"Unknown proposal {proposal_id}")
    if str(proposal.get("status") or "").strip().lower() != "working":
        raise ValueError(f"Proposal {proposal_id} is not a working draft")
    proposal["status"] = "discarded"
    proposal["discarded_at"] = datetime.now(UTC).isoformat()
    proposal["discarded_by"] = username
    write_json_artifact(
        settings,
        kpi_generator_proposal_key(settings.dna_config_id, proposal_id),
        proposal,
    )
    return {"status": "discarded", "proposal_id": proposal_id}


def approve_all_kpi_drafts(
    settings: DnaSettings,
    *,
    username: str = "",
) -> list[dict[str, Any]]:
    from meshflow.dna.web.portal.kpi_generator.integrity import classify_proposal_stage

    results: list[dict[str, Any]] = []
    for proposal in list_kpi_pending_drafts(settings):
        if classify_proposal_stage(proposal) != "approve":
            continue
        pid = str(proposal.get("proposal_id") or "").strip()
        if not pid:
            continue
        results.append(
            approve_kpi_proposal(
                settings,
                proposal_id=pid,
                username=username,
                skip_integrity_check=True,
            )
        )
    return results


def reject_all_kpi_drafts(
    settings: DnaSettings,
    *,
    username: str = "",
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for proposal in list_kpi_pending_drafts(settings):
        pid = str(proposal.get("proposal_id") or "").strip()
        if not pid:
            continue
        status = str(proposal.get("status") or "").strip().lower()
        if status != "pending_review":
            continue
        results.append(
            reject_kpi_proposal(settings, proposal_id=pid, username=username)
        )
    return results


def finalize_approved_silver_enhancements(
    settings: DnaSettings,
    *,
    proposals: list[dict[str, Any]],
    username: str = "",
) -> dict[str, Any]:
    """Rebuild one canonical silver enhancement per entity covering every approved KPI.

    Publish uses this so multiple column adds on the same table become a single
    ``enhance__{entity}`` transform that includes all contributions, not just the
    last KPI that was approved.
    """
    from meshflow.dna.governance import load_governance_reporting_payload, save_governance_version
    from meshflow.dna.schema import load_definition_pack
    from meshflow.dna.sql_pack import load_sql_pack, load_transform_sql
    from meshflow.dna.store import write_json_artifact as _write_json
    from meshflow.storage.paths import governance_workflow_key

    silver_entities: dict[str, list[dict[str, Any]]] = {}
    for proposal in proposals:
        entity = _proposal_silver_entity(proposal)
        if entity:
            silver_entities.setdefault(entity, []).append(proposal)
    workflow = load_workflow_state(settings, settings.dna_config_id)
    active_version = str(workflow.get("active_version") or "").strip()
    if not silver_entities:
        return {
            "version": active_version,
            "merged_by_entity": {},
            "rewritten": False,
        }

    merge_from = load_sql_pack(settings)
    pack_id = settings.dna_config_id
    base_pack = load_production_pack(settings)
    merge_version = str(merge_from.version if merge_from else active_version or base_pack.version)
    approved_pool = list_kpi_approved_drafts(settings)

    merged_by_entity: dict[str, str] = {}
    entity_contributions: dict[str, dict[str, str]] = {}
    needs_rewrite = False
    for entity in silver_entities:
        contributions = _collect_silver_contributions(
            settings,
            merge_from=merge_from,
            merge_version=merge_version,
            pack_id=pack_id,
            target_entity=entity,
        )
        contributions = _overlay_proposal_contributions(
            contributions,
            approved_pool,
            target_entity=entity,
        )
        entity_contributions[entity] = contributions
        merged_sql = _merge_entity_enhancement(
            settings,
            target_entity=entity,
            contributions=contributions,
            pack=base_pack,
        )
        merged_by_entity[entity] = merged_sql
        current = _canonical_sql_for_entity(settings, merge_from, entity)
        if format_kpi_sql(merged_sql) != format_kpi_sql(current):
            needs_rewrite = True

    for entity, merged_sql in merged_by_entity.items():
        affected = [
            item for item in approved_pool if _proposal_silver_entity(item) == entity
        ]
        _stamp_merged_enhancement_sql(settings, affected, merged_sql)
        for proposal in silver_entities[entity]:
            proposal["merged_enhancement_sql"] = merged_sql

    if not needs_rewrite:
        return {
            "version": merge_version,
            "merged_by_entity": merged_by_entity,
            "rewritten": False,
        }

    next_version = bump_patch_version(merge_version)
    sql_by_file: dict[str, str] = {}
    transforms: list[dict[str, Any]] = []
    skip_entities = set(silver_entities)
    if merge_from:
        for transform in merge_from.transforms:
            if (
                transform.layer == "silver"
                and str(transform.target_entity or "").strip().lower() in skip_entities
            ):
                continue
            body = load_transform_sql(
                settings,
                transform,
                version=merge_from.version,
                verify_checksum=True,
            )
            sql_by_file[transform.file] = body
            transforms.append(transform.to_dict())

    for entity, contributions in entity_contributions.items():
        sql_by_file.update(
            _write_entity_contributions(
                settings,
                pack_id=pack_id,
                version=next_version,
                target_entity=entity,
                contributions=contributions,
            )
        )
        canonical_file = canonical_enhancement_file(entity)
        sql_by_file[canonical_file] = merged_by_entity[entity]
        transforms.append(
            {
                "id": canonical_enhancement_id(entity),
                "layer": "silver",
                "mode": "add_columns",
                "target_entity": entity,
                "file": canonical_file,
                "description": (
                    f"Merged silver enhancement for {entity} "
                    f"({len(contributions)} contribution(s))"
                ),
            }
        )

    if merge_from and merge_version != next_version:
        _copy_other_entity_contributions(
            settings,
            pack_id=pack_id,
            from_version=merge_version,
            to_version=next_version,
            exclude_entities=skip_entities,
        )

    sql_pack, sql_by_file = build_sql_pack(
        version=next_version,
        transforms=transforms,
        sql_by_file=sql_by_file,
    )
    pack_dict = base_pack.to_dict()
    pack_dict["version"] = next_version
    pack_dict["status"] = "production"
    pack_dict.setdefault("approval", {})
    pack_dict["approval"]["status"] = "production"
    pack_dict["approval"]["approver"] = username or "kpi_generator"
    pack_dict["approval"]["approved_at"] = datetime.now(UTC).date().isoformat()
    new_pack = load_definition_pack(pack_dict)
    reporting = load_governance_reporting_payload(
        settings,
        settings.dna_config_id,
        merge_version,
    )
    if isinstance(reporting, dict):
        reporting = dict(reporting)
        reporting["version"] = next_version
    save_governance_version(
        settings,
        pack=new_pack,
        reporting=reporting if isinstance(reporting, dict) else None,
    )
    save_sql_pack(settings, sql_pack, sql_by_file)

    workflow_payload = dict(workflow)
    history = list(workflow_payload.get("history") or [])
    history.append(
        {
            "version": next_version,
            "status": "production",
            "approver": username or "kpi_generator",
            "at": datetime.now(UTC).isoformat(),
            "notes": (
                "KPI publish merged total silver enhancement(s) for "
                + ", ".join(sorted(silver_entities))
            ),
            "target": "dna",
            "action": "kpi_generator_publish_merge",
        }
    )
    workflow_payload["history"] = history[-50:]
    workflow_payload["active_version"] = next_version
    if isinstance(reporting, dict):
        workflow_payload["active_reporting_version"] = next_version
    _write_json(
        settings,
        governance_workflow_key(settings.dna_config_id),
        workflow_payload,
    )
    return {
        "version": next_version,
        "merged_by_entity": merged_by_entity,
        "rewritten": True,
    }


def publish_kpi_draft_group(
    settings: DnaSettings,
    *,
    target_key: str,
    proposal_ids: list[str],
    client_id: str = "",
    username: str = "",
    company: str | None = None,
    environment: str | None = None,
    monthly_limit: int | None = None,
) -> dict[str, Any]:
    """Trigger DNA refresh for approved KPIs and mark them published."""
    from meshflow.dna.web.portal.dna_manual_refresh import trigger_manual_refresh
    from meshflow.dna.web.portal.kpi_generator.integrity import load_proposals_by_ids
    from meshflow.dna.workflow import load_workflow_state

    proposals = load_proposals_by_ids(settings, proposal_ids)
    if not proposals:
        raise ValueError(f"No proposals to publish for {target_key!r}")

    for proposal in proposals:
        status = str(proposal.get("status") or "").strip().lower()
        if status != "approved":
            raise ValueError(
                f"Proposal {proposal.get('proposal_id')!r} must be approved before publish "
                f"(status={status!r})."
            )

    finalize = finalize_approved_silver_enhancements(
        settings,
        proposals=proposals,
        username=username,
    )
    proposals = load_proposals_by_ids(settings, proposal_ids)

    workflow = load_workflow_state(settings, settings.dna_config_id)
    pinned_version = str(
        finalize.get("version") or workflow.get("active_version") or ""
    ).strip()
    if not pinned_version:
        pinned_version = str(proposals[0].get("approved_version") or "").strip()
    if not pinned_version:
        raise ValueError("No production DNA version is pinned yet.")

    resolved_company = (company or settings.company or "").strip()
    result = trigger_manual_refresh(
        settings,
        client_id=client_id,
        username=username,
        pinned_version=pinned_version,
        company=resolved_company,
        environment=environment,
        monthly_limit=monthly_limit,
    )
    refresh_kind = "dna"

    now = datetime.now(UTC).isoformat()
    published: list[dict[str, Any]] = []
    execution_arn = str(result.get("execution_arn") or "").strip()
    for proposal in proposals:
        pid = str(proposal.get("proposal_id") or "").strip()
        if not pid:
            continue
        proposal["status"] = "published"
        proposal["published_at"] = now
        proposal["published_by"] = username
        if execution_arn:
            proposal["publish_execution_arn"] = execution_arn
        write_json_artifact(
            settings,
            kpi_generator_proposal_key(settings.dna_config_id, pid),
            proposal,
        )
        published.append(
            {
                "proposal_id": pid,
                "status": "published",
                "published_at": now,
            }
        )

    return {
        "status": "published",
        "target_key": target_key,
        "refresh_kind": refresh_kind,
        "published": published,
        "execution_arn": execution_arn,
        "quota": result.get("quota"),
    }


def publish_all_approved_kpis(
    settings: DnaSettings,
    *,
    client_id: str = "",
    username: str = "",
    company: str | None = None,
    environment: str | None = None,
    monthly_limit: int | None = None,
) -> dict[str, Any]:
    """Publish every approved KPI by running one DNA silver + gold refresh."""
    from meshflow.dna.web.portal.dna_manual_refresh import trigger_manual_refresh
    from meshflow.dna.workflow import load_workflow_state

    proposals = list_kpi_approved_drafts(settings)
    if not proposals:
        raise ValueError("No approved KPIs are waiting to be published.")

    finalize = finalize_approved_silver_enhancements(
        settings,
        proposals=proposals,
        username=username,
    )
    proposals = list_kpi_approved_drafts(settings)

    workflow = load_workflow_state(settings, settings.dna_config_id)
    pinned_version = str(
        finalize.get("version") or workflow.get("active_version") or ""
    ).strip()
    if not pinned_version:
        pinned_version = str(proposals[0].get("approved_version") or "").strip()
    if not pinned_version:
        raise ValueError("No production DNA version is pinned yet.")

    resolved_company = (company or settings.company or "").strip()
    dna_result = trigger_manual_refresh(
        settings,
        client_id=client_id,
        username=username,
        pinned_version=pinned_version,
        company=resolved_company,
        environment=environment,
        monthly_limit=monthly_limit,
    )
    refreshes: list[dict[str, Any]] = [
        {"kind": "dna", "result": dna_result},
    ]

    now = datetime.now(UTC).isoformat()
    published: list[dict[str, Any]] = []
    for proposal in proposals:
        pid = str(proposal.get("proposal_id") or "").strip()
        if not pid:
            continue
        proposal["status"] = "published"
        proposal["published_at"] = now
        proposal["published_by"] = username
        write_json_artifact(
            settings,
            kpi_generator_proposal_key(settings.dna_config_id, pid),
            proposal,
        )
        published.append({"proposal_id": pid, "status": "published", "published_at": now})

    return {
        "status": "published",
        "published": published,
        "refreshes": refreshes,
    }


def _normalize_contribution_id(kpi_id: str) -> str:
    return kpi_id.strip().lower().replace(" ", "_")


def _proposal_silver_entity(proposal: dict[str, Any]) -> str:
    silver = find_draft_by_layer(proposal, "silver")
    if not silver:
        return ""
    return str(silver.get("target_entity") or "").strip().lower()


def _overlay_proposal_contributions(
    contributions: dict[str, str],
    proposals: list[dict[str, Any]],
    *,
    target_entity: str,
) -> dict[str, str]:
    """Overlay per-KPI SQL from proposals targeting ``target_entity``."""
    merged = {
        _normalize_contribution_id(kpi_id): body
        for kpi_id, body in contributions.items()
        if str(kpi_id).strip() and str(body).strip()
    }
    entity = target_entity.strip().lower()
    for proposal in proposals:
        if _proposal_silver_entity(proposal) != entity:
            continue
        silver = find_draft_by_layer(proposal, "silver") or {}
        tid = _normalize_contribution_id(
            str(silver.get("id") or proposal.get("proposal_id") or "")
        )
        sql = str(silver.get("sql") or "").strip()
        if tid and sql:
            merged[tid] = sql
    return merged


def _list_same_entity_proposals(
    settings: DnaSettings,
    *,
    target_entity: str,
    statuses: tuple[str, ...],
    exclude_proposal_id: str = "",
) -> list[dict[str, Any]]:
    entity = target_entity.strip().lower()
    exclude = exclude_proposal_id.strip().lower()
    pool: list[dict[str, Any]] = []
    if "pending_review" in statuses:
        pool.extend(list_kpi_pending_drafts(settings))
    if "approved" in statuses:
        pool.extend(list_kpi_approved_drafts(settings))
    found: list[dict[str, Any]] = []
    for proposal in pool:
        pid = str(proposal.get("proposal_id") or "").strip().lower()
        if exclude and pid == exclude:
            continue
        if _proposal_silver_entity(proposal) != entity:
            continue
        found.append(proposal)
    return found


def _stamp_merged_enhancement_sql(
    settings: DnaSettings,
    proposals: list[dict[str, Any]],
    merged_sql: str,
) -> None:
    sql = str(merged_sql or "").strip()
    if not sql:
        return
    for proposal in proposals:
        pid = str(proposal.get("proposal_id") or "").strip()
        if not pid:
            continue
        live = load_kpi_proposal(settings, pid) or proposal
        live["merged_enhancement_sql"] = sql
        write_json_artifact(
            settings,
            kpi_generator_proposal_key(settings.dna_config_id, pid),
            live,
        )
        proposal["merged_enhancement_sql"] = sql


def _merge_entity_enhancement(
    settings: DnaSettings,
    *,
    target_entity: str,
    contributions: dict[str, str],
    pack: Any,
) -> str:
    primary_key = _entity_primary_key(pack, target_entity)

    def _validate_merged(merged: str) -> None:
        _validate_sql_joins(settings, merged)
        _validate_sql_columns(settings, merged)

    return merge_silver_enhancement(
        settings,
        target_entity=target_entity,
        contributions=contributions,
        primary_key=primary_key,
        validate_sql=_validate_merged,
    )


def _canonical_sql_for_entity(settings: DnaSettings, pack: Any | None, entity: str) -> str:
    if pack is None:
        return ""
    from meshflow.dna.sql_pack import load_transform_sql

    expected = canonical_enhancement_id(entity)
    for transform in pack.transforms:
        if transform.id != expected:
            continue
        body = load_transform_sql(
            settings,
            transform,
            version=pack.version,
            verify_checksum=True,
        )
        return format_kpi_sql(body)
    return ""


def _write_entity_contributions(
    settings: DnaSettings,
    *,
    pack_id: str,
    version: str,
    target_entity: str,
    contributions: dict[str, str],
) -> dict[str, str]:
    sql_by_file: dict[str, str] = {}
    for kpi_id, body in contributions.items():
        rel = write_contribution_sql(
            settings,
            pack_id=pack_id,
            version=version,
            target_entity=target_entity,
            kpi_id=kpi_id,
            sql=body,
        )
        sql_by_file[rel] = body.strip()
    return sql_by_file


def _collect_silver_contributions(
    settings: DnaSettings,
    *,
    merge_from: Any | None,
    merge_version: str,
    pack_id: str,
    target_entity: str,
) -> dict[str, str]:
    from meshflow.dna.sql_pack import load_transform_sql

    contributions = {
        _normalize_contribution_id(kpi_id): body
        for kpi_id, body in collect_contributions(
            settings,
            pack_id=pack_id,
            version=merge_version,
            target_entity=target_entity,
        ).items()
        if str(kpi_id).strip() and str(body).strip()
    }
    if merge_from:
        entity_key = target_entity.strip().lower()
        canonical_id = canonical_enhancement_id(target_entity)
        for transform in merge_from.transforms:
            if transform.layer != "silver":
                continue
            if str(transform.target_entity or "").strip().lower() != entity_key:
                continue
            transform_id = _normalize_contribution_id(transform.id)
            if transform_id == canonical_id and contributions:
                continue
            if transform_id in contributions:
                continue
            body = load_transform_sql(
                settings,
                transform,
                version=merge_from.version,
                verify_checksum=True,
            )
            contributions[transform_id] = body.strip()
    return contributions


def _copy_other_entity_contributions(
    settings: DnaSettings,
    *,
    pack_id: str,
    from_version: str,
    to_version: str,
    exclude_entity: str = "",
    exclude_entities: set[str] | None = None,
) -> None:
    from meshflow.dna.sql_pack import load_sql_pack

    prior = load_sql_pack(settings, pack_id=pack_id, version=from_version)
    if prior is None:
        return
    exclude = {item.strip().lower() for item in (exclude_entities or set()) if str(item).strip()}
    if exclude_entity.strip():
        exclude.add(exclude_entity.strip().lower())
    entities: set[str] = set()
    for transform in prior.transforms:
        if transform.layer != "silver":
            continue
        entity = str(transform.target_entity or "").strip().lower()
        if entity and entity not in exclude:
            entities.add(entity)
    for entity in entities:
        contributions = collect_contributions(
            settings,
            pack_id=pack_id,
            version=from_version,
            target_entity=entity,
        )
        for kpi_id, body in contributions.items():
            write_contribution_sql(
                settings,
                pack_id=pack_id,
                version=to_version,
                target_entity=entity,
                kpi_id=kpi_id,
                sql=body,
            )
