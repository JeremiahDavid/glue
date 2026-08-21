"""Pre-approval integrity validation for KPI draft groups."""

from __future__ import annotations

from datetime import datetime
from meshflow.compat import UTC
from typing import Any

from meshflow.athena import normalize_athena_catalog_refs, run_query
from meshflow.dna.settings import DnaSettings
from meshflow.dna.silver_integrity import (
    TableFingerprint,
    build_athena_fingerprint_query,
    fingerprint_from_athena_result,
    fingerprint_from_rows,
    load_baseline_fingerprint,
    validate_silver_enhancement_integrity,
)
from meshflow.dna.web.portal.kpi_generator.merge import (
    merge_silver_enhancement,
    repair_silver_enhancement,
)
from meshflow.dna.web.portal.kpi_generator.drafts import (
    find_draft_by_layer,
    inline_silver_contribution_for_gold_sql,
    iter_proposal_drafts,
    primary_draft,
)
from meshflow.dna.web.portal.kpi_generator.catalog import (
    _entity_primary_key,
    _validate_sql_columns,
    _validate_sql_joins,
)
from meshflow.dna.web.portal.kpi_generator.generation import load_kpi_proposal
from meshflow.dna.web.portal.kpi_generator.governance import _collect_silver_contributions
from meshflow.dna.web.portal.kpi_generator.sql_format import format_kpi_sql
from meshflow.dna.workflow import load_production_pack


def draft_target_key(draft: dict[str, Any]) -> str:
    layer = str(draft.get("layer") or "").strip().lower()
    if layer == "silver":
        entity = str(draft.get("target_entity") or "").strip().lower()
        if not entity:
            raise ValueError("Silver draft missing target_entity")
        return f"silver:{entity}"
    output_id = str(draft.get("output_id") or draft.get("id") or "").strip().lower()
    if not output_id:
        raise ValueError("Gold draft missing output_id")
    return f"gold:{output_id}"


def draft_target_label(target_key: str) -> str:
    layer, _, name = target_key.partition(":")
    if layer == "silver":
        return f"Silver entity {name}"
    return f"Gold output {name}"


