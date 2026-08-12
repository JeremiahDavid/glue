"""KPI Generator — NL draft → Athena validate → approve pinned SQL."""

from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime
from typing import Any

from meshflow.athena import inject_validation_filters, normalize_athena_catalog_refs, run_query
from meshflow.dna.settings import DnaSettings
from meshflow.dna.source_docs_reference import load_source_docs_gold_artifact
from meshflow.dna.sql_pack import build_sql_pack, save_sql_pack
from meshflow.dna.store import list_json_artifact_keys, read_json_artifact, write_json_artifact
from meshflow.dna.web.portal.config_assistant.bedrock_usage import (
    BedrockBudgetExceeded,
    record_usage,
    usage_summary,
)
from meshflow.dna.web.portal.config_assistant.proposals import bump_patch_version
from meshflow.dna.workflow import load_production_pack
from meshflow.dna.workflow import load_workflow_state
from meshflow.storage.paths import governance_pack_prefix

DEFAULT_BEDROCK_MODEL_ID = "us.anthropic.claude-haiku-4-5-20251001-v1:0"

_JSON_FENCE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)


def kpi_generator_proposals_prefix(pack_id: str) -> str:
    return f"{governance_pack_prefix(pack_id)}/kpi_generator/proposals/"


def kpi_generator_proposal_key(pack_id: str, proposal_id: str) -> str:
    pid = proposal_id.strip().lower()
    if not pid or ".." in pid or "/" in pid:
        raise ValueError(f"Invalid proposal id: {proposal_id!r}")
    return f"{governance_pack_prefix(pack_id)}/kpi_generator/proposals/{pid}.json"


