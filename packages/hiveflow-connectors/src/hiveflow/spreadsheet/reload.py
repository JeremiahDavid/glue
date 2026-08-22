"""Reload validation for previously approved spreadsheet catalog entries."""

from __future__ import annotations

from typing import Any

from meshflow.spreadsheet.transform import (
    apply_transformation,
    compute_input_shape,
    normalize_header_name,
    shape_compatibility,
)


def validate_output_schema(
    output_headers: list[str],
    expected_schema: list[dict[str, Any]],
) -> tuple[bool, list[str]]:
    """Check transformed output headers against an approved schema."""
    issues: list[str] = []
    expected_names = [str(col.get("name") or "") for col in expected_schema if isinstance(col, dict)]
    expected_norm = {normalize_header_name(n) for n in expected_names if n}
    actual_norm = {normalize_header_name(h) for h in output_headers if str(h).strip()}
    for name in expected_names:
        norm = normalize_header_name(name)
        if norm and norm not in actual_norm:
            issues.append(f"Expected column '{name}' missing from transformed output")
    for header in output_headers:
        norm = normalize_header_name(header)
        if norm and norm not in expected_norm:
            issues.append(f"Unexpected column '{header}' in transformed output")
    return not issues, issues


def validate_reload_table(
    *,
    parse_table: dict[str, Any],
    profile_table: dict[str, Any] | None,
    catalog_entry: dict[str, Any],
    sample_headers: list[str],
    sample_rows: list[list[Any]],
) -> dict[str, Any]:
    """Validate a re-uploaded table against a catalog entry without calling AI."""
    proposal = catalog_entry.get("proposal") if isinstance(catalog_entry.get("proposal"), dict) else {}
    transformation = catalog_entry.get("transformation") or proposal.get("transformation") or {}
    input_shape = compute_input_shape(parse_table)
    ref_input = catalog_entry.get("input_shape") or transformation.get("input_shape") or {}
    output_shape = catalog_entry.get("output_shape") or transformation.get("output_shape") or {}
    expected_schema = list(output_shape.get("schema") or proposal.get("schema") or [])

    issues: list[str] = []
    _, input_drift = shape_compatibility(input_shape, ref_input)
    for note in input_drift:
        issues.append(f"Input shape: {note}")

    out_rows, out_headers = apply_transformation(sample_rows, sample_headers, transformation)
    schema_ok, schema_issues = validate_output_schema(out_headers, expected_schema)
    issues.extend(schema_issues)

    if profile_table and expected_schema:
        profile_cols = {
            normalize_header_name(str(c.get("name") or "")): c
            for c in (profile_table.get("columns") or [])
            if isinstance(c, dict)
        }
        for col in expected_schema:
            if not isinstance(col, dict):
                continue
            name = str(col.get("name") or "")
            norm = normalize_header_name(name)
            prof = profile_cols.get(norm)
            if prof and col.get("is_key") and not prof.get("likely_key"):
                issues.append(f"Column '{name}' was expected as key but no longer looks like a key")

    passed = schema_ok and not input_drift
    return {
        "reload_validation_status": "passed" if passed else "failed",
        "reload_validation_issues": issues,
        "input_shape": input_shape,
        "output_headers": out_headers,
        "output_row_count": len(out_rows),
        "input_drift": input_drift,
        "schema_match": schema_ok,
    }


def build_reload_table_proposal(
    *,
    table_id: str,
    parse_table: dict[str, Any],
    profile_table: dict[str, Any] | None,
    catalog_entry: dict[str, Any],
    validation: dict[str, Any],
) -> dict[str, Any]:
    """Build a table proposal dict from catalog data for reload jobs."""
    proposal = dict(catalog_entry.get("proposal") or {})
    proposal["table_id"] = table_id
    proposal["status"] = "pending_review"
    proposal["reload_mode"] = True
    proposal["linked_catalog_id"] = str(catalog_entry.get("catalog_id") or "")
    proposal["reused_from_catalog_id"] = str(catalog_entry.get("catalog_id") or "")

    transformation = dict(catalog_entry.get("transformation") or proposal.get("transformation") or {})
    input_shape = validation.get("input_shape") or compute_input_shape(parse_table)
    if input_shape:
        transformation["input_shape"] = input_shape
    proposal["transformation"] = transformation

    if validation.get("reload_validation_status") == "passed":
        proposal["transformation_status"] = "approved"
        proposal["transformation_notes"] = ["Reload validation passed — reused approved transformation."]
    else:
        proposal["transformation_status"] = "pending_review"
        proposal["transformation_notes"] = [
            "Reload validation failed — choose how to proceed below.",
        ]

    proposal["transformation_drift"] = list(validation.get("input_drift") or [])
    proposal["reload_validation_status"] = validation.get("reload_validation_status") or "failed"
    proposal["reload_validation_issues"] = list(validation.get("reload_validation_issues") or [])

    if profile_table:
        proposal["profiling"] = profile_table
        proposal["source"] = {
            "sheet": parse_table.get("sheet") or profile_table.get("sheet"),
            "header_row": parse_table.get("header_row"),
            "data_start_row": parse_table.get("data_start_row"),
            "data_end_row": parse_table.get("data_end_row"),
            "row_count": profile_table.get("row_count"),
            "column_count": profile_table.get("column_count"),
        }

    return proposal
