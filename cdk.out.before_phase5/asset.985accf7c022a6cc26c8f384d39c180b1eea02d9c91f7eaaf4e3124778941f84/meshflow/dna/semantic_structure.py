"""Silver-backed semantic structure proposal with connector hints and heuristics."""

from __future__ import annotations

from typing import Any

from meshflow.dna.field_semantics import discover_silver_columns, list_silver_entities
from meshflow.dna.settings import DnaSettings
from meshflow.storage.paths import prefix_path, silver_entity_prefix

_ENTITY_ROLES = frozenset({"fact", "dimension", "bridge", "reference"})
_DIMENSION_NAMES = frozenset(
    {
        "customers",
        "vendors",
        "items",
        "employees",
        "contacts",
        "accounts",
        "locations",
        "dimensions",
        "dimension_values",
        "currencies",
        "units_of_measure",
    }
)
_FK_COLUMN_TARGETS: dict[str, str] = {
    "customerid": "customers",
    "vendorid": "vendors",
    "itemid": "items",
    "employeeid": "employees",
    "accountid": "accounts",
    "locationid": "locations",
    "currencyid": "currencies",
}


def _silver_entity_has_data(settings: DnaSettings, entity: str) -> bool:
    entity_name = entity.strip().lower()
    if settings.s3_bucket:
        return bool(discover_silver_columns(settings, entity_name))
    path = prefix_path(
        settings.data_dir,
        silver_entity_prefix(settings.source, entity_name),
        "data.parquet",
    )
    return path.is_file()


def list_silver_catalog_entities(settings: DnaSettings) -> list[str]:
    """All silver entity names from the connector ingest catalog."""
    return sorted({name.strip().lower() for name in list_silver_entities(settings) if name.strip()})


def list_silver_entities_with_data(settings: DnaSettings) -> list[str]:
    """Silver entities from the connector catalog that have parquet data."""
    names = [name.strip().lower() for name in list_silver_entities(settings) if name.strip()]
    return sorted(name for name in names if _silver_entity_has_data(settings, name))


def _default_entity_role(silver_entity: str) -> str:
    name = silver_entity.strip().lower()
    if name.endswith("_lines") or name.endswith("_entries"):
        return "fact"
    if name in _DIMENSION_NAMES:
        return "dimension"
    return "reference"


def _line_header_candidates(line_entity: str) -> list[str]:
    if not line_entity.endswith("_lines"):
        return []
    stem = line_entity[:-6]
    candidates = [stem, f"{stem}s"]
    if stem.endswith("_line"):
        candidates.append(f"{stem[:-5]}s")
    return candidates


def _entity_index(entities: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        str(entity.get("silver_entity") or "").strip().lower(): entity
        for entity in entities
        if isinstance(entity, dict) and str(entity.get("silver_entity") or "").strip()
    }


def propose_entities_from_silver(
    silver_entities: list[str],
    hints: dict[str, Any],
) -> list[dict[str, Any]]:
    """Seed one proposed entity per silver table; apply connector/tenant hints when present."""
    hint_index = {
        str(item.get("silver_entity") or "").strip().lower(): item
        for item in hints.get("entities") or []
        if isinstance(item, dict) and str(item.get("silver_entity") or "").strip()
    }
    entities: list[dict[str, Any]] = []
    for silver_entity in sorted(set(silver_entities)):
        hint = hint_index.get(silver_entity, {})
        role = str(hint.get("role") or _default_entity_role(silver_entity)).strip().lower()
        if role not in _ENTITY_ROLES:
            role = _default_entity_role(silver_entity)
        entry: dict[str, Any] = {
            "id": str(hint.get("id") or silver_entity).strip().lower(),
            "silver_entity": silver_entity,
            "role": role,
            "status": "proposed",
        }
        for key in ("grain", "primary_key", "description", "citation"):
            value = str(hint.get(key) or "").strip()
            if value:
                entry[key] = value
        entities.append(entry)
    return entities


def _relationship_key(item: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(item.get("from_entity") or "").strip().lower(),
        str(item.get("from_column") or "").strip(),
        str(item.get("to_entity") or "").strip().lower(),
        str(item.get("to_column") or "").strip(),
    )


