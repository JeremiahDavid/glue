"""Silver table integrity baselines and fingerprint comparison."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from hiveflow.compat import UTC
from typing import Any

from hiveflow.dna.settings import DnaSettings
from hiveflow.dna.store import read_json_artifact, read_silver_stg_entity, write_json_artifact
from hiveflow.storage.paths import silver_baseline_fingerprint_key


@dataclass
class TableFingerprint:
    row_count: int
    pk_checksum: str
    primary_key: list[str]
    captured_at: str = ""
    capture_phase: str = "post_consolidate_pre_enhancement"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> TableFingerprint:
        pk_raw = payload.get("primary_key") or ["id"]
        if isinstance(pk_raw, str):
            pk_cols = [pk_raw.strip()] if pk_raw.strip() else ["id"]
        else:
            pk_cols = [str(col).strip() for col in pk_raw if str(col).strip()] or ["id"]
        return cls(
            row_count=int(payload.get("row_count") or 0),
            pk_checksum=str(payload.get("pk_checksum") or "").strip().lower(),
            primary_key=pk_cols,
            captured_at=str(payload.get("captured_at") or ""),
            capture_phase=str(payload.get("capture_phase") or "post_consolidate_pre_enhancement"),
        )


def _pk_tuple(row: dict[str, Any], pk_columns: list[str]) -> tuple[str, ...]:
    return tuple("" if row.get(col) is None else str(row.get(col)) for col in pk_columns)


def fingerprint_from_rows(
    rows: list[dict[str, Any]],
    *,
    primary_key: list[str] | str = "id",
) -> TableFingerprint:
    pk_columns = (
        [primary_key.strip()]
        if isinstance(primary_key, str)
        else [col.strip() for col in primary_key if col.strip()]
    ) or ["id"]
    pk_values = sorted(_pk_tuple(row, pk_columns) for row in rows)
    digest = hashlib.sha256("\n".join("|".join(values) for values in pk_values).encode("utf-8"))
    return TableFingerprint(
        row_count=len(rows),
        pk_checksum=digest.hexdigest(),
        primary_key=pk_columns,
        captured_at=datetime.now(UTC).isoformat(),
    )


def compare_fingerprints(
    baseline: TableFingerprint,
    candidate: TableFingerprint,
) -> list[str]:
    """Return human-readable integrity violations (empty = pass)."""
    errors: list[str] = []
    if baseline.row_count != candidate.row_count:
        errors.append(
            f"Row count mismatch: baseline has {baseline.row_count}, "
            f"candidate has {candidate.row_count}"
        )
    if baseline.pk_checksum != candidate.pk_checksum:
        errors.append(
            "Primary-key checksum mismatch: enhancement changed the base row set "
            f"(expected checksum {baseline.pk_checksum[:12]}…, "
            f"got {candidate.pk_checksum[:12]}…)"
        )
    return errors


def write_baseline_fingerprint(
    settings: DnaSettings,
    *,
    source: str,
    entity: str,
    fingerprint: TableFingerprint,
) -> str:
    key = silver_baseline_fingerprint_key(source, entity)
    write_json_artifact(settings, key, fingerprint.to_dict())
    return key


def load_baseline_fingerprint(
    settings: DnaSettings,
    *,
    source: str,
    entity: str,
) -> TableFingerprint | None:
    key = silver_baseline_fingerprint_key(source, entity)
    payload = read_json_artifact(settings, key)
    if not isinstance(payload, dict):
        return None
    return TableFingerprint.from_dict(payload)


def snapshot_silver_baselines(
    settings: DnaSettings,
    *,
    source: str,
    entities: list[str],
    primary_key_for_entity: dict[str, str] | None = None,
) -> dict[str, str]:
    """Capture post-consolidate fingerprints before silver DNA SQL replay."""
    keys: dict[str, str] = {}
    pk_map = primary_key_for_entity or {}
    for raw_entity in sorted({name.strip().lower() for name in entities if name.strip()}):
        rows = read_silver_stg_entity(settings, raw_entity)
        if not rows:
            continue
        fingerprint = fingerprint_from_rows(
            rows,
            primary_key=pk_map.get(raw_entity, "id"),
        )
        keys[raw_entity] = write_baseline_fingerprint(
            settings,
            source=source,
            entity=raw_entity,
            fingerprint=fingerprint,
        )
    return keys


def build_athena_fingerprint_query(
    merged_sql: str,
    *,
    primary_key: list[str] | str,
) -> str:
    pk_columns = (
        [primary_key.strip()]
        if isinstance(primary_key, str)
        else [col.strip() for col in primary_key if col.strip()]
    ) or ["id"]
    pk_line = " || '|' || ".join(
        f"COALESCE(CAST({col} AS varchar), '')" for col in pk_columns
    )
    body = merged_sql.strip().rstrip(";")
    return (
        "SELECT COUNT(*) AS row_count, "
        "to_hex(sha256(to_utf8(array_join(array_agg(pk_line ORDER BY pk_line), chr(10))))) "
        "AS pk_checksum "
        f"FROM (SELECT {pk_line} AS pk_line FROM ({body}) AS _candidate_rows) AS _candidate"
    )


def fingerprint_from_athena_result(result: dict[str, Any]) -> TableFingerprint:
    rows = result.get("rows") or []
    if not rows:
        raise ValueError("Athena fingerprint query returned no rows")
    row = rows[0]
    columns = result.get("columns") or []
    by_name: dict[str, int] = {}
    for idx, col in enumerate(columns):
        if isinstance(col, str):
            name = col.strip()
            if name:
                by_name[name] = idx
            continue
        if isinstance(col, dict):
            name = str(col.get("name") or col.get("Name") or "").strip()
            if name:
                by_name[name] = idx

    def _cell(name: str) -> Any:
        if isinstance(row, dict):
            return row.get(name)
        idx = by_name.get(name)
        if idx is None:
            return None
        if isinstance(row, (list, tuple)) and idx < len(row):
            return row[idx]
        return None

    return TableFingerprint(
        row_count=int(_cell("row_count") or 0),
        pk_checksum=str(_cell("pk_checksum") or "").strip().lower(),
        primary_key=["id"],
        captured_at=datetime.now(UTC).isoformat(),
        capture_phase="athena_candidate",
    )


def validate_silver_enhancement_integrity(
    baseline: TableFingerprint,
    candidate: TableFingerprint,
) -> dict[str, Any]:
    errors = compare_fingerprints(baseline, candidate)
    return {
        "status": "passed" if not errors else "failed",
        "baseline": baseline.to_dict(),
        "candidate": candidate.to_dict(),
        "errors": errors,
    }
