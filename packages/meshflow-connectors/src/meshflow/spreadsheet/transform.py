"""Transformation spec, shape hashing, and row-level apply for Spreadsheet Engine."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from typing import Any

_TRANSFORM_VERSION = 1
_NULL_SENTINEL = object()

_COL_REF = re.compile(r"^[a-z][a-z0-9_]*$")
_STRING_LITERAL = re.compile(r"^'([^']*)'$|^\"([^\"]*)\"$")


def slugify_filename(filename: str) -> str:
    """Normalize a workbook filename to a stable slug (without extension)."""
    base = filename.rsplit(".", 1)[0] if "." in filename else filename
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", base.strip()).strip("_").lower()
    return slug or "workbook"


def normalize_header_name(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", str(text or "").strip()).strip("_").lower()
    return slug or "column"


def compute_input_shape(parse_table: dict[str, Any]) -> dict[str, Any]:
    """Build input shape dict + hash from a parse-table region."""
    headers = [str(h) for h in (parse_table.get("headers") or []) if str(h).strip()]
    sheet = str(parse_table.get("sheet") or "")
    column_count = len(headers)
    normalized = sorted({normalize_header_name(h) for h in headers})
    content = f"{sheet}|{column_count}|{'|'.join(normalized)}"
    shape_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
    return {
        "sheet": sheet,
        "headers": headers,
        "column_count": column_count,
        "shape_hash": shape_hash,
        "headers_normalized": normalized,
    }


def build_output_shape(table: dict[str, Any]) -> dict[str, Any]:
    return {
        "entity_name": str(table.get("entity_name") or ""),
        "grain": str(table.get("grain") or ""),
        "schema": list(table.get("schema") or []),
    }


def empty_transformation(
    *,
    input_shape: dict[str, Any] | None = None,
    output_shape: dict[str, Any] | None = None,
) -> dict[str, Any]:
    spec: dict[str, Any] = {"version": _TRANSFORM_VERSION, "steps": []}
    if input_shape:
        spec["input_shape"] = input_shape
    if output_shape:
        spec["output_shape"] = output_shape
    return spec


def shape_compatibility(
    current: dict[str, Any],
    reference: dict[str, Any],
) -> tuple[float, list[str]]:
    """Return compatibility score (0-1) and drift warnings."""
    if not reference:
        return 1.0, []
    cur_norm = set(current.get("headers_normalized") or [])
    ref_norm = set(reference.get("headers_normalized") or [])
    if not ref_norm:
        return 1.0, []
    overlap = cur_norm & ref_norm
    score = len(overlap) / max(len(ref_norm), 1)
    drift: list[str] = []
    for h in sorted(ref_norm - cur_norm):
        drift.append(f"Column '{h}' from prior upload is missing")
    for h in sorted(cur_norm - ref_norm):
        drift.append(f"Column '{h}' is new")
    if str(current.get("sheet") or "") != str(reference.get("sheet") or ""):
        drift.append(
            f"Sheet changed from '{reference.get('sheet')}' to '{current.get('sheet')}'"
        )
    return score, drift


def _row_dict(headers: list[str], row: list[Any]) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for index, header in enumerate(headers):
        key = str(header)
        data[key] = row[index] if index < len(row) else None
        norm = normalize_header_name(key)
        if norm and norm not in data:
            data[norm] = data[key]
    return data


def _parse_literal(token: str) -> Any:
    token = token.strip()
    if token.lower() == "null":
        return None
    match = _STRING_LITERAL.match(token)
    if match:
        return match.group(1) or match.group(2) or ""
    if re.fullmatch(r"-?\d+(\.\d+)?", token):
        return float(token) if "." in token else int(token)
    if _COL_REF.match(token):
        return token
    return token


def _eval_expr(expr: str, row_data: dict[str, Any]) -> Any:
    expr = str(expr or "").strip()
    if not expr:
        return None
    if expr.lower() == "null":
        return None
    if expr.endswith("!= null"):
        col = expr[:-7].strip()
        val = row_data.get(col) if _COL_REF.match(col) else row_data.get(normalize_header_name(col))
        return val is not None and str(val).strip() != ""
    if expr.endswith("== null"):
        col = expr[:-7].strip()
        val = row_data.get(col) if _COL_REF.match(col) else row_data.get(normalize_header_name(col))
        return val is None or str(val).strip() == ""
    if "+" in expr:
        parts = [p.strip() for p in expr.split("+")]
        out = ""
        for part in parts:
            parsed = _parse_literal(part)
            if isinstance(parsed, str) and _COL_REF.match(parsed):
                val = row_data.get(parsed) or row_data.get(normalize_header_name(parsed))
                out += "" if val is None else str(val)
            elif isinstance(parsed, str):
                out += parsed
            else:
                out += str(parsed)
        return out
    parsed = _parse_literal(expr)
    if isinstance(parsed, str) and _COL_REF.match(parsed):
        return row_data.get(parsed) or row_data.get(normalize_header_name(parsed))
    return parsed


def _cast_value(value: Any, target_type: str) -> Any:
    if value is None or value is _NULL_SENTINEL:
        return None
    text = str(value).strip()
    if not text:
        return None
    kind = target_type.strip().lower()
    if kind == "string":
        return text
    if kind == "number":
        cleaned = text.replace(",", "").replace("$", "")
        return float(cleaned) if "." in cleaned else int(cleaned)
    if kind == "boolean":
        return text.lower() in {"true", "yes", "1", "y"}
    if kind == "date":
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
            try:
                return datetime.strptime(text, fmt).date().isoformat()
            except ValueError:
                continue
        return text
    if kind == "datetime":
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(text, fmt).isoformat()
            except ValueError:
                continue
        return text
    if kind in {"currency", "email", "unknown"}:
        return text
    return text


def apply_transformation(
    rows: list[list[Any]],
    headers: list[str],
    spec: dict[str, Any],
) -> tuple[list[list[Any]], list[str]]:
    """Apply transformation steps to row data; return transformed rows and output headers."""
    working_headers = list(headers)
    working_rows = [list(row) for row in rows]

    for step in spec.get("steps") or []:
        if not isinstance(step, dict):
            continue
        op = str(step.get("op") or "").strip().lower()
        if op == "rename_columns":
            mapping = step.get("mapping") or {}
            if not isinstance(mapping, dict):
                continue
            new_headers = list(working_headers)
            for index, header in enumerate(new_headers):
                if header in mapping:
                    new_headers[index] = str(mapping[header])
            working_headers = new_headers
        elif op == "cast":
            columns = step.get("columns") or {}
            if not isinstance(columns, dict):
                continue
            for col_name, col_type in columns.items():
                try:
                    col_index = working_headers.index(col_name)
                except ValueError:
                    norm = normalize_header_name(col_name)
                    col_index = next(
                        (i for i, h in enumerate(working_headers) if normalize_header_name(h) == norm),
                        -1,
                    )
                if col_index < 0:
                    continue
                for row in working_rows:
                    row[col_index] = _cast_value(row[col_index], str(col_type))
        elif op == "filter_rows":
            expr = str(step.get("expr") or "")
            filtered: list[list[Any]] = []
            for row in working_rows:
                row_data = _row_dict(working_headers, row)
                try:
                    if _eval_expr(expr, row_data):
                        filtered.append(row)
                except Exception:  # noqa: BLE001
                    filtered.append(row)
            working_rows = filtered
        elif op == "derive_column":
            name = str(step.get("name") or "").strip()
            expr = str(step.get("expr") or "")
            if not name:
                continue
            working_headers.append(name)
            for row in working_rows:
                row_data = _row_dict(working_headers[:-1], row)
                try:
                    row.append(_eval_expr(expr, row_data))
                except Exception:  # noqa: BLE001
                    row.append(None)

    output_shape = spec.get("output_shape") or {}
    schema = output_shape.get("schema") or []
    if schema:
        out_names = [str(col.get("name") or "") for col in schema if isinstance(col, dict)]
        out_names = [n for n in out_names if n]
        if out_names:
            out_rows: list[list[Any]] = []
            for row in working_rows:
                row_data = _row_dict(working_headers, row)
                out_rows.append(
                    [row_data.get(n) or row_data.get(normalize_header_name(n)) for n in out_names]
                )
            return out_rows, out_names

    return working_rows, working_headers


def preview_transformation(
    rows: list[list[Any]],
    headers: list[str],
    spec: dict[str, Any],
    *,
    max_rows: int = 25,
) -> dict[str, Any]:
    """Return before/after preview for a transformation spec."""
    before = {
        "headers": list(headers),
        "rows": rows[:max_rows],
        "row_count": len(rows),
        "preview_row_count": min(len(rows), max_rows),
        "truncated": len(rows) > max_rows,
    }
    out_rows, out_headers = apply_transformation(rows, headers, spec)
    after = {
        "headers": out_headers,
        "rows": out_rows[:max_rows],
        "row_count": len(out_rows),
        "preview_row_count": min(len(out_rows), max_rows),
        "truncated": len(out_rows) > max_rows,
    }
    return {"before": before, "after": after}
