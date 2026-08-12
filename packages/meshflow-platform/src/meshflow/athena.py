"""Shared Athena query helpers (validation SELECTs + materializing UNLOAD)."""

from __future__ import annotations

import re
import time
from typing import Any, Callable

_LAYER_CATALOG_REF_RE = re.compile(
    r"\b(silver|gold)\.([a-zA-Z_][a-zA-Z0-9_]*)\b",
    re.IGNORECASE,
)


class AthenaQueryError(RuntimeError):
    """Athena query failed or was cancelled."""


def start_query(
    *,
    query: str,
    database: str,
    workgroup: str,
    region: str | None = None,
    client: Any | None = None,
) -> str:
    """Start an Athena query; return QueryExecutionId."""
    athena = client or _client(region)
    execution = athena.start_query_execution(
        QueryString=query,
        QueryExecutionContext={"Database": database},
        WorkGroup=workgroup,
    )
    return str(execution["QueryExecutionId"])


def wait_query(
    execution_id: str,
    *,
    region: str | None = None,
    client: Any | None = None,
    poll_seconds: float = 2.0,
    timeout_seconds: float = 600.0,
) -> dict[str, Any]:
    """Poll until SUCCEEDED; raise AthenaQueryError on failure/timeout."""
    athena = client or _client(region)
    deadline = time.monotonic() + timeout_seconds
    while True:
        response = athena.get_query_execution(QueryExecutionId=execution_id)
        status = response["QueryExecution"]["Status"]
        state = status["State"]
        if state == "SUCCEEDED":
            return response["QueryExecution"]
        if state in {"FAILED", "CANCELLED"}:
            reason = status.get("StateChangeReason", state)
            raise AthenaQueryError(f"Athena query {state.lower()}: {reason}")
        if time.monotonic() >= deadline:
            raise AthenaQueryError(f"Athena query timed out after {timeout_seconds:.0f}s")
        time.sleep(poll_seconds)


def fetch_results(
    execution_id: str,
    *,
    region: str | None = None,
    client: Any | None = None,
    max_rows: int = 1000,
) -> dict[str, Any]:
    """Return ``{columns: [...], rows: [dict, ...]}`` for a succeeded query."""
    athena = client or _client(region)
    columns: list[str] = []
    rows: list[dict[str, Any]] = []
    next_token: str | None = None
    remaining = max(0, int(max_rows))
    header_consumed = False

    while remaining > 0 or not header_consumed:
        kwargs: dict[str, Any] = {
            "QueryExecutionId": execution_id,
            "MaxResults": min(1000, max(1, remaining + (0 if header_consumed else 1))),
        }
        if next_token:
            kwargs["NextToken"] = next_token
        page = athena.get_query_results(**kwargs)
        result_rows = page.get("ResultSet", {}).get("Rows") or []
        if not header_consumed and result_rows:
            columns = [cell.get("VarCharValue", "") for cell in result_rows[0].get("Data", [])]
            result_rows = result_rows[1:]
            header_consumed = True
        for row in result_rows:
            if remaining <= 0:
                break
            values = [cell.get("VarCharValue") for cell in row.get("Data", [])]
            item = {columns[i] if i < len(columns) else f"c{i}": values[i] for i in range(len(values))}
            rows.append(item)
            remaining -= 1
        next_token = page.get("NextToken")
        if not next_token or remaining <= 0:
            break

    return {"columns": columns, "rows": rows, "execution_id": execution_id}


def run_query(
    query: str,
    *,
    database: str,
    workgroup: str,
    region: str | None = None,
    client: Any | None = None,
    poll_seconds: float = 2.0,
    timeout_seconds: float = 600.0,
    max_rows: int = 1000,
    fetch: bool = True,
) -> dict[str, Any]:
    """Start, wait, and optionally fetch results."""
    execution_id = start_query(
        query=query,
        database=database,
        workgroup=workgroup,
        region=region,
        client=client,
    )
    execution = wait_query(
        execution_id,
        region=region,
        client=client,
        poll_seconds=poll_seconds,
        timeout_seconds=timeout_seconds,
    )
    payload: dict[str, Any] = {
        "execution_id": execution_id,
        "status": "SUCCEEDED",
        "statistics": execution.get("Statistics") or {},
    }
    if fetch:
        results = fetch_results(
            execution_id,
            region=region,
            client=client,
            max_rows=max_rows,
        )
        payload.update(results)
    return payload


