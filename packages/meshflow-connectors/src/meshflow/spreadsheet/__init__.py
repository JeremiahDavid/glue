"""Spreadsheet Engine — Excel parse, profile, and Bedrock interpretation."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from meshflow.spreadsheet.interpret import interpret_tables
    from meshflow.spreadsheet.parser import parse_workbook
    from meshflow.spreadsheet.profiler import profile_tables

__all__ = ["parse_workbook", "profile_tables", "interpret_tables"]


def __getattr__(name: str):
    if name == "parse_workbook":
        from meshflow.spreadsheet.parser import parse_workbook

        return parse_workbook
    if name == "profile_tables":
        from meshflow.spreadsheet.profiler import profile_tables

        return profile_tables
    if name == "interpret_tables":
        from meshflow.spreadsheet.interpret import interpret_tables

        return interpret_tables
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
