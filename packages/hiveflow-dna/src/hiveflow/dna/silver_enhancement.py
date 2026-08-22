"""Silver enhancement contributions and grain guardrails for SQL packs."""

from __future__ import annotations

import re
from typing import Any

from hiveflow.dna.settings import DnaSettings
from hiveflow.dna.store import read_text_artifact
from hiveflow.storage.paths import governance_sql_file_key, governance_sql_prefix

_GROUP_BY_RE = re.compile(
    r"\bGROUP\s+BY\b",
    re.IGNORECASE,
)
_SELECT_DISTINCT_RE = re.compile(
    r"\bSELECT\s+DISTINCT\b",
    re.IGNORECASE,
)
_TOP_LEVEL_AGG_RE = re.compile(
    r"\b(?:SUM|COUNT|AVG|MIN|MAX)\s*\(",
    re.IGNORECASE,
)
_FROM_TABLE_RE = re.compile(
    r"\bFROM\s+([\w]+)(?:\s+(?:AS\s+)?([\w]+))?",
    re.IGNORECASE,
)
_JOIN_RE = re.compile(r"\bJOIN\b", re.IGNORECASE)
_SELECT_COL_RE = re.compile(
    r"\bSELECT\s+(.*?)\s+FROM\b",
    re.IGNORECASE | re.DOTALL,
)
_AS_ALIAS_RE = re.compile(
    r"\bAS\s+([a-zA-Z_][\w]*)",
    re.IGNORECASE,
)


def canonical_enhancement_id(target_entity: str) -> str:
    entity = target_entity.strip().lower().replace(" ", "_")
    if not entity:
        raise ValueError("target_entity is required")
    return f"enhance__{entity}"


def canonical_enhancement_file(target_entity: str) -> str:
    return f"silver/{canonical_enhancement_id(target_entity)}.sql"


def contribution_sql_relative_path(target_entity: str, kpi_id: str) -> str:
    entity = target_entity.strip().lower().replace(" ", "_")
    kid = kpi_id.strip().lower().replace(" ", "_")
    if not entity or not kid:
        raise ValueError("target_entity and kpi_id are required")
    return f"silver/contributions/{entity}/{kid}.sql"


def contribution_prefix(pack_id: str, version: str, target_entity: str) -> str:
    entity = target_entity.strip().lower().replace(" ", "_")
    return f"{governance_sql_prefix(pack_id, version)}/silver/contributions/{entity}/"


def validate_gold_grain_columns(columns: list[str] | None) -> list[str]:
    if not columns:
        return []
    normalized = sorted({str(col).strip() for col in columns if str(col).strip()})
    return normalized


def gold_grain_signature(columns: list[str] | None) -> tuple[str, ...]:
    return tuple(validate_gold_grain_columns(columns))


def assert_preserves_silver_grain(sql: str, *, primary_key: str = "id") -> None:
    """Reject SQL that would change silver entity row grain."""
    text = sql.strip()
    if not text:
        raise ValueError("SQL is required")
    if _GROUP_BY_RE.search(text):
        raise ValueError(
            "Silver contribution SQL must not use GROUP BY. "
            "Use the gold layer for grain-changing aggregations."
        )
    if _SELECT_DISTINCT_RE.search(text):
        raise ValueError(
            "Silver contribution SQL must not use SELECT DISTINCT. "
            "Use the gold layer for grain-changing logic."
        )
    if _TOP_LEVEL_AGG_RE.search(text) and not _has_subquery(text):
        raise ValueError(
            "Silver contribution SQL must not use top-level aggregates. "
            "Use correlated subqueries or move aggregation to gold."
        )
    _ = primary_key  # reserved for future PK-coverage checks


def _has_subquery(sql: str) -> bool:
    return bool(re.search(r"\(\s*SELECT\b", sql, re.IGNORECASE))


