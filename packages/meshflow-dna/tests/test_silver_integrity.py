"""Tests for silver integrity fingerprints."""

from __future__ import annotations

import pytest

from meshflow.dna.silver_integrity import (
    TableFingerprint,
    compare_fingerprints,
    fingerprint_from_athena_result,
    fingerprint_from_rows,
    validate_silver_enhancement_integrity,
)


def test_fingerprint_from_rows_stable_checksum() -> None:
    rows = [{"id": "b", "name": "B"}, {"id": "a", "name": "A"}]
    fp1 = fingerprint_from_rows(rows, primary_key="id")
    fp2 = fingerprint_from_rows(list(reversed(rows)), primary_key="id")
    assert fp1.row_count == 2
    assert fp1.pk_checksum == fp2.pk_checksum


def test_compare_fingerprints_detects_row_count_change() -> None:
    baseline = TableFingerprint(row_count=2, pk_checksum="abc", primary_key=["id"])
    candidate = TableFingerprint(row_count=3, pk_checksum="abc", primary_key=["id"])
    errors = compare_fingerprints(baseline, candidate)
    assert any("Row count mismatch" in err for err in errors)


def test_fingerprint_from_athena_result_accepts_string_columns() -> None:
    """meshflow.athena.fetch_results returns columns as plain name strings."""
    result = {
        "columns": ["row_count", "pk_checksum"],
        "rows": [{"row_count": "42", "pk_checksum": "deadbeef"}],
    }
    fp = fingerprint_from_athena_result(result)
    assert fp.row_count == 42
    assert fp.pk_checksum == "deadbeef"


def test_validate_silver_enhancement_integrity_passes_matching() -> None:
    baseline = fingerprint_from_rows([{"id": "1"}, {"id": "2"}], primary_key="id")
    candidate = fingerprint_from_rows([{"id": "1"}, {"id": "2"}], primary_key="id")
    result = validate_silver_enhancement_integrity(baseline, candidate)
    assert result["status"] == "passed"