def _normalize_hint_relationships(
    relationships: list[Any],
    *,
    silver_entities: set[str],
    source: str,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in relationships:
        if not isinstance(item, dict):
            continue
        from_entity = str(item.get("from_entity") or "").strip().lower()
        to_entity = str(item.get("to_entity") or "").strip().lower()
        from_column = str(item.get("from_column") or "").strip()
        to_column = str(item.get("to_column") or "id").strip() or "id"
        if from_entity not in silver_entities or to_entity not in silver_entities:
            continue
        if not from_column:
            continue
        entry: dict[str, Any] = {
            "id": str(item.get("id") or f"rel_{from_entity}_{from_column}_{to_entity}").strip().lower(),
            "from_entity": from_entity,
            "from_column": from_column,
            "to_entity": to_entity,
            "to_column": to_column,
            "cardinality": str(item.get("cardinality") or "many_to_one").strip().lower(),
            "status": "proposed",
            "confidence": float(item.get("confidence") or 0.9),
        }
        for key in ("description", "citation"):
            value = str(item.get(key) or "").strip()
            if value:
                entry[key] = value
            elif source:
                entry.setdefault("citation", f"connector_knowledge/{source}/hints.yaml")
        normalized.append(entry)
    return normalized


def propose_heuristic_relationships(
    settings: DnaSettings,
    entities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Connector-agnostic APV2-style join heuristics verified against silver columns."""
    silver_entities = {
        str(entity.get("silver_entity") or "").strip().lower()
        for entity in entities
        if isinstance(entity, dict) and str(entity.get("silver_entity") or "").strip()
    }
    relationships: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()

    def add_relationship(
        *,
        rel_id: str,
        from_entity: str,
        from_column: str,
        to_entity: str,
        to_column: str = "id",
        description: str = "",
        confidence: float = 0.75,
    ) -> None:
        if from_entity not in silver_entities or to_entity not in silver_entities:
            return
        columns = discover_silver_columns(settings, from_entity)
        if from_column not in columns:
            return
        target_columns = discover_silver_columns(settings, to_entity)
        if to_column not in target_columns:
            return
        key = (from_entity, from_column, to_entity, to_column)
        if key in seen:
            return
        seen.add(key)
        relationships.append(
            {
                "id": rel_id,
                "from_entity": from_entity,
                "from_column": from_column,
                "to_entity": to_entity,
                "to_column": to_column,
                "cardinality": "many_to_one",
                "status": "proposed",
                "confidence": confidence,
                "description": description,
                "citation": "heuristic:apv2_foreign_key",
            }
        )

    for entity_name in sorted(silver_entities):
        columns = discover_silver_columns(settings, entity_name)
        column_lookup = {column.lower(): column for column in columns}

        if entity_name.endswith("_lines") and "documentid" in column_lookup:
            from_column = column_lookup["documentid"]
            for candidate in _line_header_candidates(entity_name):
                add_relationship(
                    rel_id=f"rel_{entity_name}_document",
                    from_entity=entity_name,
                    from_column=from_column,
                    to_entity=candidate,
                    description=f"{entity_name} line to document header",
                    confidence=0.8,
                )

        for column in columns:
            target = _FK_COLUMN_TARGETS.get(column.lower())
            if target:
                add_relationship(
                    rel_id=f"rel_{entity_name}_{column.lower()}",
                    from_entity=entity_name,
                    from_column=column,
                    to_entity=target,
                    description=f"{entity_name}.{column} to {target}.id",
                    confidence=0.78,
                )

    return relationships


def merge_relationships(
    heuristic_relationships: list[dict[str, Any]],
    hint_relationships: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Hint relationships override heuristics on the same join key."""
    merged: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for item in heuristic_relationships:
        merged[_relationship_key(item)] = dict(item)
    for item in hint_relationships:
        merged[_relationship_key(item)] = dict(item)
    return sorted(merged.values(), key=lambda item: str(item.get("id") or ""))


def build_questions_from_hints(hints: dict[str, Any]) -> list[dict[str, Any]]:
    questions: list[dict[str, Any]] = []
    for item in hints.get("questions") or []:
        if not isinstance(item, dict):
            continue
        entry: dict[str, Any] = {
            "id": str(item.get("id") or "").strip().lower(),
            "text": str(item.get("text") or "").strip(),
            "status": "open",
        }
        if item.get("blocks_publish"):
            entry["blocks_publish"] = True
        if entry["id"] and entry["text"]:
            questions.append(entry)
    return questions


def propose_semantic_structure(
    settings: DnaSettings,
    hints: dict[str, Any],
) -> dict[str, Any]:
    """Build entities and relationships from the silver catalog, hints, and join heuristics."""
    silver_entities = list_silver_catalog_entities(settings)
    if not silver_entities:
        raise ValueError("No silver entities in connector catalog — configure ingest entities first")

    entities = propose_entities_from_silver(silver_entities, hints)
    silver_set = set(silver_entities)
    hint_relationships = _normalize_hint_relationships(
        list(hints.get("relationships") or []),
        silver_entities=silver_set,
        source=settings.source.strip().lower(),
    )
    heuristic_relationships = propose_heuristic_relationships(settings, entities)
    relationships = merge_relationships(heuristic_relationships, hint_relationships)
    questions = build_questions_from_hints(hints)
    return {
        "entities": entities,
        "relationships": relationships,
        "questions": questions,
        "column_hints": hints.get("column_hints") if isinstance(hints.get("column_hints"), dict) else {},
        "silver_entity_count": len(silver_entities),
    }


def _column_hint_for(column: str, hints: dict[str, Any]) -> dict[str, Any] | None:
    if column in hints and isinstance(hints[column], dict):
        return hints[column]
    if column.endswith("Id") and "Id" in hints and isinstance(hints["Id"], dict):
        return dict(hints["Id"])
    return None


def build_attributes_for_entities(
    settings: DnaSettings,
    *,
    entity_names: set[str],
    column_hints: dict[str, Any],
    existing_pairs: set[tuple[str, str]],
    source: str,
) -> list[dict[str, Any]]:
    """Build attribute rows for entities not yet present in the draft."""
    attributes: list[dict[str, Any]] = []
    for entity_name in sorted(entity_names):
        columns = discover_silver_columns(settings, entity_name)
        for column in columns:
            pair = (entity_name, column)
            if pair in existing_pairs:
                continue
            existing_pairs.add(pair)
            hint = _column_hint_for(column, column_hints)
            if not hint:
                attributes.append(
                    {
                        "entity": entity_name,
                        "column": column,
                        "status": "proposed",
                    }
                )
                continue
            concepts = [str(c) for c in hint.get("concepts") or [] if str(c).strip()]
            entry: dict[str, Any] = {
                "entity": entity_name,
                "column": column,
                "status": "proposed",
            }
            if concepts:
                entry["concepts"] = concepts
            role = str(hint.get("role") or "").strip().lower()
            if role:
                entry["role"] = role
            entry["citation"] = f"connector_knowledge/{source}/hints.yaml#column_hints"
            attributes.append(entry)
    return attributes


def sync_semantic_draft_from_catalog(
    settings: DnaSettings,
    *,
    username: str = "system",
) -> dict[str, int]:
    """Add catalog silver entities and column attributes missing from the draft."""
    from meshflow.dna.semantic_knowledge_base import load_merged_semantic_hints
    from meshflow.dna.semantic_model import (
        load_semantic_model_draft,
        load_semantic_model_workflow,
        save_semantic_model_draft,
    )

    workflow = load_semantic_model_workflow(settings)
    if not workflow.get("init_completed"):
        return {"added_entities": 0, "added_attributes": 0}

    hints = load_merged_semantic_hints(settings)
    draft = load_semantic_model_draft(settings)
    catalog = list_silver_catalog_entities(settings)
    if not catalog:
        return {"added_entities": 0, "added_attributes": 0}

    entities = list(draft.get("entities") or [])
    existing_entities = {
        str(entity.get("silver_entity") or "").strip().lower()
        for entity in entities
        if isinstance(entity, dict) and str(entity.get("silver_entity") or "").strip()
    }
    missing = sorted(set(catalog) - existing_entities)
    added_entities = 0
    if missing:
        entities.extend(propose_entities_from_silver(missing, hints))
        draft["entities"] = entities
        added_entities = len(missing)

    existing_pairs = {
        (
            str(attribute.get("entity") or "").strip().lower(),
            str(attribute.get("column") or "").strip(),
        )
        for attribute in draft.get("attributes") or []
        if isinstance(attribute, dict)
    }
    column_hints = hints.get("column_hints") if isinstance(hints.get("column_hints"), dict) else {}
    model_entity_names = {
        str(entity.get("silver_entity") or "").strip().lower()
        for entity in draft.get("entities") or []
        if isinstance(entity, dict) and str(entity.get("silver_entity") or "").strip()
    }
    new_attributes = build_attributes_for_entities(
        settings,
        entity_names=model_entity_names,
        column_hints=column_hints,
        existing_pairs=existing_pairs,
        source=settings.source.strip().lower(),
    )
    if new_attributes:
        draft.setdefault("attributes", [])
        draft["attributes"].extend(new_attributes)

    if added_entities or new_attributes:
        save_semantic_model_draft(settings, draft, username=username)

    return {"added_entities": added_entities, "added_attributes": len(new_attributes)}