def assert_unique_gold_grain(
    transforms: list[dict[str, Any]],
    *,
    output_id: str,
    grain_columns: list[str],
    exclude_transform_id: str | None = None,
) -> None:
    signature = gold_grain_signature(grain_columns)
    for item in transforms:
        tid = str(item.get("id") or "").strip()
        if exclude_transform_id and tid == exclude_transform_id:
            continue
        if str(item.get("layer") or "").strip().lower() != "gold":
            continue
        other_output = str(item.get("output_id") or "").strip()
        if other_output == output_id:
            continue
        other_sig = gold_grain_signature(item.get("grain_columns"))
        if other_sig == signature:
            other_label = other_output or tid
            grain_label = ", ".join(signature) if signature else "(company total)"
            raise ValueError(
                f"Gold grain [{grain_label}] already used by output {other_label!r}. "
                "Each gold table must have a unique grain."
            )


def list_contribution_keys(
    settings: DnaSettings,
    *,
    pack_id: str,
    version: str,
    target_entity: str,
) -> list[str]:
    prefix = contribution_prefix(pack_id, version, target_entity)
    normalized = prefix.strip().replace("\\", "/").lstrip("/")
    if normalized and not normalized.endswith("/"):
        normalized += "/"

    if settings.s3_bucket:
        import boto3

        client = boto3.client("s3")
        keys: list[str] = []
        token: str | None = None
        while True:
            kwargs: dict[str, Any] = {"Bucket": settings.s3_bucket, "Prefix": normalized}
            if token:
                kwargs["ContinuationToken"] = token
            response = client.list_objects_v2(**kwargs)
            for item in response.get("Contents") or []:
                key = str(item.get("Key") or "")
                if key.endswith(".sql"):
                    keys.append(key)
            if not response.get("IsTruncated"):
                break
            token = response.get("NextContinuationToken")
        return sorted(keys)

    from hiveflow.storage.paths import prefix_path

    root = prefix_path(settings.data_dir, normalized)
    if not root.is_dir():
        return []
    return sorted(
        str(path.relative_to(settings.data_dir).as_posix())
        for path in root.rglob("*.sql")
    )


def collect_contributions(
    settings: DnaSettings,
    *,
    pack_id: str,
    version: str,
    target_entity: str,
) -> dict[str, str]:
    """Load all contribution SQL files for a silver entity at a governance version."""
    contributions: dict[str, str] = {}
    for key in list_contribution_keys(
        settings,
        pack_id=pack_id,
        version=version,
        target_entity=target_entity,
    ):
        body = read_text_artifact(settings, key)
        if not body:
            continue
        filename = key.rsplit("/", 1)[-1]
        kpi_id = filename[:-4] if filename.endswith(".sql") else filename
        contributions[kpi_id] = body.strip()
    return contributions


def load_contribution_sql(
    settings: DnaSettings,
    *,
    pack_id: str,
    version: str,
    target_entity: str,
    kpi_id: str,
) -> str | None:
    rel = contribution_sql_relative_path(target_entity, kpi_id)
    return read_text_artifact(settings, governance_sql_file_key(pack_id, version, rel))


def write_contribution_sql(
    settings: DnaSettings,
    *,
    pack_id: str,
    version: str,
    target_entity: str,
    kpi_id: str,
    sql: str,
) -> str:
    from hiveflow.dna.store import write_text_artifact

    rel = contribution_sql_relative_path(target_entity, kpi_id)
    key = governance_sql_file_key(pack_id, version, rel)
    write_text_artifact(
        settings,
        key,
        sql.strip(),
        content_type="application/sql; charset=utf-8",
    )
    return rel


def extract_new_column_aliases(sql: str) -> list[str]:
    aliases: list[str] = []
    for match in _AS_ALIAS_RE.finditer(sql):
        alias = str(match.group(1) or "").strip()
        if alias and alias not in aliases:
            aliases.append(alias)
    return aliases


