"""Tests for silver key derivation."""

from __future__ import annotations

from meshflow.silver.key_derivation import apply_key_derivation_to_row, derive_row_key


def test_derive_row_key_hash_is_deterministic() -> None:
    row = {"accountId": "a1", "dateFilter": "2024-01-01"}
    first = derive_row_key(row, method="hash", columns=["accountId", "dateFilter"])
    second = derive_row_key(row, method="hash", columns=["accountId", "dateFilter"])
    assert first == second
    assert first


def test_derive_row_key_concat_uses_separator() -> None:
    row = {"accountId": "a1", "dateFilter": "2024-01-01"}
    assert derive_row_key(row, method="concat", columns=["accountId", "dateFilter"], separator="|") == "a1|2024-01-01"


def test_apply_key_derivation_writes_output_column() -> None:
    row = {"accountId": "a1", "dateFilter": "2024-01-01"}
    config = {
        "key_derivation": {
            "method": "concat",
            "columns": ["accountId", "dateFilter"],
            "separator": "|",
            "output_column": "_row_key",
        }
    }
    updated = apply_key_derivation_to_row(row, config)
    assert updated["_row_key"] == "a1|2024-01-01"
