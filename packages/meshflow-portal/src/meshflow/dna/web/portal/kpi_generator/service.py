"""KPI Generator — NL draft → Athena validate → approve pinned SQL."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from meshflow.compat import UTC
from typing import Any

from meshflow.athena import inject_validation_filters, normalize_athena_catalog_refs, run_query
from meshflow.dna.settings import DnaSettings
from meshflow.dna.source_docs.reference import (
    load_source_docs_gold_artifact,
    normalize_reference_source,
)
from meshflow.dna.sql_pack import build_sql_pack, save_sql_pack
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
from meshflow.dna.store import list_json_artifact_keys, read_json_artifact, write_json_artifact
from meshflow.dna.web.portal.governance_helpers.bedrock_usage import (
    BedrockBudgetExceeded,
    record_usage,
    usage_summary,
)
from meshflow.dna.web.portal.governance_helpers.proposals import (
    bump_patch_version,
    classify_manual_version_bump,
)
from meshflow.dna.workflow import load_production_pack
from meshflow.dna.workflow import load_workflow_state
from meshflow.storage.paths import governance_pack_prefix
from meshflow.dna.web.portal.kpi_generator.merge import merge_silver_enhancement
from meshflow.dna.web.portal.kpi_generator.sql_format import format_kpi_sql

DEFAULT_BEDROCK_MODEL_ID = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
MAX_KPI_CHAT_TURNS = 5

_JSON_FENCE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)
_FROM_TABLE_RE = re.compile(
    r"\bFROM\s+([\w]+)(?:\s+(?:AS\s+)?([\w]+))?",
    re.IGNORECASE,
)
_JOIN_ON_RE = re.compile(
    r"\b(?:(?:INNER|LEFT(?:\s+OUTER)?|RIGHT(?:\s+OUTER)?|FULL(?:\s+OUTER)?|CROSS)\s+)?JOIN\s+"
    r"([\w]+)(?:\s+(?:AS\s+)?([\w]+))?\s+ON\s+"
    r"(.+?)(?=\s+(?:(?:INNER|LEFT|RIGHT|FULL|CROSS)\s+)?JOIN\b|\s+WHERE\b|\s+GROUP\b|\s+ORDER\b|\s+HAVING\b|$)",
    re.IGNORECASE | re.DOTALL,
)
_GROUP_BY_RE = re.compile(
    r"\bGROUP\s+BY\s+(.*?)(?=\s+(?:ORDER\s+BY|HAVING|LIMIT|OFFSET)\b|$)",
    re.IGNORECASE | re.DOTALL,
)
_QUALIFIED_COL_RE = re.compile(r"\b(\w+)\.(\w+)\b")


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


def _is_reconciled_properties(props: dict[str, Any]) -> bool:
    merged = props.get("merged_from") or {}
    return isinstance(merged, dict) and bool(merged.get("silver_profile"))


def _property_silver_columns(table: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for prop in table.get("properties") or []:
        if not isinstance(prop, dict):
            continue
        if prop.get("in_silver") is False:
            continue
        column = str(prop.get("silver_column") or prop.get("name") or "").strip()
        if column:
            names.append(column)
    return names


def build_fields_by_fact(
    settings: DnaSettings,
    *,
    entity_properties: dict[str, Any] | None = None,
) -> dict[str, list[str]]:
    """Map fact id → silver column names (reconciled gold, else live parquet)."""
    props = entity_properties
    if props is None:
        props = load_source_docs_gold_artifact(settings, "entity_properties") or {}
    fields_by_fact: dict[str, list[str]] = {}
    if _is_reconciled_properties(props):
        for table in props.get("tables") or []:
            if not isinstance(table, dict):
                continue
            fact = str(table.get("silver_entity") or "").strip()
            columns = _property_silver_columns(table)
            if fact and columns:
                fields_by_fact[fact] = columns
        return fields_by_fact

    connector = normalize_reference_source(settings.source)
    prefix = f"silver_{connector}_"
    for table_name, columns in build_columns_by_table(settings, entity_properties=props).items():
        if not table_name.lower().startswith(prefix):
            continue
        entity = table_name[len(prefix):].strip().lower()
        if entity and columns:
            fields_by_fact[entity] = columns

    for table in props.get("tables") or []:
        if not isinstance(table, dict):
            continue
        fact = str(table.get("silver_entity") or "").strip()
        if not fact or fact in fields_by_fact:
            continue
        names = _property_silver_columns(table)
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


def build_columns_by_table(
    settings: DnaSettings,
    *,
    entity_properties: dict[str, Any] | None = None,
) -> dict[str, list[str]]:
    """Glue-style table name → silver column names (reconciled gold, else parquet)."""
    from meshflow.dna.field_semantics import discover_silver_columns, list_silver_entities

    connector = normalize_reference_source(settings.source)
    props = entity_properties
    if props is None:
        props = load_source_docs_gold_artifact(settings, "entity_properties") or {}

    by_table: dict[str, list[str]] = {}
    if _is_reconciled_properties(props):
        for table in props.get("tables") or []:
            if not isinstance(table, dict):
                continue
            entity = str(table.get("silver_entity") or "").strip().lower()
            if not entity:
                continue
            columns = _property_silver_columns(table)
            if columns:
                by_table[_silver_table_name(connector, entity)] = columns
        return by_table

    for entity in list_silver_entities(settings):
        entity_name = entity.strip().lower()
        if not entity_name:
            continue
        columns = discover_silver_columns(settings, entity_name)
        if columns:
            by_table[_silver_table_name(connector, entity_name)] = columns

    for table in props.get("tables") or []:
        if not isinstance(table, dict):
            continue
        entity = str(table.get("silver_entity") or "").strip().lower()
        if not entity:
            continue
        table_name = _silver_table_name(connector, entity)
        if by_table.get(table_name):
            continue
        names = _property_silver_columns(table)
        if names:
            by_table[table_name] = names
    return by_table


def format_silver_columns_for_prompt(
    columns_by_table: dict[str, list[str]],
    *,
    priority_tables: set[str] | None = None,
    max_chars: int = 8000,
) -> str:
    if not columns_by_table:
        return "No silver column catalog available (ingest/consolidate or publish source docs)."

    priority = {name.lower() for name in (priority_tables or set())}
    ordered = sorted(
        columns_by_table.items(),
        key=lambda item: (0 if item[0].lower() in priority else 1, item[0]),
    )
    lines: list[str] = []
    used = 0
    for table_name, columns in ordered:
        cols = ", ".join(columns)
        line = f"- {table_name}: {cols}"
        if used and used + len(line) + 1 > max_chars:
            lines.append("- … (truncated)")
            break
        lines.append(line)
        used += len(line) + 1
    return "\n".join(lines)


def _source_docs_context(settings: DnaSettings) -> dict[str, Any]:
    return {
        "entity_properties": load_source_docs_gold_artifact(settings, "entity_properties") or {},
        "entity_relationships": load_source_docs_gold_artifact(settings, "entity_relationships") or {},
        "entity_property_tags": load_source_docs_gold_artifact(settings, "entity_property_tags") or {},
    }


def _silver_table_name(source: str, entity: str) -> str:
    return f"silver_{normalize_reference_source(source)}_{entity}"


def build_allowed_joins(
    relationships: dict[str, Any],
    *,
    source: str,
) -> list[dict[str, str]]:
    """Allowed silver-table joins from client gold entity_relationships.yaml."""
    connector = normalize_reference_source(source or relationships.get("source") or "")
    tables = relationships.get("tables") or {}
    if not isinstance(tables, dict):
        return []
    allowed: list[dict[str, str]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for from_entity, table in tables.items():
        if not isinstance(table, dict):
            continue
        from_entity = str(from_entity).strip()
        if not from_entity:
            continue
        default_pk = str(table.get("silver_PK") or table.get("PK") or "id").strip() or "id"
        for rel in table.get("relationships") or []:
            if not isinstance(rel, dict):
                continue
            to_entity = str(rel.get("target") or "").strip()
            fk = str(rel.get("silver_FK") or rel.get("FK") or "").strip()
            to_pk = str(rel.get("silver_PK") or rel.get("PK") or default_pk).strip() or "id"
            if rel.get("fk_in_silver") is False or rel.get("pk_in_silver") is False:
                continue
            if rel.get("target_in_silver") is False:
                continue
            if not to_entity or not fk:
                continue
            for left_ent, right_ent, left_col, right_col in (
                (from_entity, to_entity, fk, to_pk),
                (to_entity, from_entity, to_pk, fk),
            ):
                key = (left_ent, right_ent, left_col, right_col)
                if key in seen:
                    continue
                seen.add(key)
                allowed.append(
                    {
                        "left_entity": left_ent,
                        "right_entity": right_ent,
                        "left_table": _silver_table_name(connector, left_ent),
                        "right_table": _silver_table_name(connector, right_ent),
                        "left_column": left_col,
                        "right_column": right_col,
                    }
                )
    return allowed


def format_allowed_joins_for_prompt(allowed_joins: list[dict[str, str]]) -> str:
    if not allowed_joins:
        return "No relationships defined in gold entity_relationships.yaml."
    lines: list[str] = []
    emitted: set[tuple[str, str, str, str]] = set()
    for join in allowed_joins:
        key = (
            join["left_entity"],
            join["right_entity"],
            join["left_column"],
            join["right_column"],
        )
        reverse = (
            join["right_entity"],
            join["left_entity"],
            join["right_column"],
            join["left_column"],
        )
        if key in emitted or reverse in emitted:
            continue
        emitted.add(key)
        lines.append(
            f"- {join['left_entity']}.{join['left_column']} = "
            f"{join['right_entity']}.{join['right_column']} "
            f"({join['left_table']} JOIN {join['right_table']})"
        )
    return "\n".join(lines)


def _column_lookup(columns_by_table: dict[str, list[str]]) -> dict[str, set[str]]:
    return {
        table.lower(): {column.lower() for column in columns}
        for table, columns in columns_by_table.items()
    }


def _check_table_column(
    table: str,
    column: str,
    col_lookup: dict[str, set[str]],
) -> None:
    known = col_lookup.get(table.lower())
    if not known:
        return
    if column.lower() not in known:
        sample = ", ".join(sorted(col_lookup[table.lower()])[:12])
        raise ValueError(
            f"Column {table}.{column} is not in the silver catalog. "
            f"Known columns for {table}: {sample}"
            + (" …" if len(known) > 12 else "")
        )


def _from_base_table(sql: str) -> tuple[str, str] | None:
    match = _FROM_TABLE_RE.search(sql)
    if not match:
        return None
    table = str(match.group(1) or "").strip()
    alias = str(match.group(2) or table).strip()
    if not table:
        return None
    return table.lower(), alias.lower()


def _validate_sql_columns(
    settings: DnaSettings,
    sql: str,
    *,
    columns_by_table: dict[str, list[str]] | None = None,
) -> None:
    """Reject GROUP BY / JOIN keys that reference columns missing from silver."""
    if columns_by_table is None:
        columns_by_table = build_columns_by_table(settings)
    if not columns_by_table:
        return

    text = sql.strip()
    if not text:
        return

    col_lookup = _column_lookup(columns_by_table)
    aliases = _table_aliases(text)

    for match in _JOIN_ON_RE.finditer(text):
        on_clause = str(match.group(3) or "")
        for ref, column in _QUALIFIED_COL_RE.findall(on_clause):
            table = aliases.get(ref.lower())
            if table and _is_client_silver_table(table, settings.source):
                _check_table_column(table, column, col_lookup)

    group_match = _GROUP_BY_RE.search(text)
    if not group_match:
        return

    clause = str(group_match.group(1) or "")
    for ref, column in _QUALIFIED_COL_RE.findall(clause):
        table = aliases.get(ref.lower())
        if table and _is_client_silver_table(table, settings.source):
            _check_table_column(table, column, col_lookup)

    base = _from_base_table(text)
    if not base:
        return
    base_table, base_alias = base
    for raw_expr in clause.split(","):
        expr = raw_expr.strip()
        if not expr or "." in expr or "(" in expr:
            continue
        if not re.fullmatch(r"\w+", expr):
            continue
        if base_table in col_lookup and _is_client_silver_table(base_table, settings.source):
            _check_table_column(base_table, expr, col_lookup)
        elif base_alias in aliases:
            resolved = aliases[base_alias]
            if _is_client_silver_table(resolved, settings.source):
                _check_table_column(resolved, expr, col_lookup)


def _table_aliases(sql: str) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for match in _FROM_TABLE_RE.finditer(sql):
        table = str(match.group(1) or "").strip()
        alias = str(match.group(2) or table).strip()
        if table:
            aliases[table.lower()] = table.lower()
        if alias:
            aliases[alias.lower()] = table.lower()
    for match in _JOIN_ON_RE.finditer(sql):
        table = str(match.group(1) or "").strip()
        alias = str(match.group(2) or table).strip()
        if table:
            aliases[table.lower()] = table.lower()
        if alias:
            aliases[alias.lower()] = table.lower()
    return aliases


def _resolve_join_predicate(
    on_clause: str,
    aliases: dict[str, str],
) -> tuple[str, str, str, str] | None:
    eq_match = re.search(
        r"(\w+)\.(\w+)\s*=\s*(\w+)\.(\w+)",
        on_clause,
        re.IGNORECASE,
    )
    if not eq_match:
        return None
    left_ref, left_col, right_ref, right_col = eq_match.groups()
    left_table = aliases.get(left_ref.lower())
    right_table = aliases.get(right_ref.lower())
    if not left_table or not right_table:
        return None
    return left_table, left_col.lower(), right_table, right_col.lower()


def _is_client_silver_table(table: str, source: str) -> bool:
    prefix = f"silver_{normalize_reference_source(source)}_"
    return table.lower().startswith(prefix)


def _join_matches_allowed(
    predicate: tuple[str, str, str, str],
    allowed_joins: list[dict[str, str]],
) -> bool:
    left_table, left_col, right_table, right_col = predicate
    for join in allowed_joins:
        if (
            join["left_table"].lower() == left_table
            and join["right_table"].lower() == right_table
            and join["left_column"].lower() == left_col
            and join["right_column"].lower() == right_col
        ):
            return True
    return False


def _validate_sql_joins(
    settings: DnaSettings,
    sql: str,
    *,
    relationships: dict[str, Any] | None = None,
) -> None:
    text = sql.strip()
    if not text or not re.search(r"\bjoin\b", text, re.IGNORECASE):
        return
    rels = relationships
    if rels is None:
        rels = load_source_docs_gold_artifact(settings, "entity_relationships") or {}
    allowed = build_allowed_joins(rels, source=settings.source)
    if not allowed:
        raise ValueError(
            "SQL contains JOINs but no entity relationships are defined in gold YAML"
        )
    aliases = _table_aliases(text)
    joins = list(_JOIN_ON_RE.finditer(text))
    if not joins:
        raise ValueError("SQL contains JOIN keyword but no valid JOIN ... ON clause was found")
    for match in joins:
        on_clause = str(match.group(3) or "").strip()
        predicate = _resolve_join_predicate(on_clause, aliases)
        if predicate is None:
            raise ValueError(f"Could not parse JOIN ON clause: {on_clause[:120]}")
        left_table, left_col, right_table, right_col = predicate
        if not (
            _is_client_silver_table(left_table, settings.source)
            and _is_client_silver_table(right_table, settings.source)
        ):
            continue
        if not _join_matches_allowed(predicate, allowed):
            raise ValueError(
                "SQL uses a JOIN that is not defined in gold entity_relationships.yaml: "
                f"{left_table}.{left_col} = {right_table}.{right_col}"
            )


def _assistant_text_from_draft(draft: dict[str, Any]) -> str:
    text = str(draft.get("summary") or draft.get("calculation") or "").strip()
    return text or "Draft KPI SQL is ready — review the proposal below."


def _trim_kpi_chat_history(history: list[dict[str, str]]) -> list[dict[str, str]]:
    """Keep at most MAX_KPI_CHAT_TURNS user messages and their assistant replies."""
    if not history:
        return []
    user_indices = [
        index for index, entry in enumerate(history) if str(entry.get("role") or "") == "user"
    ]
    if len(user_indices) <= MAX_KPI_CHAT_TURNS:
        return history
    return history[user_indices[-MAX_KPI_CHAT_TURNS] :]


def _build_kpi_chat_messages(
    chat_history: list[dict[str, str]],
    *,
    prompt: str,
) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    for entry in chat_history:
        role = str(entry.get("role") or "").strip().lower()
        text = str(entry.get("text") or "").strip()
        if role not in {"user", "assistant"} or not text:
            continue
        messages.append({"role": role, "content": [{"text": text}]})
    messages.append({"role": "user", "content": [{"text": prompt}]})
    return messages


def generate_kpi_proposal(
    settings: DnaSettings,
    *,
    prompt: str,
    client_id: str = "",
    monthly_budget_usd: float | None = None,
    username: str = "",
    prior_chat_history: list[dict[str, str]] | None = None,
    prior_validation_criteria: dict[str, Any] | None = None,
    prior_proposal_id: str = "",
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
    entity_properties = context.get("entity_properties") or {}
    relationships = context.get("entity_relationships") or {}
    allowed_joins = build_allowed_joins(relationships, source=settings.source)
    allowed_joins_text = format_allowed_joins_for_prompt(allowed_joins)
    columns_by_table = build_columns_by_table(settings, entity_properties=entity_properties)
    priority_tables = {join["left_table"] for join in allowed_joins}
    priority_tables.update(join["right_table"] for join in allowed_joins)
    silver_columns_text = format_silver_columns_for_prompt(
        columns_by_table,
        priority_tables=priority_tables,
    )
    pack = None
    try:
        pack = load_production_pack(settings)
        pack_summary = {
            "entities": [e.silver_entity for e in pack.entities],
            "outputs": [o.id for o in pack.outputs],
            "kpis": [k.id for k in pack.kpis],
        }
        for entity in pack.entities:
            name = str(entity.silver_entity or "").strip().lower()
            if name:
                priority_tables.add(
                    _silver_table_name(normalize_reference_source(settings.source), name)
                )
    except Exception:  # noqa: BLE001
        pack_summary = {}

    system = (
        "You are the Meshflow KPI Generator. Using live silver column catalogs, "
        "source-docs gold YAML, and the DNA pack summary, "
        "draft ONE Athena SQL SELECT for a KPI or fact. Follow layer rules: "
        "column additions → layer silver mode add_columns with target_entity; "
        "new fact tables / KPIs → layer gold mode fact_table or kpi with output_id. "
        "Silver SQL is a per-KPI contribution: preserve the entity primary-key grain "
        "(no GROUP BY, no SELECT DISTINCT, no top-level aggregates). "
        "If aggregation changes grain, use gold layer instead. "
        "Gold transforms must include grain_columns (list of dimension keys; "
        "empty list = company total). Duplicate gold grains are rejected. "
        "Return ONLY JSON with keys: "
        "layer, mode, id, target_entity, output_id, grain_columns, file, sql, "
        "fields_used (list), filters_applied (list of strings), calculation (string), "
        "summary (string). "
        "file must be a path relative to sql/ with the layer prefix, e.g. "
        "silver/add_col__customers.sql or gold/kpi_net_revenue.sql. "
        "Athena SQL must use Glue table names only (no database prefix): "
        "silver tables as silver_{source}_{entity}, gold outputs as dna_{output_id}. "
        "Do not use silver. or gold. qualifiers. "
        "Column names (strict): use ONLY column names listed under silver_columns below. "
        "MS Learn / source-docs names may differ from silver (e.g. displayName vs customerName). "
        "Never invent columns. "
        "When adding a column from another table via JOIN, prefer correlated subqueries "
        "instead of GROUP BY when each base row maps to one joined row. "
        "Silver contributions must never use GROUP BY. "
        "JOIN rules (strict): use ONLY joins listed in allowed_joins below. "
        "Each JOIN ON must use the exact FK/PK columns shown. "
        "Do not invent join paths, bridge tables, or join keys. "
        "Single-table SELECTs are fine when no join is needed."
        f"\n\nSilver table columns (authoritative for SQL):\n{silver_columns_text}\n\n"
        f"Allowed joins:\n{allowed_joins_text}\n\n"
        f"DNA pack summary:\n{json.dumps(pack_summary, indent=2)[:6000]}\n\n"
        f"Source docs metadata (truncated):\n{json.dumps(context, indent=2)[:8000]}"
    )
    chat_history = _trim_kpi_chat_history(list(prior_chat_history or []))
    if not chat_history:
        user_prompt = f"User request:\n{text}"
    else:
        user_prompt = text
    bedrock_messages = _build_kpi_chat_messages(chat_history, prompt=user_prompt)

    import boto3

    model_id = __import__("os").environ.get("MESHFLOW_BEDROCK_MODEL_ID", DEFAULT_BEDROCK_MODEL_ID)
    client = boto3.client("bedrock-runtime")
    response = client.converse(
        modelId=model_id,
        system=[{"text": system}],
        messages=bedrock_messages,
        inferenceConfig={"maxTokens": 4096, "temperature": 0.2},
    )
    raw_text = _extract_converse_text(response)
    draft = _parse_json_object(raw_text)
    _normalize_draft_file_path(draft)
    _normalize_draft_grain_columns(draft)
    draft["sql"] = format_kpi_sql(str(draft.get("sql") or ""))
    _validate_layer_rules(draft, settings=settings, relationships=relationships, pack=pack)

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

    chat_history = _trim_kpi_chat_history(
        chat_history
        + [
            {"role": "user", "text": text},
            {"role": "assistant", "text": _assistant_text_from_draft(draft)},
        ]
    )
    now = datetime.now(UTC).isoformat()
    proposal_id = ""
    created_at = now
    prior_id = str(prior_proposal_id or "").strip()
    if prior_id:
        prior = load_kpi_proposal(settings, prior_id)
        if prior and str(prior.get("status") or "").strip().lower() == "working":
            proposal_id = prior_id
            created_at = str(prior.get("created_at") or now)
    if not proposal_id:
        proposal_id = uuid.uuid4().hex[:12]
    close_working_kpi_proposals(
        settings,
        username=username,
        keep_id=proposal_id,
    )
    proposal = {
        "proposal_id": proposal_id,
        "created_at": created_at,
        "username": username,
        "prompt": text,
        "chat_history": chat_history,
        "draft": draft,
        "status": "working",
    }
    if prior_validation_criteria:
        proposal["last_validation"] = dict(prior_validation_criteria)
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


def find_working_kpi_proposal(settings: DnaSettings) -> dict[str, Any] | None:
    """Return the most recent working generator session, if any."""
    prefix = kpi_generator_proposals_prefix(settings.dna_config_id)
    latest: dict[str, Any] | None = None
    latest_key = ""
    for key in list_json_artifact_keys(settings, prefix):
        proposal = read_json_artifact(settings, key)
        if not isinstance(proposal, dict):
            continue
        if str(proposal.get("status") or "").strip().lower() != "working":
            continue
        sort_key = str(proposal.get("created_at") or "")
        if latest is None or sort_key >= latest_key:
            latest = proposal
            latest_key = sort_key
    return latest


def close_working_kpi_proposals(
    settings: DnaSettings,
    *,
    username: str = "",
    keep_id: str = "",
) -> list[str]:
    """Discard working generator sessions so compose can reset.

    ``keep_id`` leaves one in-progress session open (used when continuing a chat).
    """
    keep = str(keep_id or "").strip()
    prefix = kpi_generator_proposals_prefix(settings.dna_config_id)
    now = datetime.now(UTC).isoformat()
    closed: list[str] = []
    for key in list_json_artifact_keys(settings, prefix):
        proposal = read_json_artifact(settings, key)
        if not isinstance(proposal, dict):
            continue
        if str(proposal.get("status") or "").strip().lower() != "working":
            continue
        pid = str(proposal.get("proposal_id") or "").strip()
        if keep and pid == keep:
            continue
        proposal["status"] = "discarded"
        proposal["discarded_at"] = now
        proposal["discarded_by"] = username
        write_json_artifact(settings, key, proposal)
        if pid:
            closed.append(pid)
    return closed


def parse_validation_filters(
    facts: list[str],
    fields: list[str],
    values: list[str],
) -> list[dict[str, str]]:
    filters: list[dict[str, str]] = []
    for fact, field, value in zip(facts, fields, values, strict=False):
        field_text = str(field).strip()
        value_text = str(value).strip()
        if field_text and value_text:
            filters.append(
                {
                    "fact": str(fact).strip(),
                    "field": field_text,
                    "value": value_text,
                }
            )
    return filters


def validation_criteria_from_proposal(
    proposal: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Extract persisted validation filters from a working proposal."""
    if not proposal:
        return None
    last_val = proposal.get("last_validation")
    if not isinstance(last_val, dict):
        return None
    filters = last_val.get("filters") or []
    if not filters:
        return None
    return {"filters": list(filters)}


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