def _parse_star_projection(
    sql: str,
    *,
    table_name: str,
) -> tuple[str, str, int] | None:
    """Return ``(table_alias, rest_exprs, from_start)`` for ``*`` or ``alias.*`` projections."""
    body = sql.strip().rstrip(";")
    from_re = re.compile(
        rf"\bFROM\s+{re.escape(table_name)}(?:\s+(?:AS\s+)?(\w+))?\b",
        re.IGNORECASE,
    )
    from_match = from_re.search(body)
    if not from_match:
        return None

    table_alias = str(from_match.group(1) or "").strip() or "t"
    prefix = body[: from_match.start()]
    select_match = re.match(r"^\s*SELECT\s+(.*)\s*$", prefix, re.IGNORECASE | re.DOTALL)
    if not select_match:
        return None

    select_clause = str(select_match.group(1) or "").strip()
    star_match = re.match(
        r"^(?:(\w+)\.)?\*(?:\s*,\s*(.*))?$",
        select_clause,
        re.IGNORECASE | re.DOTALL,
    )
    if not star_match:
        return None

    star_alias = str(star_match.group(1) or "").strip()
    rest_exprs = str(star_match.group(2) or "").strip()
    if star_alias and star_alias.lower() != table_alias.lower():
        return None
    return table_alias, rest_exprs, from_match.start()


def uses_star_projection(sql: str, *, table_name: str | None = None) -> bool:
    if table_name:
        return _parse_star_projection(sql, table_name=table_name) is not None
    select_match = _SELECT_COL_RE.search(sql.strip())
    if not select_match:
        return False
    clause = str(select_match.group(1) or "").strip()
    return bool(re.match(r"^(?:\w+\.)?\*", clause, re.IGNORECASE))


def rewrite_star_select_with_except(sql: str, except_columns: list[str]) -> str:
    """Deprecated: Athena engine v2 does not support ``* EXCEPT (col)``. Use explicit columns."""
    _ = (sql, except_columns)
    return sql


def _quote_athena_identifier(name: str) -> str:
    token = str(name or "").strip()
    if not token:
        return token
    if token.islower() and token.isidentifier():
        return token
    escaped = token.replace('"', '""')
    return f'"{escaped}"'


def rewrite_star_select_with_explicit_columns(
    sql: str,
    *,
    table_name: str,
    column_lookup: dict[str, str],
    replacing_aliases: list[str],
) -> str:
    """Rewrite ``SELECT [alias.]*, expr AS col`` to an explicit column list omitting replaced aliases."""
    body = sql.strip().rstrip(";")
    if not replacing_aliases:
        return sql

    parsed = _parse_star_projection(body, table_name=table_name)
    if not parsed:
        return sql

    table_alias, rest_exprs, from_start = parsed
    replace_lower = {alias.strip().lower() for alias in replacing_aliases if alias.strip()}
    base_columns = [
        column_lookup[key]
        for key in sorted(column_lookup)
        if key not in replace_lower
    ]
    if not base_columns:
        return sql

    prefixed = [f"{table_alias}.{_quote_athena_identifier(col)}" for col in base_columns]
    projection = ", ".join(prefixed)
    if rest_exprs:
        projection = f"{projection}, {rest_exprs}"

    tail = body[from_start:]
    if not re.search(
        rf"^\s*FROM\s+{re.escape(table_name)}\s+(?:AS\s+)?\w+",
        tail,
        flags=re.IGNORECASE,
    ):
        tail = re.sub(
            rf"^(\s*FROM\s+{re.escape(table_name)})(\s+|$)",
            rf"\1 {table_alias}\2",
            tail,
            count=1,
            flags=re.IGNORECASE,
        )
    return f"SELECT {projection} {tail}".strip()


