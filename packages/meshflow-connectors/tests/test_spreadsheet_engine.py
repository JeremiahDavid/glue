"""Tests for spreadsheet workbook parsing."""

from __future__ import annotations

from pathlib import Path

import pytest
from openpyxl import Workbook

from meshflow.spreadsheet.parser import parse_workbook
from meshflow.spreadsheet.preview import MAX_PREVIEW_ROWS, extract_table_preview
from meshflow.spreadsheet.profiler import profile_tables
from meshflow.spreadsheet.interpret import interpret_tables


def test_extract_table_preview_limits_rows(tmp_path: Path) -> None:
    path = tmp_path / "preview.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "Items"
    ws.append(["Item", "Price"])
    for idx in range(150):
        ws.append([f"I{idx}", idx + 1])
    wb.save(path)

    payload = parse_workbook(path)
    table = payload["tables"][0]
    preview = extract_table_preview(
        path,
        sheet=table["sheet"],
        data_start_row=table["data_start_row"],
        data_end_row=table["data_end_row"],
        min_col=table["min_col"],
        max_col=table["max_col"],
        headers=table["headers"],
        max_rows=MAX_PREVIEW_ROWS,
    )
    assert preview["preview_row_count"] == MAX_PREVIEW_ROWS
    assert preview["row_count"] == 150
    assert preview["truncated"] is True
    assert preview["rows"][0] == ["I0", 1]


def test_load_table_preview_reads_upload(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MESHFLOW_DATA_DIR", str(tmp_path))

    from meshflow.spreadsheet.jobs import create_job, load_table_preview, run_parse, store_upload

    path = tmp_path / "sample.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "Customers"
    ws.append(["Customer ID", "Company"])
    ws.append(["C1", "Acme"])
    ws.append(["C2", "Beta"])
    wb.save(path)

    job = create_job(filename="sample.xlsx", username="poc")
    store_upload(job["job_id"], filename="sample.xlsx", body=path.read_bytes())
    run_parse(job["job_id"])

    preview = load_table_preview(job["job_id"], "t0")
    assert preview is not None
    assert preview["headers"] == ["customer_id", "company"]
    assert preview["preview_row_count"] == 2
    assert preview["rows"] == [["C1", "Acme"], ["C2", "Beta"]]


def test_parse_workbook_detects_table_after_report_preamble(tmp_path: Path) -> None:
    path = tmp_path / "price_list.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(["List Price Sheet as of 07/01/27"])
    ws.append(["Phone: +1 425 555 0100", None, None, None, None, None, None, None, None, None, None, None, None, "Page", 1])
    ws.append([None] * 7)
    ws.append(["CRONUS International Ltd."])
    ws.append([None] * 7)
    ws.append(["All Customers"])
    ws.append([None] * 7)
    ws.append([None] * 7)
    ws.append(["No.", "Description", "Unit of Measure Code", "Unit Price"])
    ws.append(["1896-S", "ATHENS Desk", None, None])
    ws.append([None, None, "PCS", 1000.8])
    ws.append(["1900-S", "PARIS Guest Chair, black", None, None])
    ws.append([None, None, "PCS", 192.8])
    wb.save(path)

    payload = parse_workbook(path, filename="price_list.xlsx")
    assert payload["table_count"] == 1
    table = payload["tables"][0]
    assert table["headers"][:2] == ["no", "description"]
    assert table["header_row"] == 9
    assert table["row_count"] >= 4


def test_parse_workbook_detects_table(tmp_path: Path) -> None:
    path = tmp_path / "sample.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "Customers"
    ws.append(["Customer ID", "Company", "Email"])
    ws.append(["C1", "Acme", "a@acme.test"])
    ws.append(["C2", "Beta", "b@beta.test"])
    wb.save(path)

    payload = parse_workbook(path, filename="sample.xlsx")
    assert payload["table_count"] == 1
    table = payload["tables"][0]
    assert table["headers"] == ["customer_id", "company", "email"]
    assert table["row_count"] == 2

    profile = profile_tables(payload)
    assert profile["table_count"] == 1
    columns = profile["tables"][0]["columns"]
    assert columns[0]["likely_key"] is True

    report = interpret_tables(payload, profile, invoke=False)
    assert report["table_count"] == 1
    proposal = report["tables"][0]
    assert proposal["entity_name"]
    assert proposal["schema"]


def test_approve_table_saves_catalog_entry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MESHFLOW_DATA_DIR", str(tmp_path))

    from meshflow.spreadsheet.jobs import (
        approve_table,
        create_job,
        list_catalog_entries,
        load_catalog_entry,
        save_job,
        update_report_tables,
    )

    job = create_job(filename="sample.xlsx", username="poc")
    job = save_job({**job, "status": "ready"})
    table = {
        "table_id": "t0",
        "entity_name": "customers",
        "purpose": "Customer master",
        "grain": "one row per customer",
        "confidence": 0.9,
        "status": "pending_review",
        "schema": [{"name": "customer_id", "type": "string", "description": "id", "is_key": True}],
        "profiling": {"columns": []},
        "source": {"sheet": "Customers", "row_count": 2},
    }
    update_report_tables(job["job_id"], [table])
    approved = approve_table(job["job_id"], "t0", username="poc")
    assert approved["status"] == "approved"

    entries = list_catalog_entries()
    assert len(entries) == 1
    entry = load_catalog_entry(entries[0]["catalog_id"])
    assert entry is not None
    assert entry["entity_name"] == "customers"
    assert entry["filename"] == "sample.xlsx"
    assert entry["proposal"]["status"] == "approved"


def test_load_report_rebuilds_from_table_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MESHFLOW_DATA_DIR", str(tmp_path))

    from meshflow.spreadsheet.jobs import (
        create_job,
        load_report,
        save_job,
    )
    from meshflow.storage.paths import spreadsheet_engine_job_table_key

    job = create_job(filename="sample.xlsx", username="poc")
    job = save_job({**job, "status": "ready", "table_ids": ["t0"]})
    table = {
        "table_id": "t0",
        "entity_name": "customers",
        "purpose": "Customer master",
        "grain": "one row per customer",
        "confidence": 0.9,
        "status": "pending_review",
        "schema": [{"name": "customer_id", "type": "string", "description": "id", "is_key": True}],
        "profiling": {"columns": []},
        "source": {"sheet": "Customers", "row_count": 2},
    }
    from meshflow.spreadsheet.jobs import _write_json

    _write_json(spreadsheet_engine_job_table_key(job["job_id"], "t0"), table)

    report = load_report(job["job_id"])
    assert report is not None
    assert report.get("table_count") == 1
    assert report["tables"][0]["entity_name"] == "customers"


def test_load_report_discovers_table_files_without_table_ids(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MESHFLOW_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("MESHFLOW_S3_BUCKET", raising=False)

    from meshflow.spreadsheet.jobs import _write_json, create_job, load_report, save_job
    from meshflow.storage.paths import spreadsheet_engine_job_table_key

    job = create_job(filename="sample.xlsx", username="poc")
    job = save_job({**job, "status": "ready", "table_ids": []})
    table = {
        "table_id": "t0",
        "entity_name": "customers",
        "schema": [{"name": "customer_id", "type": "string"}],
    }
    _write_json(spreadsheet_engine_job_table_key(job["job_id"], "t0"), table)

    report = load_report(job["job_id"])
    assert report is not None
    assert report.get("table_count") == 1
