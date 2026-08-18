"""Read bounded table previews from parsed spreadsheet regions."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from meshflow.spreadsheet.parser import _cell_value, _row_values

MAX_PREVIEW_ROWS = 100


def extract_table_preview(
    path: str | Path,
    *,
    sheet: str,
    data_start_row: int,
    data_end_row: int,
    min_col: int,
    max_col: int,
    headers: list[str] | None = None,
    max_rows: int = MAX_PREVIEW_ROWS,
) -> dict[str, Any]:
    """Return up to ``max_rows`` data rows for a detected table region."""
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
        if len(rows) >= max_rows:
            break
        values = [
            _cell_value(value)
            for value in _row_values(worksheet, row_idx, min_col=min_col, max_col=max_col)
        ]
        rows.append(values)

    workbook.close()
    truncated = total_rows > len(rows)
    return {
        "headers": list(headers or []),
        "rows": rows,
        "row_count": total_rows,
        "preview_row_count": len(rows),
        "truncated": truncated,
    }
