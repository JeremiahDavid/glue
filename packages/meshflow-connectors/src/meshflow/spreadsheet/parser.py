"""Detect table regions in Excel workbooks."""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.worksheet.worksheet import Worksheet

JOB_KIND = "spreadsheet_engine_parse"
MAX_SAMPLE_ROWS = 25
MIN_DATA_ROWS = 2
MIN_DATA_COLS = 2


def _cell_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def _row_values(sheet: Worksheet, row_idx: int, *, min_col: int, max_col: int) -> list[Any]:
    return [
        _cell_value(sheet.cell(row=row_idx, column=col_idx).value)
        for col_idx in range(min_col, max_col + 1)
    ]


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


def _row_is_empty(values: list[Any]) -> bool:
    return all(_is_blank(v) for v in values)


def _normalize_header(value: Any, *, index: int) -> str:
    if value is None:
        return f"column_{index + 1}"
    text = str(value).strip()
    if not text:
        return f"column_{index + 1}"
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", text).strip("_").lower()
    return slug or f"column_{index + 1}"


def _sheet_bounds(sheet: Worksheet) -> tuple[int, int, int, int]:
    min_row = sheet.min_row or 1
    max_row = sheet.max_row or 1
    min_col = sheet.min_column or 1
    max_col = sheet.max_column or 1
    return min_row, max_row, min_col, max_col


def _detect_regions(sheet: Worksheet) -> list[dict[str, Any]]:
    min_row, max_row, min_col, max_col = _sheet_bounds(sheet)
    if max_row < min_row or max_col < min_col:
        return []

    regions: list[dict[str, Any]] = []
    row = min_row
    while row <= max_row:
        header_values = _row_values(sheet, row, min_col=min_col, max_col=max_col)
        if _row_is_empty(header_values):
            row += 1
            continue

        data_start = row + 1
        data_end = row
        blank_streak = 0
        for data_row in range(data_start, max_row + 1):
            values = _row_values(sheet, data_row, min_col=min_col, max_col=max_col)
            if _row_is_empty(values):
                blank_streak += 1
                if blank_streak >= 2:
                    break
                continue
            blank_streak = 0
            data_end = data_row

        data_rows = data_end - row
        if data_rows < MIN_DATA_ROWS:
            row += 1
            continue

        non_empty_cols = [
            idx
            for idx, header in enumerate(header_values)
            if not _is_blank(header)
            or any(
                not _is_blank(
                    _row_values(sheet, r, min_col=min_col, max_col=max_col)[idx]
                )
                for r in range(data_start, data_end + 1)
            )
        ]
        if len(non_empty_cols) < MIN_DATA_COLS:
            row += 1
            continue

        col_start = min_col + non_empty_cols[0]
        col_end = min_col + non_empty_cols[-1]
        headers = [
            _normalize_header(header_values[idx], index=idx) for idx in non_empty_cols
        ]
        sample_rows: list[list[Any]] = []
        for sample_row in range(data_start, min(data_end + 1, data_start + MAX_SAMPLE_ROWS)):
            row_vals = _row_values(sheet, sample_row, min_col=col_start, max_col=col_end)
            if _row_is_empty(row_vals):
                continue
            sample_rows.append(row_vals)

        regions.append(
            {
                "sheet": sheet.title,
                "header_row": row,
                "data_start_row": data_start,
                "data_end_row": data_end,
                "min_col": col_start,
                "max_col": col_end,
                "row_count": data_rows,
                "column_count": len(headers),
                "headers": headers,
                "sample_rows": sample_rows,
            }
        )
        row = data_end + 1

    return regions


def parse_workbook(path: str | Path, *, filename: str = "") -> dict[str, Any]:
    """Parse an Excel workbook into table candidates."""
    workbook_path = Path(path)
    workbook = load_workbook(workbook_path, read_only=True, data_only=True)
    tables: list[dict[str, Any]] = []
    table_index = 0
    for sheet_name in workbook.sheetnames:
        sheet = workbook[sheet_name]
        for region in _detect_regions(sheet):
            table_id = f"t{table_index}"
            table_index += 1
            tables.append(
                {
                    "table_id": table_id,
                    "sheet": region["sheet"],
                    "header_row": region["header_row"],
                    "data_start_row": region["data_start_row"],
                    "data_end_row": region["data_end_row"],
                    "min_col": region["min_col"],
                    "max_col": region["max_col"],
                    "row_count": region["row_count"],
                    "column_count": region["column_count"],
                    "headers": region["headers"],
                    "sample_rows": region["sample_rows"],
                }
            )
    workbook.close()
    return {
        "kind": JOB_KIND,
        "filename": filename or workbook_path.name,
        "sheet_count": len(workbook.sheetnames),
        "table_count": len(tables),
        "tables": tables,
    }
