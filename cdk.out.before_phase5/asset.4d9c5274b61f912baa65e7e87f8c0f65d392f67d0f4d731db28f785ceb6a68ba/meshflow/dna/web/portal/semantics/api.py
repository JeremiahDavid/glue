"""Field semantics API payloads for the portal."""

from __future__ import annotations

from typing import Any

from meshflow.dna.field_semantics import (
    build_assistant_field_semantics_context,
    discover_silver_columns,
    draft_differs_from_production,
    load_field_semantics_draft,
    load_field_semantics_workflow,
    load_operational_concept_catalog,
    load_production_field_semantics,
    preview_silver_entity,
    list_silver_entities,
    field_semantics_summary,
)
from meshflow.dna.settings import DnaSettings


def _mapping_index(mappings: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    index: dict[tuple[str, str], dict[str, Any]] = {}
    for item in mappings:
        if not isinstance(item, dict):
            continue
        entity = str(item.get("silver_entity") or "").strip().lower()
        column = str(item.get("column") or "").strip()
        if entity and column:
            index[(entity, column)] = item
    return index


def concepts_payload(settings: DnaSettings) -> dict[str, Any]:
    catalog = load_operational_concept_catalog()
    draft = load_field_semantics_draft(settings)
    return {
        "categories": catalog.get("categories") or [],
        "concepts": catalog.get("concepts") or [],
        "custom_concepts": draft.get("custom_concepts") or [],
    }


def entities_payload(settings: DnaSettings) -> dict[str, Any]:
    entities = list_silver_entities(settings)
    draft = load_field_semantics_draft(settings)
    mappings = draft.get("mappings") or []
    tagged_entities = {str(m.get("silver_entity") or "") for m in mappings}
    return {
        "source": settings.source,
        "entities": [
            {
                "name": name,
                "tagged_column_count": sum(
                    1 for m in mappings if str(m.get("silver_entity") or "") == name
                ),
            }
            for name in entities
        ],
        "tagged_entity_count": len(tagged_entities & set(entities)),
    }


def entity_detail_payload(settings: DnaSettings, entity: str) -> dict[str, Any]:
    entity_name = entity.strip().lower()
    columns = discover_silver_columns(settings, entity_name)
    rows = preview_silver_entity(settings, entity_name)
    draft = load_field_semantics_draft(settings)
    index = _mapping_index(draft.get("mappings") or [])

    column_payload: list[dict[str, Any]] = []
    for column in columns:
        sample = ""
        for row in rows:
            if not isinstance(row, dict):
                continue
            value = row.get(column)
            if value is not None and str(value).strip():
                sample = str(value)
                break
        mapping = index.get((entity_name, column), {})
        column_payload.append(
            {
                "column": column,
                "sample_value": sample,
                "concepts": list(mapping.get("concepts") or []),
                "notes": str(mapping.get("notes") or ""),
            }
        )

    return {
        "entity": entity_name,
        "source": settings.source,
        "columns": column_payload,
        "preview_rows": rows,
        "preview_limit": len(rows),
    }


def draft_payload(settings: DnaSettings) -> dict[str, Any]:
    draft = load_field_semantics_draft(settings)
    production = load_production_field_semantics(settings)
    workflow = load_field_semantics_workflow(settings)
    return {
        "draft": draft,
        "production": production,
        "workflow": {
            "active_version": workflow.get("active_version"),
            "draft_updated_at": workflow.get("draft_updated_at"),
        },
        "draft_summary": field_semantics_summary(draft),
        "production_summary": field_semantics_summary(production) if production else None,
        "draft_differs_from_production": draft_differs_from_production(settings),
        "assistant_context": build_assistant_field_semantics_context(settings),
    }