def list_kpi_approved_drafts(settings: DnaSettings) -> list[dict[str, Any]]:
    """Approved KPI proposals waiting to be published."""
    prefix = kpi_generator_proposals_prefix(settings.dna_config_id)
    drafts: list[dict[str, Any]] = []
    for key in list_json_artifact_keys(settings, prefix):
        proposal = read_json_artifact(settings, key)
        if not isinstance(proposal, dict):
            continue
        if str(proposal.get("status") or "").strip().lower() == "approved":
            drafts.append(proposal)
    drafts.sort(key=lambda item: str(item.get("saved_at") or item.get("created_at") or ""), reverse=True)
    return drafts


def list_kpi_review_tab_drafts(settings: DnaSettings) -> list[dict[str, Any]]:
    """Pending + approved proposals shown on the Review Drafts tab badge."""
    return list_kpi_pending_drafts(settings) + list_kpi_approved_drafts(settings)


def _proposal_snapshot(proposal: dict[str, Any]) -> dict[str, Any]:
    """Persist full generator context on the proposal artifact."""
    draft = proposal.get("draft") or {}
    return {
        "proposal_id": proposal.get("proposal_id"),
        "prompt": proposal.get("prompt"),
        "chat_history": list(proposal.get("chat_history") or []),
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

    draft = proposal.get("draft") or {}
    sql = str(draft.get("sql") or "")
    if not sql.strip():
        raise ValueError("Proposal has no SQL")
    workflow = load_workflow_state(settings, settings.dna_config_id)
    base_pack = load_production_pack(settings)
    _validate_layer_rules(draft, settings=settings, pack=base_pack)

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

    layer = str(draft.get("layer") or "").strip().lower()
    mode = str(draft.get("mode") or "").strip().lower()
    tid = str(draft.get("id") or f"kpi_{proposal_id}").strip()

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

    transforms: list[dict[str, Any]] = []
    sql_by_file: dict[str, str] = {}
    merged_sql_preview = ""
    sibling_proposals: list[dict[str, Any]] = []

    if layer == "silver":
        target_entity = str(draft.get("target_entity") or "").strip()
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
        contributions[_normalize_contribution_id(tid)] = sql

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

        if merge_from:
            for t in merge_from.transforms:
                if t.layer == "gold":
                    body = load_transform_sql(
                        settings,
                        t,
                        version=merge_from.version,
                        verify_checksum=True,
                    )
                    sql_by_file[t.file] = body
                    transforms.append(t.to_dict())
                elif (
                    t.layer == "silver"
                    and str(t.target_entity or "").strip().lower() != target_entity.lower()
                ):
                    body = load_transform_sql(
                        settings,
                        t,
                        version=merge_from.version,
                        verify_checksum=True,
                    )
                    sql_by_file[t.file] = body
                    transforms.append(t.to_dict())

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
            target_entity, _normalize_contribution_id(tid)
        )
    else:
        file_rel = _normalize_sql_file_path(
            layer,
            str(draft.get("file") or ""),
            tid,
        )
        output_id = str(draft.get("output_id") or tid).strip()
        grain_columns = validate_gold_grain_columns(draft.get("grain_columns"))
        existing_transforms: list[dict[str, Any]] = []
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
                entry = t.to_dict()
                existing_transforms.append(entry)
                transforms.append(entry)
        assert_unique_gold_grain(
            existing_transforms,
            output_id=output_id,
            grain_columns=grain_columns,
        )
        sql_by_file[file_rel] = sql
        transforms.append(
            {
                "id": tid,
                "layer": layer,
                "mode": mode,
                "file": file_rel,
                "output_id": output_id,
                "grain_columns": grain_columns,
                "description": str(draft.get("summary") or draft.get("calculation") or ""),
            }
        )

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
    sql: str,
) -> dict[str, Any]:
    """Persist edited SQL on the working proposal draft."""
    proposal = load_kpi_proposal(settings, proposal_id)
    if not proposal:
        raise FileNotFoundError(f"Unknown proposal {proposal_id}")
    draft = dict(proposal.get("draft") or {})
    draft["sql"] = format_kpi_sql(sql)
    _normalize_draft_grain_columns(draft)
    _validate_layer_rules(
        draft,
        settings=settings,
        pack=load_production_pack(settings),
    )
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
    silver_monthly_limit: int | None = None,
    gold_monthly_limit: int | None = None,
) -> dict[str, Any]:
    """Trigger silver or gold refresh for approved KPIs and mark them published."""
    from meshflow.dna.web.portal.dna_manual_refresh import trigger_manual_refresh
    from meshflow.dna.web.portal.kpi_generator.integrity import load_proposals_by_ids
    from meshflow.dna.web.portal.silver_manual_refresh import trigger_manual_silver_refresh
    from meshflow.dna.workflow import load_workflow_state

    proposals = load_proposals_by_ids(settings, proposal_ids)
    if not proposals:
        raise ValueError(f"No proposals to publish for {target_key!r}")

    layer, _, _ = target_key.partition(":")
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
    if layer == "silver":
        result = trigger_manual_silver_refresh(
            settings,
            client_id=client_id,
            username=username,
            pinned_version=pinned_version,
            company=resolved_company,
            environment=environment,
            monthly_limit=silver_monthly_limit,
        )
        refresh_kind = "silver"
    else:
        result = trigger_manual_refresh(
            settings,
            client_id=client_id,
            username=username,
            pinned_version=pinned_version,
            company=resolved_company,
            environment=environment,
            monthly_limit=gold_monthly_limit,
        )
        refresh_kind = "gold"

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
    silver_monthly_limit: int | None = None,
    gold_monthly_limit: int | None = None,
) -> dict[str, Any]:
    """Publish every approved KPI by running silver and/or gold refresh."""
    from meshflow.dna.web.portal.dna_manual_refresh import trigger_manual_refresh
    from meshflow.dna.web.portal.silver_manual_refresh import trigger_manual_silver_refresh
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
    needs_silver = any(
        str((proposal.get("draft") or {}).get("layer") or "").strip().lower() == "silver"
        for proposal in proposals
    )
    needs_gold = any(
        str((proposal.get("draft") or {}).get("layer") or "").strip().lower() == "gold"
        for proposal in proposals
    )

    refreshes: list[dict[str, Any]] = []
    if needs_silver:
        refreshes.append(
            {
                "kind": "silver",
                "result": trigger_manual_silver_refresh(
                    settings,
                    client_id=client_id,
                    username=username,
                    pinned_version=pinned_version,
                    company=resolved_company,
                    environment=environment,
                    monthly_limit=silver_monthly_limit,
                ),
            }
        )
    if needs_gold:
        refreshes.append(
            {
                "kind": "gold",
                "result": trigger_manual_refresh(
                    settings,
                    client_id=client_id,
                    username=username,
                    pinned_version=pinned_version,
                    company=resolved_company,
                    environment=environment,
                    monthly_limit=gold_monthly_limit,
                ),
            }
        )

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