def glue_table_column_names(
    database: str,
    table_name: str,
    *,
    region: str | None = None,
) -> dict[str, str]:
    """Return Glue column names keyed by lowercase name."""
    import boto3

    client = boto3.client("glue", region_name=region)
    response = client.get_table(DatabaseName=database, Name=table_name)
    columns = (response.get("Table") or {}).get("StorageDescriptor", {}).get("Columns") or []
    return {
        str(column.get("Name") or "").strip().lower(): str(column.get("Name") or "").strip()
        for column in columns
        if str(column.get("Name") or "").strip()
    }


def prepare_add_columns_sql_for_replay(
    sql: str,
    *,
    database: str,
    table_name: str,
    region: str | None = None,
) -> str:
    """Make add-columns SQL safe to replay when enhanced columns already exist in silver."""
    body = sql.strip().rstrip(";")
    if not uses_star_projection(body, table_name=table_name):
        return sql

    aliases = extract_new_column_aliases(body)
    if not aliases:
        return sql

    try:
        existing = glue_table_column_names(database, table_name, region=region)
    except Exception:  # noqa: BLE001
        return sql

    except_columns = [
        existing[alias.lower()]
        for alias in aliases
        if alias.lower() in existing
    ]
    if not except_columns:
        return sql
    return rewrite_star_select_with_explicit_columns(
        body,
        table_name=table_name,
        column_lookup=existing,
        replacing_aliases=aliases,
    )


def retarget_silver_sql_to_stg(sql: str, *, source: str) -> str:
    """Rewrite ``silver_{source}_*`` / ``silver.entity`` refs to silver_stg for replay."""
    src = source.strip().lower()
    body = sql
    body = re.sub(r"\bsilver\.([a-zA-Z_][a-zA-Z0-9_]*)\b", r"silver_stg.\1", body, flags=re.IGNORECASE)
    if src:
        body = re.sub(
            rf"\bsilver_{re.escape(src)}_",
            f"silver_stg_{src}_",
            body,
            flags=re.IGNORECASE,
        )
    return body


def try_deterministic_merge(
    *,
    target_entity: str,
    source: str,
    contributions: dict[str, str],
) -> str | None:
    """Merge simple same-table contributions without LLM when possible."""
    if not contributions:
        return None
    if len(contributions) == 1:
        return next(iter(contributions.values()))

    stg_table = f"silver_stg_{source.strip().lower()}_{target_entity.strip().lower()}"
    legacy_table = f"silver_{source.strip().lower()}_{target_entity.strip().lower()}"
    expressions: dict[str, str] = {}
    from_tables: set[str] = set()

    for body in contributions.values():
        if _GROUP_BY_RE.search(body) or _JOIN_RE.search(body):
            return None
        from_match = _FROM_TABLE_RE.search(body)
        if not from_match:
            return None
        table = str(from_match.group(1) or "").strip().lower()
        from_tables.add(table)
        select_match = _SELECT_COL_RE.search(body)
        if not select_match:
            return None
        select_clause = str(select_match.group(1) or "").strip()
        if select_clause == "*":
            continue
        for part in _split_select_expressions(select_clause):
            expr = part.strip()
            if not expr or expr == "*":
                continue
            alias_match = _AS_ALIAS_RE.search(expr)
            if alias_match:
                alias = str(alias_match.group(1) or "").strip()
                expressions[alias] = expr

    if len(from_tables) != 1:
        return None
    table = next(iter(from_tables))
    if table not in {stg_table, legacy_table}:
        return None

    aliases = sorted(expressions)
    extra_exprs = [expressions[key] for key in aliases]
    if not extra_exprs:
        return f"SELECT * FROM {stg_table}"

    extras = ", ".join(extra_exprs)
    return f"SELECT t.*, {extras} FROM {stg_table} t"


def _split_select_expressions(select_clause: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    depth = 0
    for char in select_clause:
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        if char == "," and depth == 0:
            parts.append("".join(current))
            current = []
            continue
        current.append(char)
    if current:
        parts.append("".join(current))
    return parts
