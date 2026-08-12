"""DNA portal section navigation — source browser, engine, catalog, legacy tools."""

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
SEMANTIC_BUILDER_KEYS = f"{SEMANTIC_BUILDER_ROOT}/keys"
SEMANTIC_BUILDER_RELATIONSHIPS = f"{SEMANTIC_BUILDER_ROOT}/relationships"
SEMANTIC_BUILDER_TAGS = f"{SEMANTIC_BUILDER_ROOT}/tags"
SEMANTIC_BUILDER_DECISIONS = f"{SEMANTIC_BUILDER_ROOT}/decisions"
SOURCE_DOCS_INSPECTOR_ROOT = "/portal/semantics/source-docs"

_SOURCE_BROWSER_LABEL = "Source Browser"
_DNA_CATALOG_LABEL = "DNA Catalog"
_SEMANTIC_BUILDER_LABEL = "Semantic Builder (legacy)"
_SEMANTIC_BROWSER_LABEL = "Semantic Browser (legacy)"


def source_docs_inspector_path(source: str | None = None) -> str:
    key = (source or "").strip().lower()
    if not key:
        return SOURCE_DOCS_INSPECTOR_ROOT
    return f"{SOURCE_DOCS_INSPECTOR_ROOT}/{key}"


BUILDER_STEP_PATHS: dict[str, str] = {
    "keys": SEMANTIC_BUILDER_KEYS,
    "relationships": SEMANTIC_BUILDER_RELATIONSHIPS,
    "tags": SEMANTIC_BUILDER_TAGS,
    "decisions": SEMANTIC_BUILDER_DECISIONS,
}

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
            (SOURCE_DOCS_INSPECTOR_ROOT, _SOURCE_BROWSER_LABEL),
            (DNA_ENGINE_ROOT, "DNA Engine"),
            (CATALOG_ROOT, _DNA_CATALOG_LABEL),
            (SEMANTIC_BUILDER_ROOT, _SEMANTIC_BUILDER_LABEL),
            (SEMANTICS_ROOT, _SEMANTIC_BROWSER_LABEL),
        )

    catalog_children = _catalog_nav_children(settings)
    browser_children = _browser_nav_children(settings)
    catalog_item: SideNavItem = (
        (CATALOG_ROOT, _DNA_CATALOG_LABEL, catalog_children)
        if catalog_children
        else (CATALOG_ROOT, _DNA_CATALOG_LABEL)
    )
    browser_item: SideNavItem = (
        (SEMANTICS_ROOT, _SEMANTIC_BROWSER_LABEL, browser_children)
        if browser_children
        else (SEMANTICS_ROOT, _SEMANTIC_BROWSER_LABEL)
    )
    return (
        (SOURCE_DOCS_INSPECTOR_ROOT, _SOURCE_BROWSER_LABEL),
        (DNA_ENGINE_ROOT, "DNA Engine"),
        catalog_item,
        (SEMANTIC_BUILDER_ROOT, _SEMANTIC_BUILDER_LABEL),
        browser_item,
    )
