"""Per-table pipeline stages for Spreadsheet Engine review."""

from __future__ import annotations

from typing import Any

# Ordered stages for UI steppers.
PIPELINE_STAGES: tuple[tuple[str, str], ...] = (
    ("clean_review", "1. Review cleaned data"),
    ("transform_review", "2. Compare transform output"),
    ("transform_approved", "3. Save transformation"),
    ("approved", "4. Catalogued"),
)

STAGE_LABELS = {key: label for key, label in PIPELINE_STAGES}


def table_pipeline_stage(table: dict[str, Any] | None) -> str:
    """Derive the current review stage for one table proposal."""
    if not table:
        return "clean_review"
    if str(table.get("status") or "") == "approved":
        return "approved"

    transform_status = str(table.get("transformation_status") or "")
    shape_status = str(table.get("clean_shape_status") or "")
    has_goal = bool(table.get("clean_goal"))
    steps = list((table.get("transformation") or {}).get("steps") or [])

    if transform_status == "approved":
        return "transform_approved"
    if shape_status == "approved" and steps:
        return "transform_review"
    if has_goal and shape_status in {"", "pending_review", "rejected"}:
        return "clean_review"
    if transform_status in {"pending_review", "rejected"} and steps:
        return "transform_review"
    if shape_status == "approved":
        return "transform_review"
    return "clean_review"


def stage_index(stage: str) -> int:
    keys = [key for key, _ in PIPELINE_STAGES]
    try:
        return keys.index(stage)
    except ValueError:
        return 0
