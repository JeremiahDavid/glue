"""Per-table pipeline stages for Spreadsheet Engine review."""

from __future__ import annotations

from typing import Any

# Ordered stages for UI steppers.
PIPELINE_STAGES: tuple[tuple[str, str], ...] = (
    ("clean_review", "1. Review cleaned data"),
    ("transform_review", "2. Compare transform output"),
    ("transform_approved", "3. Save transformation"),
    ("catalogued", "4. Catalogued"),
    ("join_review", "5. Propose lake joins"),
)

STAGE_LABELS = {key: label for key, label in PIPELINE_STAGES}
STAGE_LABELS["approved"] = STAGE_LABELS["catalogued"]
STAGE_LABELS["joins_approved"] = "5. Propose lake joins"


def table_pipeline_stage(table: dict[str, Any] | None) -> str:
    """Derive the current review stage for one table proposal."""
    if not table:
        return "clean_review"
    if str(table.get("status") or "") == "approved":
        join_status = str(table.get("join_status") or "")
        if join_status == "approved":
            return "joins_approved"
        if join_status or table.get("join_proposals") is not None:
            return "join_review"
        return "catalogued"

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
    if stage in {"approved", "joins_approved"}:
        return len(PIPELINE_STAGES)
    keys = [key for key, _ in PIPELINE_STAGES]
    try:
        return keys.index(stage)
    except ValueError:
        return 0
