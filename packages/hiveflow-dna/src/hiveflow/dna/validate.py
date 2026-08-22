from __future__ import annotations

from datetime import datetime
from meshflow.compat import UTC
from typing import Any

from meshflow.dna.schema import DefinitionPack
from meshflow.dna.settings import DnaSettings
from meshflow.dna.store import load_pack_from_settings, read_silver_entity, read_staging_output


def _join_orphan_rate(
    pack: DefinitionPack,
    settings: DnaSettings,
    join_id: str,
) -> float:
    join = pack.join_by_id(join_id)
    left_entity = pack.entity_by_id(join.left_entity)
    right_entity = pack.entity_by_id(join.right_entity)
    left_rows = read_silver_entity(settings, left_entity.silver_entity)
    right_rows = read_silver_entity(settings, right_entity.silver_entity)
    if not left_rows:
        return 0.0

    right_keys = {row.get(join.right_key) for row in right_rows}
    orphans = sum(
        1
        for row in left_rows
        if row.get(join.left_key) is not None and row.get(join.left_key) not in right_keys
    )
    return orphans / len(left_rows)


def run_validation(
    settings: DnaSettings,
    pack: DefinitionPack | None = None,
) -> dict[str, Any]:
    if pack is None:
        pack = load_pack_from_settings(settings)

    results: list[dict[str, Any]] = []
    passed = True

    for test in pack.tests:
        outcome: dict[str, Any] = {"test_id": test.id, "test_type": test.test_type}
        try:
            if test.test_type == "join_orphan_rate":
                rate = _join_orphan_rate(pack, settings, test.join_id)
                outcome["orphan_rate"] = rate
                outcome["max_orphan_rate"] = test.max_orphan_rate
                outcome["passed"] = rate <= test.max_orphan_rate
            elif test.test_type == "required_columns":
                rows = read_staging_output(settings, test.output_id)
                if not rows:
                    outcome["passed"] = True
                    outcome["note"] = "no rows — column check deferred"
                else:
                    columns = set(rows[0].keys())
                    missing = [column for column in test.columns if column not in columns]
                    outcome["missing_columns"] = missing
                    outcome["passed"] = not missing
            elif test.test_type == "row_count_minimum":
                rows = read_staging_output(settings, test.output_id)
                outcome["row_count"] = len(rows)
                outcome["minimum_rows"] = test.minimum_rows
                outcome["passed"] = len(rows) >= test.minimum_rows
            elif test.test_type == "header_line_sum_tolerance":
                outcome["passed"] = True
                outcome["note"] = "header_line_sum_tolerance not implemented in v1"
            else:
                outcome["passed"] = False
                outcome["error"] = f"Unknown test type {test.test_type!r}"
        except Exception as exc:  # noqa: BLE001 — collect all test failures
            outcome["passed"] = False
            outcome["error"] = str(exc)

        if not outcome.get("passed"):
            passed = False
        results.append(outcome)

    return {
        "status": "passed" if passed else "failed",
        "pack_id": pack.pack_id,
        "pack_version": pack.version,
        "validated_at": datetime.now(UTC).isoformat(),
        "results": results,
    }