def list_fact_options(
    settings: DnaSettings,
    *,
    entity_properties: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Facts for validation dropdowns: pack entities + source-docs tables."""
    facts: list[dict[str, Any]] = []
    seen: set[str] = set()
    try:
        pack = load_production_pack(settings)
        for entity in pack.entities:
            name = str(entity.silver_entity or entity.id).strip()
            if name and name not in seen:
                seen.add(name)
                facts.append({"id": name, "label": name, "source": "pack"})
        for output in pack.outputs:
            oid = str(output.id).strip()
            if oid and oid not in seen:
                seen.add(oid)
                facts.append({"id": oid, "label": oid, "source": "gold_output"})
    except Exception:  # noqa: BLE001
        pass
    props = entity_properties
    if props is None:
        props = load_source_docs_gold_artifact(settings, "entity_properties") or {}
    for table in props.get("tables") or []:
        if not isinstance(table, dict):
            continue
        name = str(table.get("silver_entity") or "").strip()
        if name and name not in seen:
            seen.add(name)
            facts.append({"id": name, "label": name, "source": "source_docs"})
    facts.sort(key=lambda item: item["id"])
    return facts


def build_fields_by_fact(
    settings: DnaSettings,
    *,
    entity_properties: dict[str, Any] | None = None,
) -> dict[str, list[str]]:
    """Map fact id → column names from source-docs gold (single artifact read)."""
    props = entity_properties
    if props is None:
        props = load_source_docs_gold_artifact(settings, "entity_properties") or {}
    fields_by_fact: dict[str, list[str]] = {}
    for table in props.get("tables") or []:
        if not isinstance(table, dict):
            continue
        fact = str(table.get("silver_entity") or "").strip()
        if not fact:
            continue
        names: list[str] = []
        for prop in table.get("properties") or []:
            if isinstance(prop, dict) and prop.get("name"):
                names.append(str(prop["name"]))
        if names:
            fields_by_fact[fact] = names
    return fields_by_fact


def list_fields_for_fact(
    settings: DnaSettings,
    fact_id: str,
    *,
    fields_by_fact: dict[str, list[str]] | None = None,
) -> list[str]:
    fact = (fact_id or "").strip()
    if not fact:
        return []
    if fields_by_fact is not None:
        return list(fields_by_fact.get(fact, []))
    return build_fields_by_fact(settings).get(fact, [])


def _source_docs_context(settings: DnaSettings) -> dict[str, Any]:
    return {
        "entity_properties": load_source_docs_gold_artifact(settings, "entity_properties") or {},
        "entity_relationships": load_source_docs_gold_artifact(settings, "entity_relationships") or {},
        "entity_property_tags": load_source_docs_gold_artifact(settings, "entity_property_tags") or {},
    }


def generate_kpi_proposal(
    settings: DnaSettings,
    *,
    prompt: str,
    client_id: str = "",
    monthly_budget_usd: float | None = None,
    username: str = "",
) -> dict[str, Any]:
    """Call Bedrock once; store ephemeral proposal (not production SQL)."""
    text = (prompt or "").strip()
    if not text:
        raise ValueError("Prompt is required")

    summary = usage_summary(
        settings,
        client_id=client_id,
        monthly_budget_usd=monthly_budget_usd,
    )
    if summary.at_limit:
        raise BedrockBudgetExceeded(
            monthly_budget_usd=summary.monthly_budget_usd,
            estimated_cost_usd=summary.estimated_cost_usd,
            input_tokens=summary.input_tokens,
            output_tokens=summary.output_tokens,
        )

    context = _source_docs_context(settings)
    try:
        pack = load_production_pack(settings)
        pack_summary = {
            "entities": [e.silver_entity for e in pack.entities],
            "outputs": [o.id for o in pack.outputs],
            "kpis": [k.id for k in pack.kpis],
        }
    except Exception:  # noqa: BLE001
        pack_summary = {}

    system = (
        "You are the Meshflow KPI Generator. Using source-docs gold YAML and the DNA pack summary, "
        "draft ONE Athena SQL SELECT for a KPI or fact. Follow layer rules: "
        "column additions → layer silver mode add_columns with target_entity; "
        "new fact tables / KPIs → layer gold mode fact_table or kpi with output_id. "
        "Return ONLY JSON with keys: "
        "layer, mode, id, target_entity, output_id, file, sql, "
        "fields_used (list), filters_applied (list of strings), calculation (string), "
        "summary (string). "
        "file must be a path relative to sql/ with the layer prefix, e.g. "
        "silver/add_col__customers.sql or gold/kpi_net_revenue.sql. "
        "Athena SQL must use Glue table names only (no database prefix): "
        "silver tables as silver_{source}_{entity}, gold outputs as dna_{output_id}. "
        "Do not use silver. or gold. qualifiers."
    )
    user_msg = (
        f"User request:\n{text}\n\n"
        f"DNA pack summary:\n{json.dumps(pack_summary, indent=2)[:6000]}\n\n"
        f"Source docs (truncated):\n{json.dumps(context, indent=2)[:12000]}"
    )

    import boto3

    model_id = __import__("os").environ.get("MESHFLOW_BEDROCK_MODEL_ID", DEFAULT_BEDROCK_MODEL_ID)
    client = boto3.client("bedrock-runtime")
    response = client.converse(
        modelId=model_id,
        system=[{"text": system}],
        messages=[{"role": "user", "content": [{"text": user_msg}]}],
        inferenceConfig={"maxTokens": 4096, "temperature": 0.2},
    )
    raw_text = _extract_converse_text(response)
    draft = _parse_json_object(raw_text)
    _normalize_draft_file_path(draft)
    _validate_layer_rules(draft)

    # Record token usage for the shared Bedrock budget meter.
    usage = response.get("usage") or {}
    in_tok = int(usage.get("inputTokens") or 0)
    out_tok = int(usage.get("outputTokens") or 0)
    if in_tok or out_tok:
        record_usage(
            settings,
            input_tokens=in_tok,
            output_tokens=out_tok,
            client_id=client_id,
        )

    proposal_id = uuid.uuid4().hex[:12]
    proposal = {
        "proposal_id": proposal_id,
        "created_at": datetime.now(UTC).isoformat(),
        "username": username,
        "prompt": text,
        "draft": draft,
        "status": "working",
    }
    write_json_artifact(
        settings,
        kpi_generator_proposal_key(settings.dna_config_id, proposal_id),
        proposal,
    )
    return proposal


def load_kpi_proposal(settings: DnaSettings, proposal_id: str) -> dict[str, Any] | None:
    return read_json_artifact(
        settings,
        kpi_generator_proposal_key(settings.dna_config_id, proposal_id),
    )


def list_kpi_pending_drafts(settings: DnaSettings) -> list[dict[str, Any]]:
    """KPI proposals saved as DNA governance drafts awaiting review."""
    prefix = kpi_generator_proposals_prefix(settings.dna_config_id)
    drafts: list[dict[str, Any]] = []
    for key in list_json_artifact_keys(settings, prefix):
        proposal = read_json_artifact(settings, key)
        if not isinstance(proposal, dict):
            continue
        status = str(proposal.get("status") or "").strip().lower()
        if status == "pending_review":
            drafts.append(proposal)
    drafts.sort(key=lambda item: str(item.get("saved_at") or item.get("created_at") or ""), reverse=True)
    return drafts


def _proposal_snapshot(proposal: dict[str, Any]) -> dict[str, Any]:
    """Persist full generator context on the proposal artifact."""
    draft = proposal.get("draft") or {}
    return {
        "proposal_id": proposal.get("proposal_id"),
        "prompt": proposal.get("prompt"),
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

    draft = proposal.get("draft") or {}
    sql = str(draft.get("sql") or "")
    if not sql.strip():
        raise ValueError("Proposal has no SQL")
    _validate_layer_rules(draft)

    workflow = load_workflow_state(settings, settings.dna_config_id)
    base_pack = load_production_pack(settings)
    active_version = str(workflow.get("active_version") or base_pack.version)
    existing_governance_version = str(proposal.get("governance_version") or "").strip()

    if pin_production and status == "pending_review" and existing_governance_version:
        next_version = existing_governance_version
    elif not pin_production and status == "pending_review" and existing_governance_version:
        next_version = existing_governance_version
    else:
        next_version = bump_patch_version(active_version)

    layer = str(draft.get("layer") or "").strip().lower()
    mode = str(draft.get("mode") or "").strip().lower()
    tid = str(draft.get("id") or f"kpi_{proposal_id}").strip()
    file_rel = _normalize_sql_file_path(
        layer,
        str(draft.get("file") or ""),
        tid,
    )

    transform: dict[str, Any] = {
        "id": tid,
        "layer": layer,
        "mode": mode,
        "file": file_rel,
        "description": str(draft.get("summary") or draft.get("calculation") or ""),
    }
    if layer == "silver":
        transform["target_entity"] = str(draft.get("target_entity") or "").strip()
    else:
        transform["output_id"] = str(draft.get("output_id") or tid).strip()

    from meshflow.dna.sql_pack import load_sql_pack, load_transform_sql

    if existing_governance_version and status == "pending_review":
        merge_from = load_sql_pack(settings, version=existing_governance_version)
    else:
        merge_from = load_sql_pack(settings)

    sql_by_file: dict[str, str] = {file_rel: sql}
    transforms: list[dict[str, Any]] = []
    if merge_from:
        for t in merge_from.transforms:
            if t.id == tid:
                continue
            body = load_transform_sql(
                settings,
                t,
                version=merge_from.version,
                verify_checksum=True,
            )
            sql_by_file[t.file] = body
            transforms.append(t.to_dict())
    transforms.append(transform)

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
    proposal["governance_snapshot"] = _proposal_snapshot(proposal)
    proposal["governance_version"] = next_version
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
    return {
        "status": "approved" if pin_production else "pending_review",
        "version": next_version,
        "proposal_id": proposal_id,
        "sql_file": file_rel,
        "transform_id": tid,
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
    sql: str,
) -> dict[str, Any]:
    """Persist edited SQL on the working proposal draft."""
    proposal = load_kpi_proposal(settings, proposal_id)
    if not proposal:
        raise FileNotFoundError(f"Unknown proposal {proposal_id}")
    draft = dict(proposal.get("draft") or {})
    draft["sql"] = sql.strip()
    _validate_layer_rules(draft)
    proposal["draft"] = draft
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
    draft = proposal.get("draft") or {}
    sql = str(draft.get("sql") or "").strip()
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


def approve_kpi_proposal(
    settings: DnaSettings,
    *,
    proposal_id: str,
    username: str = "",
) -> dict[str, Any]:
    """Pin KPI SQL into production governance at the draft or next patch version."""
    return _persist_kpi_to_governance(
        settings,
        proposal_id=proposal_id,
        username=username,
        pin_production=True,
    )


def reject_kpi_proposal(
    settings: DnaSettings,
    *,
    proposal_id: str,
    username: str = "",
) -> dict[str, Any]:
    proposal = load_kpi_proposal(settings, proposal_id)
    if not proposal:
        raise FileNotFoundError(f"Unknown proposal {proposal_id}")
    if str(proposal.get("status") or "").strip().lower() != "pending_review":
        raise ValueError(f"Proposal {proposal_id} is not pending review")
    proposal["status"] = "rejected"
    proposal["rejected_at"] = datetime.now(UTC).isoformat()
    proposal["rejected_by"] = username
    write_json_artifact(
        settings,
        kpi_generator_proposal_key(settings.dna_config_id, proposal_id),
        proposal,
    )
    return {"status": "rejected", "proposal_id": proposal_id}


def approve_all_kpi_drafts(
    settings: DnaSettings,
    *,
    username: str = "",
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for proposal in list_kpi_pending_drafts(settings):
        pid = str(proposal.get("proposal_id") or "").strip()
        if not pid:
            continue
        results.append(
            approve_kpi_proposal(settings, proposal_id=pid, username=username)
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
        results.append(
            reject_kpi_proposal(settings, proposal_id=pid, username=username)
        )
    return results


def _normalize_sql_file_path(layer: str, file_rel: str, transform_id: str) -> str:
    """Ensure governance SQL paths are relative to sql/ with a layer prefix."""
    layer_norm = str(layer or "").strip().lower()
    if layer_norm not in {"silver", "gold"}:
        raise ValueError("layer must be silver or gold")
    tid = str(transform_id or "").strip() or "transform"
    rel = str(file_rel or "").strip().replace("\\", "/")
    for prefix in ("silver/", "gold/"):
        if rel.startswith(prefix):
            rel = rel[len(prefix) :]
            break
    if not rel:
        rel = f"{tid}.sql"
    elif not rel.endswith(".sql"):
        rel = f"{rel}.sql"
    return f"{layer_norm}/{rel}"


def _normalize_draft_file_path(draft: dict[str, Any]) -> None:
    layer = str(draft.get("layer") or "").strip().lower()
    if layer not in {"silver", "gold"}:
        return
    tid = str(draft.get("id") or "transform").strip() or "transform"
    draft["file"] = _normalize_sql_file_path(layer, str(draft.get("file") or ""), tid)


def _validate_layer_rules(draft: dict[str, Any]) -> None:
    layer = str(draft.get("layer") or "").strip().lower()
    mode = str(draft.get("mode") or "").strip().lower()
    if layer == "silver":
        if mode != "add_columns":
            raise ValueError("Silver transforms must use mode=add_columns")
        if not str(draft.get("target_entity") or "").strip():
            raise ValueError("Silver transforms require target_entity")
    elif layer == "gold":
        if mode not in {"fact_table", "kpi"}:
            raise ValueError("Gold transforms must use mode=fact_table or kpi")
        if not str(draft.get("output_id") or draft.get("id") or "").strip():
            raise ValueError("Gold transforms require output_id")
    else:
        raise ValueError("layer must be silver or gold")
    if not str(draft.get("sql") or "").strip():
        raise ValueError("sql is required")


def _extract_converse_text(response: dict[str, Any]) -> str:
    parts: list[str] = []
    for block in ((response.get("output") or {}).get("message") or {}).get("content") or []:
        if isinstance(block, dict) and block.get("text"):
            parts.append(str(block["text"]))
    return "\n".join(parts).strip()


def _parse_json_object(text: str) -> dict[str, Any]:
    raw = text.strip()
    match = _JSON_FENCE.search(raw)
    if match:
        raw = match.group(1).strip()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("Model did not return JSON") from None
        payload = json.loads(raw[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError("Model JSON must be an object")
    return payload
