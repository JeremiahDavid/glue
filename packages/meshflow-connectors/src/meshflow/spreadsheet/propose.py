"""Bedrock + heuristic transformation proposals for Spreadsheet Engine."""

from __future__ import annotations

import json
from difflib import SequenceMatcher
from typing import Any, Callable

from meshflow.spreadsheet.interpret import _default_invoke, _extract_json
from meshflow.spreadsheet.transform import (
    build_output_shape,
    compute_input_shape,
    empty_transformation,
    normalize_header_name,
    shape_compatibility,
    slugify_filename,
)

_PROPOSE_SYSTEM = """You propose spreadsheet-to-entity transformation specs for a data platform.
Return strict JSON only (no markdown):
{
  "tables": [
    {
      "table_id": "t0",
      "transformation": {
        "version": 1,
        "steps": [
          {"op": "rename_columns", "mapping": {"Customer Name": "customer_name"}},
          {"op": "cast", "columns": {"amount": "number"}},
          {"op": "filter_rows", "expr": "amount != null"},
          {"op": "derive_column", "name": "full_name", "expr": "first_name + ' ' + last_name"}
        ],
        "input_shape": {...},
        "output_shape": {"entity_name": "...", "grain": "...", "schema": [...]}
      },
      "transformation_confidence": 0.0-1.0,
      "transformation_notes": ["..."],
      "transformation_drift": []
    }
  ]
}
Use rename_columns, cast, filter_rows, and derive_column ops. Match output schema to the interpreted entity."""


def _header_mapping(
    source_headers: list[str],
    target_schema: list[dict[str, Any]],
) -> dict[str, str]:
    mapping: dict[str, str] = {}
    targets = {
        str(col.get("name") or ""): normalize_header_name(str(col.get("name") or ""))
        for col in target_schema
        if isinstance(col, dict)
    }
    used: set[str] = set()
    for header in source_headers:
        src_norm = normalize_header_name(header)
        best_name = ""
        best_score = 0.0
        for target_name, target_norm in targets.items():
            if target_name in used:
                continue
            score = SequenceMatcher(None, src_norm, target_norm).ratio()
            if score > best_score:
                best_score = score
                best_name = target_name
        if best_name and best_score >= 0.6:
            mapping[header] = best_name
            used.add(best_name)
    return mapping