def _normalize_draft_grain_columns(draft: dict[str, Any]) -> None:
    layer = str(draft.get("layer") or "").strip().lower()
    if layer != "gold":
        draft.pop("grain_columns", None)
        return
    raw = draft.get("grain_columns")
    if raw is None:
        draft["grain_columns"] = []
        return
    if isinstance(raw, str):
        text = raw.strip()
        draft["grain_columns"] = [text] if text else []
        return
    if isinstance(raw, list):
        draft["grain_columns"] = validate_gold_grain_columns(raw)
        return
    raise ValueError("grain_columns must be a list of column names")


def _entity_primary_key(pack: Any, silver_entity: str) -> str:
    name = silver_entity.strip().lower()
    for entity in getattr(pack, "entities", []) or []:
        if str(getattr(entity, "silver_entity", "") or "").strip().lower() == name:
            return str(getattr(entity, "primary_key", "") or "id").strip() or "id"
    return "id"


def _normalize_contribution_id(kpi_id: str) -> str:
    return kpi_id.strip().lower().replace(" ", "_")


def _proposal_silver_entity(proposal: dict[str, Any]) -> str:
    draft = proposal.get("draft") or {}
    if str(draft.get("layer") or "").strip().lower() != "silver":
        return ""
    return str(draft.get("target_entity") or "").strip().lower()


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
        draft = proposal.get("draft") or {}
        tid = _normalize_contribution_id(
            str(draft.get("id") or proposal.get("proposal_id") or "")
        )
        sql = str(draft.get("sql") or "").strip()
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


