"""DNA portal section navigation — catalog, mappings, and semantic browser."""

from __future__ import annotations

from typing import Any

from meshflow.dna.field_semantics import list_silver_entities
from meshflow.dna.settings import DnaSettings
from meshflow.dna.web.portal.catalog import (
    CATALOG_ROOT,
    catalog_table_label,
    list_catalog_tables,
)

DNA_ROOT = "/portal/dna"
MAPPINGS_ROOT = f"{DNA_ROOT}/mappings"
DNA_ENGINE_ROOT = f"{DNA_ROOT}/engine"
SEMANTICS_ROOT = "/portal/semantics"
SEMANTIC_BUILDER_ROOT = "/portal/semantics/builder"

_SOURCE_LABELS = {
    "dbc": "Business Central",
    "qbo": "QuickBooks Online",
    "qbd": "QuickBooks Desktop",
}

SideNavItem = tuple[str, str] | tuple[str, str, tuple[Any, ...]]


def source_label(source: str) -> str:
    key = source.strip().lower()
    return _SOURCE_LABELS.get(key, key.replace("_", " ").title() or "Source")


def _humanize_entity(name: str) -> str:
    return name.replace("_", " ").title()


def _catalog_nav_children(settings: DnaSettings) -> tuple[tuple[str, str], ...]:
    return tuple(
        (f"{CATALOG_ROOT}/{output.id}", catalog_table_label(output))
        for output in list_catalog_tables(settings)
    )


def _browser_nav_children(settings: DnaSettings) -> tuple[Any, ...]:
    entities = list_silver_entities(settings)
    if not entities:
        return ()
    source = settings.source.strip().lower()
    entity_children: tuple[tuple[str, str], ...] = tuple(
        (f"{SEMANTICS_ROOT}/{entity}", _humanize_entity(entity)) for entity in entities
    )
    source_item: SideNavItem = (SEMANTICS_ROOT, source_label(source), entity_children)
    return (source_item,)


def dna_section_nav(settings: DnaSettings | None) -> tuple[Any, ...]:
    if settings is None:
        return (
            (CATALOG_ROOT, "Catalog"),
            (MAPPINGS_ROOT, "Semantic Mappings"),
            (SEMANTIC_BUILDER_ROOT, "Semantic Builder"),
            (SEMANTICS_ROOT, "Semantic Browser"),
            (DNA_ENGINE_ROOT, "DNA Engine"),
        )

    catalog_children = _catalog_nav_children(settings)
    browser_children = _browser_nav_children(settings)
    catalog_item: SideNavItem = (
        (CATALOG_ROOT, "Catalog", catalog_children)
        if catalog_children
        else (CATALOG_ROOT, "Catalog")
    )
    browser_item: SideNavItem = (
        (SEMANTICS_ROOT, "Semantic Browser", browser_children)
        if browser_children
        else (SEMANTICS_ROOT, "Semantic Browser")
    )
    return (
        catalog_item,
        (MAPPINGS_ROOT, "Semantic Mappings"),
        (SEMANTIC_BUILDER_ROOT, "Semantic Builder"),
        browser_item,
        (DNA_ENGINE_ROOT, "DNA Engine"),
    )