def group_pending_drafts(proposals: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for proposal in proposals:
        draft = primary_draft(iter_proposal_drafts(proposal))
        try:
            key = draft_target_key(draft)
        except ValueError:
            continue
        groups.setdefault(key, []).append(proposal)
    for key in groups:
        groups[key].sort(
            key=lambda item: str(item.get("saved_at") or item.get("created_at") or "")
        )
    return dict(sorted(groups.items()))


def _athena_targets(
    settings: DnaSettings,
    *,
    company: str | None = None,
    environment: str | None = None,
) -> tuple[str, str]:
    from meshflow.project_config import athena_workgroup_name, glue_database_name, resolve_selection

    resolved_company = (company or settings.company or "").strip()
    resolved_env = (environment or "").strip()
    if not resolved_company or not resolved_env:
        sel_c, sel_e = resolve_selection()
        resolved_company = resolved_company or sel_c
        resolved_env = resolved_env or sel_e
    return (
        glue_database_name(resolved_company, resolved_env),
        athena_workgroup_name(resolved_company, resolved_env),
    )


def _merged_contributions_for_group(
    settings: DnaSettings,
    proposals: list[dict[str, Any]],
    *,
    target_entity: str,
) -> dict[str, str]:
    from meshflow.dna.sql_pack import load_sql_pack

    contributions: dict[str, str] = {}
    governance_versions: set[str] = set()
    for proposal in proposals:
        silver = find_draft_by_layer(proposal, "silver")
        if not silver:
            continue
        entity = str(silver.get("target_entity") or "").strip().lower()
        if entity and entity != target_entity.strip().lower():
            continue
        tid = str(silver.get("id") or proposal.get("proposal_id") or "").strip()
        sql = str(silver.get("sql") or "").strip()
        if tid and sql:
            contributions[tid] = sql
        version = str(proposal.get("governance_version") or "").strip()
        if version:
            governance_versions.add(version)

    merge_version = next(iter(governance_versions), "")
    merge_from = load_sql_pack(settings, version=merge_version) if merge_version else load_sql_pack(settings)
    if merge_from:
        prior = _collect_silver_contributions(
            settings,
            merge_from=merge_from,
            merge_version=merge_from.version,
            pack_id=settings.dna_config_id,
            target_entity=target_entity,
        )
        for kpi_id, body in prior.items():
            contributions.setdefault(kpi_id, body)
    return contributions


def validate_silver_group_integrity(
    settings: DnaSettings,
    *,
    target_entity: str,
    proposals: list[dict[str, Any]],
    company: str | None = None,
    environment: str | None = None,
    region: str | None = None,
    attempt_repair: bool = True,
) -> dict[str, Any]:
    """Merge contributions and verify row count + PK checksum against raw silver baseline."""
    pack = load_production_pack(settings)
    primary_key = _entity_primary_key(pack, target_entity)
    baseline = load_baseline_fingerprint(
        settings,
        source=settings.source,
        entity=target_entity,
    )
    if baseline is None:
        rows = []
        try:
            from meshflow.dna.store import read_silver_stg_entity

            rows = read_silver_stg_entity(settings, target_entity)
        except Exception:  # noqa: BLE001
            rows = []
        if rows:
            baseline = fingerprint_from_rows(rows, primary_key=primary_key)
        else:
            raise ValueError(
                f"No silver_stg baseline for entity {target_entity!r}. "
                "Run connector consolidate before validating enhancements."
            )

    contributions = _merged_contributions_for_group(
        settings,
        proposals,
        target_entity=target_entity,
    )

    def _validate_merged(merged: str) -> None:
        _validate_sql_joins(settings, merged)
        _validate_sql_columns(settings, merged)

    merged_sql = merge_silver_enhancement(
        settings,
        target_entity=target_entity,
        contributions=contributions,
        primary_key=primary_key,
        validate_sql=_validate_merged,
    )

    from meshflow.dna.silver_enhancement import retarget_silver_sql_to_stg

    database, workgroup = _athena_targets(settings, company=company, environment=environment)
    retargeted = retarget_silver_sql_to_stg(merged_sql, source=settings.source or "")
    normalized = normalize_athena_catalog_refs(
        retargeted,
        source=settings.source or "",
        database=database,
    )
    fingerprint_query = build_athena_fingerprint_query(
        normalized,
        primary_key=baseline.primary_key or [primary_key],
    )
    result = run_query(
        fingerprint_query,
        database=database,
        workgroup=workgroup,
        region=region,
        max_rows=1,
    )
    candidate = fingerprint_from_athena_result(result)
    candidate.primary_key = list(baseline.primary_key or [primary_key])
    validation = validate_silver_enhancement_integrity(baseline, candidate)
    validation["merged_sql"] = format_kpi_sql(merged_sql)
    validation["target_entity"] = target_entity
    validation["validated_at"] = datetime.now(UTC).isoformat()
    validation["execution_id"] = result.get("execution_id")

    if validation["status"] == "failed" and attempt_repair:
        repaired = repair_silver_enhancement(
            settings,
            target_entity=target_entity,
            contributions=contributions,
            primary_key=primary_key,
            failure=validation,
        )
        repaired_sql = format_kpi_sql(repaired.get("sql") or "")
        repaired_contributions = dict(contributions)
        repair_id = str(repaired.get("contribution_id") or "merge_repair")
        repaired_contributions[repair_id] = repaired_sql
        validation["repair_attempted"] = True
        validation["repair"] = repaired
        merged_sql = merge_silver_enhancement(
            settings,
            target_entity=target_entity,
            contributions=repaired_contributions,
            primary_key=primary_key,
            validate_sql=_validate_merged,
        )
        retargeted = retarget_silver_sql_to_stg(merged_sql, source=settings.source or "")
        normalized = normalize_athena_catalog_refs(
            retargeted,
            source=settings.source or "",
            database=database,
        )
        fingerprint_query = build_athena_fingerprint_query(
            normalized,
            primary_key=baseline.primary_key or [primary_key],
        )
        result = run_query(
            fingerprint_query,
            database=database,
            workgroup=workgroup,
            region=region,
            max_rows=1,
        )
        candidate = fingerprint_from_athena_result(result)
        candidate.primary_key = list(baseline.primary_key or [primary_key])
        validation = validate_silver_enhancement_integrity(baseline, candidate)
        validation["merged_sql"] = format_kpi_sql(merged_sql)
        validation["target_entity"] = target_entity
        validation["validated_at"] = datetime.now(UTC).isoformat()
        validation["execution_id"] = result.get("execution_id")
        validation["repair_attempted"] = True
        validation["repair"] = repaired
        if validation["status"] == "passed":
            _apply_repair_to_proposals(proposals, repaired, repaired_sql)

    return validation


def _apply_repair_to_proposals(
    proposals: list[dict[str, Any]],
    repair: dict[str, Any],
    repaired_sql: str,
) -> None:
    contribution_id = str(repair.get("contribution_id") or "").strip()
    if not contribution_id:
        return
    for proposal in proposals:
        silver = find_draft_by_layer(proposal, "silver")
        if str((silver or {}).get("id") or "").strip() == contribution_id:
            if silver is not None:
                silver["sql"] = repaired_sql
            drafts = iter_proposal_drafts(proposal)
            proposal["drafts"] = drafts
            proposal["draft"] = proposal.get("draft") or silver
            if str((proposal.get("draft") or {}).get("id") or "").strip() == contribution_id:
                proposal["draft"]["sql"] = repaired_sql
            proposal["integrity_repair"] = repair


def validate_gold_group_integrity(
    settings: DnaSettings,
    *,
    proposals: list[dict[str, Any]],
    company: str | None = None,
    environment: str | None = None,
    region: str | None = None,
) -> dict[str, Any]:
    """Execute each gold draft SQL in Athena (execution gate only)."""
    database, workgroup = _athena_targets(settings, company=company, environment=environment)
    executions: list[dict[str, Any]] = []
    errors: list[str] = []
    for proposal in proposals:
        gold = find_draft_by_layer(proposal, "gold") or proposal.get("draft") or {}
        sql = str(gold.get("sql") or "").strip()
        if not sql:
            errors.append(f"Proposal {proposal.get('proposal_id')}: missing SQL")
            continue
        silver = find_draft_by_layer(proposal, "silver")
        if silver:
            sql = inline_silver_contribution_for_gold_sql(
                sql,
                source=settings.source or "",
                target_entity=str(silver.get("target_entity") or ""),
                contribution_sql=str(silver.get("sql") or ""),
            )
        normalized = normalize_athena_catalog_refs(
            sql,
            source=settings.source or "",
            database=database,
        )
        wrapped = f"SELECT * FROM ({normalized.rstrip(';')}) AS _candidate LIMIT 1"
        try:
            result = run_query(
                wrapped,
                database=database,
                workgroup=workgroup,
                region=region,
                max_rows=1,
            )
            executions.append(
                {
                    "proposal_id": proposal.get("proposal_id"),
                    "execution_id": result.get("execution_id"),
                    "status": "ok",
                }
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Proposal {proposal.get('proposal_id')}: {exc}")
    return {
        "status": "passed" if not errors else "failed",
        "layer": "gold",
        "errors": errors,
        "executions": executions,
        "validated_at": datetime.now(UTC).isoformat(),
    }


def validate_draft_group_integrity(
    settings: DnaSettings,
    *,
    target_key: str,
    proposals: list[dict[str, Any]],
    company: str | None = None,
    environment: str | None = None,
    region: str | None = None,
    attempt_repair: bool = True,
) -> dict[str, Any]:
    layer, _, name = target_key.partition(":")
    silver_entities: list[str] = []
    has_gold = False
    for proposal in proposals:
        silver = find_draft_by_layer(proposal, "silver")
        if silver:
            entity = str(silver.get("target_entity") or "").strip().lower()
            if entity and entity not in silver_entities:
                silver_entities.append(entity)
        if find_draft_by_layer(proposal, "gold") or (
            str((proposal.get("draft") or {}).get("layer") or "").strip().lower() == "gold"
        ):
            has_gold = True
    if layer == "silver" and name and name not in silver_entities:
        silver_entities.append(name)
    if layer == "gold":
        has_gold = True

    errors: list[str] = []
    merged: dict[str, Any] = {
        "status": "passed",
        "target_key": target_key,
        "errors": errors,
        "validated_at": datetime.now(UTC).isoformat(),
    }
    if silver_entities:
        silver_result = None
        for entity in silver_entities:
            silver_result = validate_silver_group_integrity(
                settings,
                target_entity=entity,
                proposals=proposals,
                company=company,
                environment=environment,
                region=region,
                attempt_repair=attempt_repair,
            )
            if str(silver_result.get("status") or "").strip().lower() != "passed":
                errors.extend(silver_result.get("errors") or ["Silver integrity failed"])
            merged["silver"] = silver_result
            if silver_result.get("merged_sql"):
                merged["merged_sql"] = silver_result["merged_sql"]
                merged["target_entity"] = entity
    if has_gold:
        gold_result = validate_gold_group_integrity(
            settings,
            proposals=proposals,
            company=company,
            environment=environment,
            region=region,
        )
        merged["gold"] = gold_result
        if str(gold_result.get("status") or "").strip().lower() != "passed":
            errors.extend(gold_result.get("errors") or ["Gold integrity failed"])
        if gold_result.get("executions"):
            merged["executions"] = gold_result["executions"]
    if not silver_entities and not has_gold:
        raise ValueError(f"Unknown draft group layer: {layer!r}")
    merged["status"] = "passed" if not errors else "failed"
    merged["errors"] = errors
    return merged


def group_integrity_status(proposals: list[dict[str, Any]], *, target_key: str) -> str:
    """Return passed, failed, or not_run for a draft group."""
    for proposal in proposals:
        validation = proposal.get("integrity_validation") or {}
        if not validation:
            continue
        recorded_key = str(
            validation.get("target_key")
            or (
                f"silver:{validation.get('target_entity')}"
                if validation.get("target_entity")
                else ""
            )
            or ""
        ).strip()
        if recorded_key and recorded_key != target_key:
            continue
        return str(validation.get("status") or "not_run").strip().lower()
    return "not_run"


def group_integrity_passed(proposals: list[dict[str, Any]], *, target_key: str) -> bool:
    return group_integrity_status(proposals, target_key=target_key) == "passed"


REVIEW_KANBAN_STAGES = ("integrity", "approve")


def proposal_integrity_status(proposal: dict[str, Any]) -> str:
    validation = proposal.get("integrity_validation") or {}
    if not isinstance(validation, dict):
        return "not_run"
    return str(validation.get("status") or "not_run").strip().lower()


def proposal_integrity_passed(proposal: dict[str, Any]) -> bool:
    return proposal_integrity_status(proposal) == "passed"


def classify_proposal_stage(proposal: dict[str, Any]) -> str:
    """Return kanban pillar for a pending-review proposal: integrity or approve."""
    if str(proposal.get("status") or "").strip().lower() != "pending_review":
        return "approve"
    if proposal_integrity_passed(proposal):
        return "approve"
    return "integrity"


def partition_proposals_by_stage(
    proposals: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Bucket pending-review proposals into integrity / approve kanban pillars."""
    staged: dict[str, list[dict[str, Any]]] = {stage: [] for stage in REVIEW_KANBAN_STAGES}
    for proposal in proposals:
        stage = classify_proposal_stage(proposal)
        staged[stage].append(proposal)
    for stage in REVIEW_KANBAN_STAGES:
        staged[stage].sort(
            key=lambda item: str(item.get("saved_at") or item.get("created_at") or "")
        )
    return staged


def classify_review_group_stage(
    proposals: list[dict[str, Any]],
    *,
    target_key: str,
) -> str:
    """Return kanban stage for a proposal group (legacy helper for group actions)."""
    if not proposals:
        return "integrity"
    if all(str(proposal.get("status") or "").strip().lower() == "pending_review" for proposal in proposals):
        if all(proposal_integrity_passed(proposal) for proposal in proposals):
            return "approve"
        if any(proposal_integrity_passed(proposal) for proposal in proposals):
            return "approve"
        return "integrity"
    return "integrity"


def _group_integrity_validation_record(
    proposals: list[dict[str, Any]],
    *,
    target_key: str,
) -> dict[str, Any]:
    for proposal in proposals:
        validation = proposal.get("integrity_validation") or {}
        if not isinstance(validation, dict) or not validation:
            continue
        recorded_key = str(validation.get("target_key") or "").strip()
        if not recorded_key and validation.get("target_entity"):
            recorded_key = f"silver:{validation.get('target_entity')}"
        if recorded_key and recorded_key != target_key:
            continue
        return validation
    return {}


def persist_group_integrity_validation(
    settings: DnaSettings,
    proposals: list[dict[str, Any]],
    validation: dict[str, Any],
) -> None:
    from meshflow.dna.store import write_json_artifact
    from meshflow.dna.web.portal.kpi_generator.paths import kpi_generator_proposal_key

    for proposal in proposals:
        proposal_id = str(proposal.get("proposal_id") or "").strip()
        if not proposal_id:
            continue
        proposal["integrity_validation"] = validation
        if validation.get("merged_sql"):
            proposal["merged_enhancement_sql"] = validation["merged_sql"]
        write_json_artifact(
            settings,
            kpi_generator_proposal_key(settings.dna_config_id, proposal_id),
            proposal,
        )


def load_proposals_by_ids(
    settings: DnaSettings,
    proposal_ids: list[str],
) -> list[dict[str, Any]]:
    loaded: list[dict[str, Any]] = []
    for proposal_id in proposal_ids:
        proposal = load_kpi_proposal(settings, proposal_id)
        if proposal:
            loaded.append(proposal)
    return loaded
