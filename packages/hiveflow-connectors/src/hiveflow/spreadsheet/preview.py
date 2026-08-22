"""Read bounded table previews from parsed spreadsheet regions."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from meshflow.spreadsheet.parser import _cell_value, _row_values

MAX_PREVIEW_ROWS = 100


def _align_row(row: list[Any], header_col_offsets: list[int] | None) -> list[Any]:
    if not header_col_offsets:
        return row
    return [
        row[offset] if 0 <= offset < len(row) else None for offset in header_col_offsets
    ]


def extract_table_preview(
    path: str | Path,
    *,
    sheet: str,
    data_start_row: int,
    data_end_row: int,
    min_col: int,
    max_col: int,
    headers: list[str] | None = None,
    header_col_offsets: list[int] | None = None,
    max_rows: int | None = MAX_PREVIEW_ROWS,
) -> dict[str, Any]:
    """Return data rows for a detected table region.

  When ``max_rows`` is ``None``, all rows in the region are returned.
    """
    workbook = load_workbook(path, data_only=True)
    try:
        worksheet = workbook[sheet]
    except KeyError:
        workbook.close()
        return {
            "headers": list(headers or []),
            "rows": [],
            "row_count": 0,
            "preview_row_count": 0,
            "truncated": False,
        }

    total_rows = max(0, int(data_end_row) - int(data_start_row) + 1)
    rows: list[list[Any]] = []
    for row_idx in range(int(data_start_row), int(data_end_row) + 1):
        if max_rows is not None and len(rows) >= max_rows:
            break
        values = [
            _cell_value(value)
            for value in _row_values(worksheet, row_idx, min_col=min_col, max_col=max_col)
        ]
        rows.append(_align_row(values, header_col_offsets))

    workbook.close()
    truncated = max_rows is not None and total_rows > len(rows)
    return {
        "headers": list(headers or []),
        "rows": rows,
        "row_count": total_rows,
        "preview_row_count": len(rows),
        "truncated": truncated,
    }
