from __future__ import annotations

from meshflow.dna.web.portal.views import (
    _filter_pack_history,
    _history_entry_target,
    _history_table_rows,
)


def test_history_entry_target_defaults() -> None:
    assert _history_entry_target({}) == "dna"
    assert _history_entry_target({"target": "reporting"}) == "reporting"
    assert (
        _history_entry_target({"notes": "Updated via client portal"})
        == "all"
    )


def test_filter_pack_history_splits_by_target() -> None:
    history = [
        {"version": "1.0.0", "target": "dna", "notes": "DNA only"},
        {"version": "1.0.1", "target": "reporting", "notes": "Reporting only"},
        {"version": "1.0.2", "notes": "Updated via client portal"},
        {"version": "1.0.3", "notes": "Initialized pack"},
    ]
    dna = _filter_pack_history(history, "dna")
    reporting = _filter_pack_history(history, "reporting")
    assert [entry["version"] for entry in dna] == ["1.0.0", "1.0.2", "1.0.3"]
    assert [entry["version"] for entry in reporting] == ["1.0.1", "1.0.2"]


def test_history_table_rows_empty_colspan() -> None:
    admin_empty = _history_table_rows([], is_admin=True)
    assert "colspan='6'" in admin_empty
    viewer_empty = _history_table_rows([], is_admin=False)
    assert "colspan='5'" in viewer_empty
