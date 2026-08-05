"""Resolve portal pages from the company reporting config."""

from __future__ import annotations

from typing import Any

from meshflow.dna.settings import DnaSettings
from meshflow.dna.web.reporting import (
    default_reporting_pack,
    load_production_reporting,
    load_reporting_boilerplate,
)


def _normalize_portal_path(path: str | None, page_id: str) -> str:
    value = (path or "").strip()
    if not value:
        value = f"/portal/{page_id.strip().lower()}"
    if not value.startswith("/"):
        value = f"/{value}"
    if value != "/" and value.endswith("/"):
        value = value.rstrip("/")
    return value


def load_reporting_layout(
    settings: DnaSettings,
    *,
    override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Pinned production reporting config, or boilerplate fallback for local tooling."""
    if override is not None:
        return override
    try:
        return load_production_reporting(settings)
    except FileNotFoundError:
        try:
            return load_reporting_boilerplate(
                pack_id=settings.reporting_config_id,
                version="1.0.0",
            )
        except Exception:  # noqa: BLE001
            return default_reporting_pack(
                pack_id=settings.reporting_config_id,
                version="1.0.0",
                status="draft",
            )


def list_reporting_pages(
    settings: DnaSettings,
    *,
    override: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    layout = load_reporting_layout(settings, override=override)
    pages: list[dict[str, Any]] = []
    for raw in layout.get("pages", []):
        if not isinstance(raw, dict):
            continue
        page_id = str(raw.get("id") or "").strip()
        title = str(raw.get("title") or "").strip()
        if not page_id or not title:
            continue
        page = dict(raw)
        page["id"] = page_id
        page["title"] = title
        page["path"] = _normalize_portal_path(str(raw.get("path") or ""), page_id)
        page["description"] = str(raw.get("description") or "")
        pages.append(page)
    return pages


def find_reporting_page(
    settings: DnaSettings,
    path: str,
    *,
    override: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    target = _normalize_portal_path(path, "page")
    for page in list_reporting_pages(settings, override=override):
        if page["path"] == target:
            return page
    return None


def reporting_data_menu(
    settings: DnaSettings,
    *,
    override: dict[str, Any] | None = None,
) -> tuple[tuple[str, str], ...]:
    return tuple(
        (page["path"], page["title"])
        for page in list_reporting_pages(settings, override=override)
    )


def reporting_quick_links(
    settings: DnaSettings,
    *,
    override: dict[str, Any] | None = None,
) -> tuple[tuple[str, str, str], ...]:
    """Overview quick links — all configured pages except the summary/home page."""
    links: list[tuple[str, str, str]] = []
    for page in list_reporting_pages(settings, override=override):
        if page["path"] in {"/portal", "/portal/"}:
            continue
        links.append((page["path"], page["title"], page.get("description") or ""))
    return tuple(links)


def page_source_output(
    page: dict[str, Any] | None,
    *,
    kind: str = "table",
    default: str,
) -> str:
    if not page:
        return default
    key = "tables" if kind == "table" else "charts"
    items = page.get(key) or []
    if not isinstance(items, list):
        return default
    for item in items:
        if isinstance(item, dict):
            source = str(item.get("source_output") or "").strip()
            if source:
                return source
    return default
