from __future__ import annotations

from meshflow.silver.glue_runner import resolve_glue_consolidate_runtime


def test_resolve_glue_consolidate_runtime_uses_explicit_args() -> None:
    source, full_rebuild = resolve_glue_consolidate_runtime(
        {"MESHFLOW_SOURCE": "qbo", "full_rebuild": "true"}
    )
    assert source == "qbo"
    assert full_rebuild is True


def test_resolve_glue_consolidate_runtime_defaults() -> None:
    source, full_rebuild = resolve_glue_consolidate_runtime({})
    assert source == ""
    assert full_rebuild is False


def test_resolve_glue_consolidate_runtime_ignores_flag_like_source() -> None:
    source, full_rebuild = resolve_glue_consolidate_runtime(
        {"MESHFLOW_SOURCE": "--scriptLocation"}
    )
    assert source == ""
    assert full_rebuild is False
