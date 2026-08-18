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
    assert entry["catalog_id"] == "sample__customers"


def test_compute_input_shape_hash_stable(tmp_path: Path) -> None:
    from meshflow.spreadsheet.transform import compute_input_shape

    shape_a = compute_input_shape(
        {"sheet": "Customers", "headers": ["Customer ID", "Company"]}
    )
    shape_b = compute_input_shape(
        {"sheet": "Customers", "headers": ["Customer ID", "Company"]}
    )
    assert shape_a["shape_hash"] == shape_b["shape_hash"]
    assert shape_a["column_count"] == 2


def test_apply_transformation_rename_and_cast() -> None:
    from meshflow.spreadsheet.transform import apply_transformation

    headers = ["Customer Name", "Amount"]
    rows = [["Acme", "10"], ["Beta", "20.5"]]
    spec = {
        "version": 1,
        "steps": [
            {"op": "rename_columns", "mapping": {"Customer Name": "customer_name"}},
            {"op": "cast", "columns": {"customer_name": "string", "Amount": "number"}},
        ],
        "output_shape": {
            "schema": [
                {"name": "customer_name", "type": "string"},
                {"name": "Amount", "type": "number"},
            ]
        },
    }
    out_rows, out_headers = apply_transformation(rows, headers, spec)
    assert out_headers == ["customer_name", "Amount"]
    assert out_rows[0][0] == "Acme"
    assert out_rows[1][1] == 20.5


def test_approve_transformation_writes_knowledge(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MESHFLOW_DATA_DIR", str(tmp_path))

    from meshflow.spreadsheet.jobs import (
        approve_transformation,
        create_job,
        load_knowledge_entry,
        save_job,
        update_report_tables,
    )
    from meshflow.spreadsheet.transform import compute_input_shape

    job = create_job(filename="sample.xlsx", username="poc")
    job = save_job({**job, "status": "ready"})
    input_shape = compute_input_shape({"sheet": "Customers", "headers": ["customer_id", "company"]})
    transformation = {
        "version": 1,
        "steps": [{"op": "rename_columns", "mapping": {"customer_id": "customer_id"}}],
        "input_shape": input_shape,
        "output_shape": {"entity_name": "customers", "grain": "one row per customer", "schema": []},
    }
    table = {
        "table_id": "t0",
        "entity_name": "customers",
        "transformation": transformation,
        "transformation_status": "pending_review",
        "schema": [{"name": "customer_id", "type": "string"}],
    }
    update_report_tables(job["job_id"], [table])
    approve_transformation(job["job_id"], "t0", username="poc")
    kb = load_knowledge_entry("sample__customers")
    assert kb is not None
    assert kb["entity_name"] == "customers"
    assert kb["transformation"]["version"] == 1


def test_edit_transformation_resets_pending_review(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MESHFLOW_DATA_DIR", str(tmp_path))

    from meshflow.spreadsheet.jobs import create_job, edit_transformation, load_table, save_job, update_report_tables

    job = create_job(filename="sample.xlsx")
    job = save_job({**job, "status": "ready"})
    table = {
        "table_id": "t0",
        "entity_name": "customers",
        "transformation": {"version": 1, "steps": []},
        "transformation_status": "approved",
    }
    update_report_tables(job["job_id"], [table])
    edited = edit_transformation(
        job["job_id"],
        "t0",
        {"version": 1, "steps": [{"op": "rename_columns", "mapping": {"A": "a"}}]},
    )
    assert edited["transformation_status"] == "pending_review"
    stored = load_table(job["job_id"], "t0")
    assert stored is not None
    assert stored["transformation_status"] == "pending_review"


def test_reupload_updates_last_upload_at(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MESHFLOW_DATA_DIR", str(tmp_path))

    from meshflow.spreadsheet.jobs import (
        approve_table,
        approve_transformation,
        create_job,
        link_job_to_catalog,
        load_catalog_entry,
        record_upload_on_catalog,
        run_parse,
        save_job,
        store_upload,
        update_report_tables,
    )
    from meshflow.spreadsheet.transform import compute_input_shape

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

    input_shape = compute_input_shape({"sheet": "Customers", "headers": ["customer_id", "company"]})
    transformation = {
        "version": 1,
        "steps": [],
        "input_shape": input_shape,
        "output_shape": {"entity_name": "customers", "schema": []},
    }
    table = {
        "table_id": "t0",
        "entity_name": "customers",
        "status": "pending_review",
        "transformation": transformation,
        "transformation_status": "pending_review",
        "schema": [{"name": "customer_id", "type": "string"}],
    }
    update_report_tables(job["job_id"], [table])
    approve_transformation(job["job_id"], "t0", username="poc")
    approve_table(job["job_id"], "t0", username="poc")

    entry = load_catalog_entry("sample__customers")
    assert entry is not None

    job2 = create_job(filename="sample.xlsx", username="poc", linked_catalog_id="sample__customers")
    link_job_to_catalog(job2["job_id"], "sample__customers")
    record_upload_on_catalog(
        "sample__customers",
        job_id=job2["job_id"],
        uploaded_by="poc",
        input_shape_hash=input_shape["shape_hash"],
    )
    entry = load_catalog_entry("sample__customers")
    assert entry is not None
    assert entry.get("last_upload_at")
    assert entry.get("last_upload_job_id") == job2["job_id"]
    assert len(entry.get("upload_history") or []) >= 2


def test_reload_pipeline_validates_without_ai(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MESHFLOW_DATA_DIR", str(tmp_path))

    from meshflow.spreadsheet.jobs import (
        approve_table,
        approve_transformation,
        create_job,
        load_catalog_entry,
        load_table,
        run_interpret,
        run_parse,
        run_profile,
        run_propose,
        store_upload,
        update_report_tables,
    )
    from meshflow.spreadsheet.transform import compute_input_shape

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

    input_shape = compute_input_shape({"sheet": "Customers", "headers": ["customer_id", "company"]})
    transformation = {
        "version": 1,
        "steps": [{"op": "rename_columns", "mapping": {}}],
        "input_shape": input_shape,
        "output_shape": {
            "entity_name": "customers",
            "grain": "one row per customer",
            "schema": [
                {"name": "customer_id", "type": "string"},
                {"name": "company", "type": "string"},
            ],
        },
    }
    table = {
        "table_id": "t0",
        "entity_name": "customers",
        "purpose": "Customers",
        "grain": "one row per customer",
        "status": "approved",
        "schema": transformation["output_shape"]["schema"],
        "transformation": transformation,
        "transformation_status": "approved",
    }
    update_report_tables(job["job_id"], [table])
    approve_transformation(job["job_id"], "t0", username="poc")
    approve_table(job["job_id"], "t0", username="poc")

    job2 = create_job(filename="sample.xlsx", username="poc", linked_catalog_id="sample__customers")
    store_upload(job2["job_id"], filename="sample.xlsx", body=path.read_bytes())
    run_parse(job2["job_id"])
    run_profile(job2["job_id"])
    run_interpret(job2["job_id"])
    run_propose(job2["job_id"])

    reloaded = load_table(job2["job_id"], "t0")
    assert reloaded is not None
    assert reloaded.get("reload_mode") is True
    assert reloaded.get("reload_validation_status") == "passed"
    assert reloaded.get("transformation_status") == "approved"


def test_validate_output_schema_detects_missing_column() -> None:
    from meshflow.spreadsheet.reload import validate_output_schema

    ok, issues = validate_output_schema(
        ["customer_id"],
        [{"name": "customer_id"}, {"name": "company"}],
    )
    assert not ok
    assert any("company" in item for item in issues)


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
