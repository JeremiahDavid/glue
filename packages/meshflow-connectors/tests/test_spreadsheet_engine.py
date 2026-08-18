"""Tests for spreadsheet workbook parsing."""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook

from meshflow.spreadsheet.parser import parse_workbook
from meshflow.spreadsheet.profiler import profile_tables
from meshflow.spreadsheet.interpret import interpret_tables


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
