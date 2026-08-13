from __future__ import annotations

from meshflow.ingest.storage import resolve_run_path, run_stamp
from meshflow.project_config import resolve_fanout_entity_names


class _Settings:
    s3_bucket = "bucket"
    s3_prefix = "raw/dbc"
    data_dir = None  # type: ignore[assignment]


def test_resolve_run_path_uses_shared_run_id() -> None:
    settings = _Settings()
    assert resolve_run_path(settings, "20260730T120000Z") == "raw/dbc/20260730T120000Z"


def test_resolve_fanout_entity_names_for_dbc_full() -> None:
    names = resolve_fanout_entity_names("dbc", {"entity_bundle": "full"})
    assert "customers" in names
    assert "general_ledger_entries" in names
    assert len(names) >= 70


def test_resolve_fanout_entity_names_for_qbo() -> None:
    names = resolve_fanout_entity_names("qbo", {"entity_bundle": "v1_accounting"})
    assert names == ["customers", "invoices", "open_invoices", "payments"]


def test_run_stamp_format() -> None:
    assert len(run_stamp()) == 16
    assert "T" in run_stamp()
