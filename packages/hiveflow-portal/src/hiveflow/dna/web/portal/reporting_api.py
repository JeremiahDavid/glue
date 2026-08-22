"""Config-driven JSON API for reporting gold outputs."""

from __future__ import annotations

from typing import Any

from hiveflow.dna.settings import DnaSettings
from hiveflow.dna.web.portal.reporting_layout import find_reporting_page, list_reporting_pages
from hiveflow.dna.web.portal.reporting_render import query_chart, query_table


def fetch_output_rows(
    settings: DnaSettings,
    output_id: str,
    *,
    limit: int | None = None,
    sort_column: str | None = None,
    sort_direction: str = "desc",
) -> dict[str, Any]:
    table_config: dict[str, Any] = {"source_output": output_id}
    if limit is not None:
        table_config["limit"] = limit
    if sort_column:
        table_config["sort"] = [{"column": sort_column, "direction": sort_direction}]
    result = query_table(settings, table_config)
    result["output_id"] = result.pop("source_output")
    return result


def list_reporting_pages_json(settings: DnaSettings) -> list[dict[str, Any]]:
    pages: list[dict[str, Any]] = []
    for page in list_reporting_pages(settings):
        pages.append(
            {
                "id": page.get("id"),
                "title": page.get("title"),
                "path": page.get("path"),
                "pillar": page.get("pillar"),
                "chart_catalog": bool(page.get("chart_catalog")),
                "has_sections": bool(page.get("sections")),
                "table_count": len(page.get("tables") or []),
                "chart_count": len(page.get("charts") or []),
            }
        )
    return pages


def fetch_page_data(settings: DnaSettings, path: str) -> dict[str, Any]:
    page = find_reporting_page(settings, path)
    if not page:
        raise KeyError(f"No reporting page at {path!r}")

    payload: dict[str, Any] = {
        "page_id": page.get("id"),
        "title": page.get("title"),
        "path": page.get("path"),
        "description": page.get("description"),
        "chart_catalog": bool(page.get("chart_catalog")),
        "tables": [],
        "charts": [],
    }

    for table in page.get("tables") or []:
        if not isinstance(table, dict):
            continue
        entry = dict(table)
        if entry.get("source_output"):
            entry["data"] = query_table(settings, entry)
        payload["tables"].append(entry)

    for chart in page.get("charts") or []:
        if not isinstance(chart, dict):
            continue
        entry = dict(chart)
        if entry.get("source_output"):
            entry["data"] = query_chart(settings, entry)
        payload["charts"].append(entry)

    return payload