def wrap_unload(select_sql: str, s3_output_prefix: str) -> str:
    """Wrap a SELECT (or SELECT body) as Athena UNLOAD to Parquet."""
    body = select_sql.strip().rstrip(";")
    # Allow full SELECT statements or parenthesized subqueries.
    if body.upper().startswith("SELECT") or body.upper().startswith("WITH"):
        inner = body
    else:
        inner = f"SELECT * FROM ({body})"
    location = s3_output_prefix.rstrip("/") + "/"
    return (
        f"UNLOAD ({inner})\n"
        f"TO '{location}'\n"
        f"WITH (format = 'PARQUET', compression = 'SNAPPY')"
    )


def materialize_select_to_prefix(
    select_sql: str,
    *,
    s3_output_prefix: str,
    database: str,
    workgroup: str,
    region: str | None = None,
    client: Any | None = None,
    poll_seconds: float = 2.0,
    timeout_seconds: float = 900.0,
) -> dict[str, Any]:
    """UNLOAD a SELECT to an S3 prefix (Athena writes one or more Parquet parts)."""
    query = wrap_unload(select_sql, s3_output_prefix)
    return run_query(
        query,
        database=database,
        workgroup=workgroup,
        region=region,
        client=client,
        poll_seconds=poll_seconds,
        timeout_seconds=timeout_seconds,
        fetch=False,
    )


def normalize_athena_catalog_refs(
    sql: str,
    *,
    source: str,
    database: str | None = None,
) -> str:
    """Rewrite ``silver.entity`` / ``gold.output`` refs to Glue table names in the meshflow DB."""
    from meshflow.project_config import catalog_table_name, dna_catalog_table_name

    src = source.strip().lower()
    body = sql.strip()

    def _replace(match: re.Match[str]) -> str:
        layer = match.group(1).lower()
        name = match.group(2)
        low = name.lower()
        if layer == "silver":
            if low.startswith("silver_") or low.startswith("dna_"):
                return name
            return catalog_table_name("silver", src, name)
        if low.startswith("dna_"):
            return name
        return dna_catalog_table_name(name)

    body = _LAYER_CATALOG_REF_RE.sub(_replace, body)
    if database:
        body = re.sub(re.escape(database) + r"\.", "", body, flags=re.IGNORECASE)
    return body


def inject_validation_filters(select_sql: str, filters: list[dict[str, str]]) -> str:
    """Wrap production SELECT with session-only validation predicates (AND).

    ``filters`` items: ``{table|fact, field, value}``. Does not mutate the original SQL.
    """
    body = select_sql.strip().rstrip(";")
    predicates: list[str] = []
    for item in filters:
        field = str(item.get("field") or "").strip()
        value = str(item.get("value") or "")
        if not field:
            continue
        # Qualify only the bare identifier; reject path traversal style names.
        if not _safe_ident(field):
            raise ValueError(f"Invalid filter field: {field!r}")
        predicates.append(f"{field} = {_sql_literal(value)}")
    if not predicates:
        return body
    where = " AND ".join(predicates)
    return f"SELECT * FROM (\n{body}\n) AS _kpi_validation\nWHERE {where}"


def _safe_ident(name: str) -> bool:
    if not name or len(name) > 128:
        return False
    for ch in name:
        if not (ch.isalnum() or ch in {"_", "."}):
            return False
    return True


def _sql_literal(value: str) -> str:
    escaped = value.replace("'", "''")
    return f"'{escaped}'"


def _client(region: str | None) -> Any:
    import boto3

    kwargs: dict[str, Any] = {}
    if region:
        kwargs["region_name"] = region
    return boto3.client("athena", **kwargs)
