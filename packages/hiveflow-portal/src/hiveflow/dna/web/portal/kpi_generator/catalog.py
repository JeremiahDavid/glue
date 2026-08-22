"""KPI Generator — silver_stg schema/join catalog resolution and SQL/draft validation."""

from __future__ import annotations

import re
from typing import Any

from hiveflow.dna.settings import DnaSettings
from hiveflow.dna.silver_enhancement import (
    assert_preserves_silver_grain,
    assert_unique_gold_grain,
    extract_new_column_aliases,
    validate_gold_grain_columns,
)
from hiveflow.dna.source_docs.reference import (
    load_source_docs_gold_artifact,
    normalize_reference_source,
)
from hiveflow.dna.web.portal.kpi_generator.sql_format import format_kpi_sql
from hiveflow.dna.workflow import load_production_pack

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


def _register_entity_columns(
    by_table: dict[str, list[str]],
    source: str,
    entity: str,
    columns: list[str],
) -> None:
    entity_name = entity.strip().lower()
    if not entity_name or not columns:
        return
    by_table[_silver_stg_table_name(source, entity_name)] = list(columns)
    by_table[_silver_table_name(source, entity_name)] = list(columns)


def _columns_from_silver_stg_profile(settings: DnaSettings) -> dict[str, list[str]]:
    from hiveflow.dna.source_docs.reference import load_silver_schema_profile

    profile = load_silver_schema_profile(settings) or {}
    if str(profile.get("kind") or "") != "silver_schema_profile":
        return {}
    connector = normalize_reference_source(settings.source)
    by_table: dict[str, list[str]] = {}
    for table in profile.get("tables") or []:
        if not isinstance(table, dict):
            continue
        entity = str(table.get("silver_entity") or "").strip().lower()
        columns = [
            str(col.get("name") or "").strip()
            for col in (table.get("columns") or [])
            if isinstance(col, dict) and str(col.get("name") or "").strip()
        ]
        _register_entity_columns(by_table, connector, entity, columns)
    return by_table


def build_fields_by_fact(
    settings: DnaSettings,
    *,
    entity_properties: dict[str, Any] | None = None,
    parquet_fallback: bool = True,
) -> dict[str, list[str]]:
    """Map fact id → silver_stg column names."""
    props = entity_properties
    if props is None:
        props = load_source_docs_gold_artifact(settings, "entity_properties") or {}
    connector = normalize_reference_source(settings.source)
    stg_prefix = f"silver_stg_{connector}_"
    fields_by_fact: dict[str, list[str]] = {}
    for table_name, columns in build_columns_by_table(
        settings,
        entity_properties=props,
        parquet_fallback=parquet_fallback,
    ).items():
        if not table_name.lower().startswith(stg_prefix):
            continue
        entity = table_name[len(stg_prefix) :].strip().lower()
        if entity and columns:
            fields_by_fact[entity] = columns
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
    parquet_fallback: bool = True,
) -> dict[str, list[str]]:
    """Glue-style table name → silver_stg column names (profile, then parquet)."""
    from hiveflow.dna.field_semantics import (
        discover_silver_columns,
        discover_silver_stg_columns,
        list_lake_silver_entities,
        list_lake_silver_stg_entities,
    )

    connector = normalize_reference_source(settings.source)
    props = entity_properties
    if props is None:
        props = load_source_docs_gold_artifact(settings, "entity_properties") or {}

    by_table = _columns_from_silver_stg_profile(settings)

    if parquet_fallback:
        lake_entities = set(list_lake_silver_stg_entities(settings))
        lake_entities.update(list_lake_silver_entities(settings))
        for entity_name in sorted(lake_entities):
            stg_name = _silver_stg_table_name(connector, entity_name)
            if by_table.get(stg_name):
                continue
            columns = discover_silver_stg_columns(settings, entity_name)
            if not columns:
                columns = discover_silver_columns(settings, entity_name)
            if columns:
                _register_entity_columns(by_table, connector, entity_name, columns)

    for table in props.get("tables") or []:
        if not isinstance(table, dict):
            continue
        entity = str(table.get("silver_entity") or "").strip().lower()
        if not entity:
            continue
        stg_name = _silver_stg_table_name(connector, entity)
        if by_table.get(stg_name):
            continue
        names = _property_silver_columns(table)
        if names:
            _register_entity_columns(by_table, connector, entity, names)
    return by_table


def _prompt_tokens(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(token) > 2}


def _token_matches_blob(token: str, blob: str, parts: set[str]) -> bool:
    if token in blob:
        return True
    if len(token) < 5:
        return False
    for part in parts:
        if abs(len(part) - len(token)) > 1 or len(part) < 5:
            continue
        if sum(a != b for a, b in zip(part, token, strict=False)) + abs(len(part) - len(token)) <= 1:
            return True
    return False


def _entity_from_catalog_table(table_name: str) -> str:
    low = table_name.lower()
    for prefix in ("silver_stg_", "silver_"):
        if not low.startswith(prefix):
            continue
        rest = low[len(prefix) :]
        _source, _, entity = rest.partition("_")
        return entity or rest
    return low


def _table_prompt_score(table_name: str, columns: list[str], tokens: set[str]) -> int:
    entity = _entity_from_catalog_table(table_name)
    parts = set(re.findall(r"[a-z0-9]+", entity.replace("_", " ")))
    parts.update(re.findall(r"[a-z0-9]+", " ".join(columns).lower()))
    blob = f"{table_name} {entity} {' '.join(columns)}".lower()
    score = 0
    for token in tokens:
        if _token_matches_blob(token, blob, parts):
            score += 3 if token in entity or token in parts else 1
    return score


