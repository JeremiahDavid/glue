"""Budgeted row sampling for Spreadsheet Engine AI induction."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from meshflow.spreadsheet.parser import _cell_value, _row_values
from meshflow.spreadsheet.preview import _align_row

# Up to 0.5 GiB of raw row data for local verification / structural analysis.
DEFAULT_MAX_SAMPLE_BYTES = 512 * 1024 * 1024
# Separate, smaller cap for LLM oracle / synthesize prompts.
DEFAULT_ORACLE_PROMPT_BYTES = 2 * 1024 * 1024
DEFAULT_WINDOW_ROWS = 400
MIN_WINDOW_ROWS = 40


def max_sample_bytes() -> int:
    raw = os.getenv("MESHFLOW_SPREADSHEET_MAX_SAMPLE_BYTES", "").strip()
    if raw.isdigit():
        return max(1, int(raw))
    return DEFAULT_MAX_SAMPLE_BYTES


def oracle_prompt_bytes() -> int:
    raw = os.getenv("MESHFLOW_SPREADSHEET_ORACLE_PROMPT_BYTES", "").strip()
    if raw.isdigit():
        return max(1, int(raw))
    return DEFAULT_ORACLE_PROMPT_BYTES


def estimate_row_bytes(row: list[Any]) -> int:
    return len(json.dumps(row, default=str, ensure_ascii=False).encode("utf-8"))


def extract_table_sample(
    path: str | Path,
    *,
    sheet: str,
    data_start_row: int,
    data_end_row: int,
    min_col: int,
    max_col: int,
    headers: list[str] | None = None,
    header_col_offsets: list[int] | None = None,
    max_bytes: int | None = None,
) -> dict[str, Any]:
    """Read table rows until ``max_bytes`` is reached (default 0.5 GiB)."""
    budget = max_bytes if max_bytes is not None else max_sample_bytes()
    workbook = load_workbook(path, data_only=True)
    try:
        worksheet = workbook[sheet]
    except KeyError:
        workbook.close()
        return {
            "headers": list(headers or []),
            "rows": [],
            "row_count": 0,
            "sample_row_count": 0,
            "sample_bytes": 0,
            "truncated": False,
            "total_row_count": 0,
        }

    total_rows = max(0, int(data_end_row) - int(data_start_row) + 1)
    rows: list[list[Any]] = []
    used_bytes = 0
    truncated = False
    for row_idx in range(int(data_start_row), int(data_end_row) + 1):
        values = [
            _cell_value(value)
            for value in _row_values(worksheet, row_idx, min_col=min_col, max_col=max_col)
        ]
        values = _align_row(values, header_col_offsets)
        row_size = estimate_row_bytes(values)
        if rows and used_bytes + row_size > budget:
            truncated = True
            break
        rows.append(values)
        used_bytes += row_size

    workbook.close()
    return {
        "headers": list(headers or []),
        "rows": rows,
        "row_count": len(rows),
        "sample_row_count": len(rows),
        "sample_bytes": used_bytes,
        "truncated": truncated or len(rows) < total_rows,
        "total_row_count": total_rows,
    }


def _window_byte_size(rows: list[list[Any]]) -> int:
    return sum(estimate_row_bytes(row) for row in rows)


def select_oracle_windows(
    rows: list[list[Any]],
    *,
    max_bytes: int | None = None,
    window_rows: int = DEFAULT_WINDOW_ROWS,
) -> list[dict[str, Any]]:
    """Pick representative row windows for LLM oracle/synthesis within a byte budget."""
    if not rows:
        return []

    budget = max_bytes if max_bytes is not None else oracle_prompt_bytes()
    size = max(MIN_WINDOW_ROWS, window_rows)
    total = len(rows)
    if total <= size:
        chunk = rows[:]
        if _window_byte_size(chunk) <= budget:
            return [{"start": 0, "end": total, "rows": chunk}]

    anchor_starts: list[int] = [0]
    if total > size * 2:
        anchor_starts.extend([total // 3, (2 * total) // 3])
    if total > size:
        anchor_starts.append(max(0, total - size))
    anchor_starts = sorted(dict.fromkeys(anchor_starts))

    windows: list[dict[str, Any]] = []
    used = 0
    for start in anchor_starts:
        end = min(total, start + size)
        chunk = rows[start:end]
        chunk_bytes = _window_byte_size(chunk)
        if used + chunk_bytes > budget:
            remaining = budget - used
            if remaining <= 0:
                break
            trimmed: list[list[Any]] = []
            for row in chunk:
                row_bytes = estimate_row_bytes(row)
                if trimmed and used + _window_byte_size(trimmed) + row_bytes > budget:
                    break
                trimmed.append(row)
                if _window_byte_size(trimmed) >= remaining:
                    break
            if not trimmed:
                break
            chunk = trimmed
            chunk_bytes = _window_byte_size(chunk)
        windows.append({"start": start, "end": start + len(chunk), "rows": chunk})
        used += chunk_bytes
        if used >= budget:
            break
    return windows


def flatten_oracle_windows(windows: list[dict[str, Any]]) -> list[list[Any]]:
    out: list[list[Any]] = []
    for window in windows:
        out.extend(list(window.get("rows") or []))
    return out