def _validate_layer_rules(
    draft: dict[str, Any],
    *,
    settings: DnaSettings | None = None,
    relationships: dict[str, Any] | None = None,
    pack: Any | None = None,
    existing_gold_transforms: list[dict[str, Any]] | None = None,
) -> None:
    layer = str(draft.get("layer") or "").strip().lower()
    mode = str(draft.get("mode") or "").strip().lower()
    if layer == "silver":
        if mode != "add_columns":
            raise ValueError("Silver transforms must use mode=add_columns")
        target_entity = str(draft.get("target_entity") or "").strip()
        if not target_entity:
            raise ValueError("Silver transforms require target_entity")
        if draft.get("grain_columns"):
            raise ValueError("grain_columns is only valid for gold transforms")
    elif layer == "gold":
        if mode not in {"fact_table", "kpi"}:
            raise ValueError("Gold transforms must use mode=fact_table or kpi")
        output_id = str(draft.get("output_id") or draft.get("id") or "").strip()
        if not output_id:
            raise ValueError("Gold transforms require output_id")
        if "grain_columns" not in draft:
            raise ValueError("Gold transforms require grain_columns (use [] for company total)")
        grain_columns = validate_gold_grain_columns(draft.get("grain_columns"))
        draft["grain_columns"] = grain_columns
        if existing_gold_transforms is not None:
            assert_unique_gold_grain(
                existing_gold_transforms,
                output_id=output_id,
                grain_columns=grain_columns,
                exclude_transform_id=str(draft.get("id") or "").strip() or None,
            )
    else:
        raise ValueError("layer must be silver or gold")
    sql = str(draft.get("sql") or "").strip()
    if not sql:
        raise ValueError("sql is required")
    if layer == "silver" and settings is not None:
        primary_key = "id"
        if pack is not None:
            primary_key = _entity_primary_key(pack, str(draft.get("target_entity") or ""))
        assert_preserves_silver_grain(sql, primary_key=primary_key)
    if settings is not None:
        _validate_sql_joins(settings, sql, relationships=relationships)
        _validate_sql_columns(settings, sql)


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