def _expand_join_neighbors(
    tables: set[str],
    allowed_joins: list[dict[str, str]],
) -> set[str]:
    extra = {name.lower() for name in tables}
    for join in allowed_joins:
        left = str(join.get("left_table") or "").strip().lower()
        right = str(join.get("right_table") or "").strip().lower()
        if left in extra and right:
            extra.add(right)
        if right in extra and left:
            extra.add(left)
    return extra


def format_silver_columns_for_prompt(
    columns_by_table: dict[str, list[str]],
    *,
    priority_tables: set[str] | None = None,
    prompt: str = "",
    allowed_joins: list[dict[str, str]] | None = None,
    max_chars: int = 14000,
) -> str:
    if not columns_by_table:
        return "No silver_stg column catalog available (run connector consolidate)."

    stg_tables = {
        name: columns
        for name, columns in columns_by_table.items()
        if name.lower().startswith("silver_stg_")
    }
    catalog = stg_tables or columns_by_table
    tokens = _prompt_tokens(prompt)
    scored: dict[str, int] = {
        name: _table_prompt_score(name, columns, tokens) for name, columns in catalog.items()
    }
    priority = {name.lower() for name in (priority_tables or set())}
    if tokens:
        relevant = {name.lower() for name, score in scored.items() if score > 0}
        priority.update(_expand_join_neighbors(relevant | priority, allowed_joins or []))
    ordered = sorted(
        catalog.items(),
        key=lambda item: (
            0 if item[0].lower() in priority else 1,
            -scored.get(item[0], 0),
            item[0],
        ),
    )
    lines = [
        "Ingest Glue catalog silver_stg_{source}_{entity} is authoritative. "
        "Silver SQL reads these tables. Gold SQL reads silver_{source}_{entity} "
        "with the same columns plus pinned DNA aliases. "
        "Never use source-docs property names that are not listed here "
        "(those are documentation-only, e.g. navigation fields)."
    ]
    used = sum(len(line) + 1 for line in lines)
    for table_name, columns in ordered:
        cols = ", ".join(columns)
        line = f"- {table_name}: {cols}"
        if used and used + len(line) + 1 > max_chars:
            lines.append("- … (truncated; prefer tables listed above for this request)")
            break
        lines.append(line)
        used += len(line) + 1
    return "\n".join(lines)


def _silver_stg_table_name(source: str, entity: str) -> str:
    return f"silver_stg_{normalize_reference_source(source)}_{entity}"


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
                for namer in (_silver_stg_table_name, _silver_table_name):
                    key = (namer(connector, left_ent), namer(connector, right_ent), left_col, right_col)
                    if key in seen:
                        continue
                    seen.add(key)
                    allowed.append(
                        {
                            "left_table": key[0],
                            "right_table": key[1],
                            "left_column": left_col,
                            "right_column": right_col,
                            "left_entity": left_ent,
                            "right_entity": right_ent,
                        }
                    )
    return allowed


def format_allowed_joins_for_prompt(allowed_joins: list[dict[str, str]]) -> str:
    if not allowed_joins:
        return "No relationships defined in gold entity_relationships.yaml."
    lines: list[str] = []
    emitted: set[tuple[str, str, str, str]] = set()
    for join in allowed_joins:
        left_entity = str(join.get("left_entity") or "").strip()
        right_entity = str(join.get("right_entity") or "").strip()
        if not left_entity or not right_entity:
            continue
        key = (
            left_entity,
            right_entity,
            join["left_column"],
            join["right_column"],
        )
        reverse = (
            right_entity,
            left_entity,
            join["right_column"],
            join["left_column"],
        )
        if key in emitted or reverse in emitted:
            continue
        emitted.add(key)
        lines.append(
            f"- {left_entity}.{join['left_column']} = "
            f"{right_entity}.{join['right_column']} "
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
    src = normalize_reference_source(source)
    low = table.lower()
    return low.startswith(f"silver_stg_{src}_") or low.startswith(f"silver_{src}_")


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


def _columns_with_companion_aliases(
    settings: DnaSettings,
    drafts: list[dict[str, Any]],
    *,
    columns_by_table: dict[str, list[str]] | None = None,
) -> dict[str, list[str]]:
    """Add silver contribution aliases to DNA and stg catalogs for gold validation."""
    merged = {
        table: list(columns)
        for table, columns in (columns_by_table or build_columns_by_table(settings)).items()
    }
    source = settings.source or ""
    for draft in drafts:
        if str(draft.get("layer") or "").strip().lower() != "silver":
            continue
        entity = str(draft.get("target_entity") or "").strip().lower()
        aliases = extract_new_column_aliases(str(draft.get("sql") or ""))
        if not entity or not aliases:
            continue
        for table in (
            _silver_table_name(source, entity),
            _silver_stg_table_name(source, entity),
        ):
            existing = list(merged.get(table) or [])
            known = {name.lower() for name in existing}
            for alias in aliases:
                if alias.lower() not in known:
                    existing.append(alias)
                    known.add(alias.lower())
            merged[table] = existing
    return merged


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


def _prepare_implement_draft(draft: dict[str, Any]) -> None:
    _normalize_draft_file_path(draft)
    _normalize_draft_grain_columns(draft)
    draft["sql"] = format_kpi_sql(str(draft.get("sql") or ""))


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


def _validate_layer_rules(
    draft: dict[str, Any],
    *,
    settings: DnaSettings | None = None,
    relationships: dict[str, Any] | None = None,
    pack: Any | None = None,
    existing_gold_transforms: list[dict[str, Any]] | None = None,
    columns_by_table: dict[str, list[str]] | None = None,
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
        _validate_sql_columns(settings, sql, columns_by_table=columns_by_table)