def _heuristic_transformation(
    *,
    table: dict[str, Any],
    parse_table: dict[str, Any],
    linked_catalog: dict[str, Any] | None = None,
    knowledge_entries: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    input_shape = compute_input_shape(parse_table)
    output_shape = build_output_shape(table)
    schema = list(table.get("schema") or [])
    steps: list[dict[str, Any]] = []
    notes: list[str] = []
    drift: list[str] = []
    confidence = 0.4
    reused_from = ""

    ref_spec = None
    ref_input = None
    if linked_catalog:
        ref_spec = linked_catalog.get("transformation") or {}
        ref_input = ref_spec.get("input_shape") or linked_catalog.get("input_shape")
        reused_from = str(linked_catalog.get("catalog_id") or "")
    elif knowledge_entries:
        entry = knowledge_entries[0]
        ref_spec = entry.get("transformation") or {}
        ref_input = ref_spec.get("input_shape") or entry.get("input_shape")
        reused_from = str(entry.get("catalog_id") or entry.get("knowledge_id") or "")

    if ref_spec and ref_input:
        score, drift = shape_compatibility(input_shape, ref_input)
        ref_steps = list(ref_spec.get("steps") or [])
        if score >= 0.8 and ref_steps:
            steps = ref_steps
            confidence = min(0.95, 0.5 + score * 0.45)
            notes.append(f"Reused {len(ref_steps)} transformation step(s) from prior approval")
        else:
            mapping = _header_mapping(input_shape.get("headers") or [], schema)
            if mapping:
                steps.append({"op": "rename_columns", "mapping": mapping})
                notes.append(f"Mapped {len(mapping)} column(s) via name similarity")
            confidence = 0.35 + score * 0.3
    else:
        mapping = _header_mapping(input_shape.get("headers") or [], schema)
        if mapping:
            steps.append({"op": "rename_columns", "mapping": mapping})
            notes.append(f"Mapped {len(mapping)} column(s) via name similarity")

    cast_cols: dict[str, str] = {}
    for col in schema:
        if not isinstance(col, dict):
            continue
        name = str(col.get("name") or "")
        col_type = str(col.get("type") or "string")
        if name and col_type not in {"unknown", "string"}:
            cast_cols[name] = col_type
    if cast_cols:
        steps.append({"op": "cast", "columns": cast_cols})

    transformation = {
        "version": 1,
        "steps": steps,
        "input_shape": input_shape,
        "output_shape": output_shape,
    }
    return {
        "transformation": transformation,
        "transformation_status": "pending_review",
        "transformation_confidence": round(confidence, 2),
        "transformation_notes": notes,
        "transformation_drift": drift,
        "reused_from_catalog_id": reused_from,
    }


def propose_transforms_for_report(
    report: dict[str, Any],
    parse_payload: dict[str, Any],
    *,
    linked_catalog: dict[str, Any] | None = None,
    knowledge_entries: list[dict[str, Any]] | None = None,
    invoke: Callable[[str, str], str] | None = None,
) -> dict[str, Any]:
    """Add transformation proposals to each table in the report."""
    parse_tables = {
        str(t.get("table_id")): t
        for t in (parse_payload.get("tables") or [])
        if isinstance(t, dict) and t.get("table_id")
    }
    kb = list(knowledge_entries or [])
    llm_tables: dict[str, dict[str, Any]] = {}

    if invoke is not False:
        user_payload = {
            "filename": parse_payload.get("filename"),
            "linked_catalog": linked_catalog,
            "knowledge_examples": kb[:3],
            "tables": [],
        }
        for table in report.get("tables") or []:
            if not isinstance(table, dict):
                continue
            table_id = str(table.get("table_id") or "")
            parse_table = parse_tables.get(table_id) or {}
            user_payload["tables"].append(
                {
                    "table_id": table_id,
                    "interpretation": table,
                    "parse": parse_table,
                    "input_shape": compute_input_shape(parse_table) if parse_table else {},
                }
            )
        try:
            invoke_fn = invoke or _default_invoke
            raw = invoke_fn(_PROPOSE_SYSTEM, json.dumps(user_payload, default=str))
            parsed = _extract_json(raw)
            for item in parsed.get("tables") or []:
                if isinstance(item, dict) and item.get("table_id"):
                    llm_tables[str(item["table_id"])] = item
        except Exception:  # noqa: BLE001
            llm_tables = {}

    updated_tables: list[dict[str, Any]] = []
    for table in report.get("tables") or []:
        if not isinstance(table, dict):
            continue
        table_id = str(table.get("table_id") or "")
        parse_table = parse_tables.get(table_id) or {}
        llm_item = llm_tables.get(table_id)
        if llm_item and isinstance(llm_item.get("transformation"), dict):
            proposal = {
                "transformation": llm_item["transformation"],
                "transformation_status": "pending_review",
                "transformation_confidence": float(llm_item.get("transformation_confidence") or 0.7),
                "transformation_notes": list(llm_item.get("transformation_notes") or []),
                "transformation_drift": list(llm_item.get("transformation_drift") or []),
                "reused_from_catalog_id": str(llm_item.get("reused_from_catalog_id") or ""),
            }
        else:
            proposal = _heuristic_transformation(
                table=table,
                parse_table=parse_table,
                linked_catalog=linked_catalog,
                knowledge_entries=kb,
            )
        input_shape = compute_input_shape(parse_table) if parse_table else {}
        transformation = proposal.get("transformation") or empty_transformation()
        if input_shape and not transformation.get("input_shape"):
            transformation["input_shape"] = input_shape
        if not transformation.get("output_shape"):
            transformation["output_shape"] = build_output_shape(table)
        proposal["transformation"] = transformation
        updated_tables.append({**table, **proposal})

    report["tables"] = updated_tables
    report["table_count"] = len(updated_tables)
    return report


def propose_transforms(
    parse_payload: dict[str, Any],
    profile_payload: dict[str, Any],
    report: dict[str, Any],
    *,
    linked_catalog: dict[str, Any] | None = None,
    knowledge_entries: list[dict[str, Any]] | None = None,
    invoke: Callable[[str, str], str] | None = None,
) -> dict[str, Any]:
    """Propose transformations for an interpreted report."""
    filename = str(parse_payload.get("filename") or report.get("filename") or "")
    report = propose_transforms_for_report(
        report,
        parse_payload,
        linked_catalog=linked_catalog,
        knowledge_entries=knowledge_entries,
        invoke=invoke,
    )
    report["filename"] = filename
    report["source_file_slug"] = slugify_filename(filename)
    return report
