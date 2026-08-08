"""Initialize a draft semantic model from silver profiling and source documentation packs."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from meshflow.dna.field_semantics import (
    discover_silver_columns,
    list_silver_entities,
    load_production_field_semantics,
)
from meshflow.dna.semantic_model import (
    load_semantic_model_draft,
    load_semantic_model_workflow,
    load_source_semantic_pack,
    save_semantic_model_draft,
    save_semantic_model_workflow,
)
from meshflow.dna.settings import DnaSettings


def _column_hint_for(column: str, hints: dict[str, Any]) -> dict[str, Any] | None:
    if column in hints and isinstance(hints[column], dict):
        return hints[column]
    # Suffix / camelCase heuristics for Id columns
    if column.endswith("Id") and "Id" in hints and isinstance(hints["Id"], dict):
        base = hints["Id"]
        return dict(base)
    return None


def _merge_field_semantics_attributes(
    settings: DnaSettings,
    attributes: list[dict[str, Any]],
    *,
    seen: set[tuple[str, str]],
) -> None:
    semantics = load_production_field_semantics(settings)
    if not semantics:
        return
    for mapping in semantics.get("mappings") or []:
        if not isinstance(mapping, dict):
            continue
        entity = str(mapping.get("silver_entity") or "").strip().lower()
        column = str(mapping.get("column") or "").strip()
        concepts = [str(c) for c in mapping.get("concepts") or [] if str(c).strip()]
        if not entity or not column or not concepts:
            continue
        pair = (entity, column)
        if pair in seen:
            continue
        seen.add(pair)
        entry: dict[str, Any] = {
            "entity": entity,
            "column": column,
            "concepts": concepts,
            "status": "approved",
            "notes": str(mapping.get("notes") or "").strip() or "Imported from published field semantics",
        }
        attributes.append(entry)


def build_semantic_model_from_source(
    settings: DnaSettings,
    *,
    username: str = "system",
    merge_existing: bool = True,
    enable_llm_tagging: bool = True,
) -> dict[str, Any]:
    """Profile silver tables and apply connector source semantic pack proposals.

    LLM column tagging is optional. Portal HTTP init should pass
    ``enable_llm_tagging=False`` (API Gateway ~29s limit) and enqueue tagging
    asynchronously; DNA Step Functions / offline jobs can keep it enabled.
    """
    source = settings.source.strip().lower()
    pack = load_source_semantic_pack(source)
    if pack is None:
        raise ValueError(f"No source semantic pack for connector {source!r}")

    silver_entities = set(list_silver_entities(settings))
    if not silver_entities:
        raise ValueError("No silver entities available — run ingest and silver consolidate first")

    entities: list[dict[str, Any]] = []
    relationships: list[dict[str, Any]] = []
    attributes: list[dict[str, Any]] = []
    questions: list[dict[str, Any]] = []
    seen_attrs: set[tuple[str, str]] = set()

    for item in pack.get("entities") or []:
        if not isinstance(item, dict):
            continue
        silver_entity = str(item.get("silver_entity") or "").strip().lower()
        if silver_entity not in silver_entities:
            continue
        entry: dict[str, Any] = {
            "id": str(item.get("id") or silver_entity).strip().lower(),
            "silver_entity": silver_entity,
            "role": str(item.get("role") or "reference").strip().lower(),
            "status": "proposed",
        }
        for key in ("grain", "primary_key", "description", "citation"):
            value = str(item.get(key) or "").strip()
            if value:
                entry[key] = value
        entities.append(entry)

    for item in pack.get("relationships") or []:
        if not isinstance(item, dict):
            continue
        from_entity = str(item.get("from_entity") or "").strip().lower()
        to_entity = str(item.get("to_entity") or "").strip().lower()
        if from_entity not in silver_entities or to_entity not in silver_entities:
            continue
        entry: dict[str, Any] = {
            "id": str(item.get("id") or "").strip().lower(),
            "from_entity": from_entity,
            "from_column": str(item.get("from_column") or "").strip(),
            "to_entity": to_entity,
            "to_column": str(item.get("to_column") or "").strip(),
            "cardinality": str(item.get("cardinality") or "many_to_one").strip().lower(),
            "status": "proposed",
            "confidence": float(item.get("confidence") or 0.85),
        }
        for key in ("description", "citation"):
            value = str(item.get(key) or "").strip()
            if value:
                entry[key] = value
        relationships.append(entry)

    column_hints = pack.get("column_hints") or {}
    if not isinstance(column_hints, dict):
        column_hints = {}

    model_entity_names = {str(e.get("silver_entity") or "") for e in entities}
    for entity_name in sorted(model_entity_names & silver_entities):
        columns = discover_silver_columns(settings, entity_name)
        for column in columns:
            pair = (entity_name, column)
            if pair in seen_attrs:
                continue
            hint = _column_hint_for(column, column_hints)
            if not hint:
                seen_attrs.add(pair)
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
            if pack.get("source"):
                entry["citation"] = f"packs/source_semantic/{source}.yaml#column_hints"
            seen_attrs.add(pair)
            attributes.append(entry)

    for item in pack.get("questions") or []:
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

    _merge_field_semantics_attributes(settings, attributes, seen=seen_attrs)

    llm_result: dict[str, Any] = {"tagged_count": 0, "skipped_count": 0, "reason": "disabled"}
    if enable_llm_tagging:
        from meshflow.dna.semantic_column_tagger import apply_llm_tags_to_attributes

        try:
            llm_result = apply_llm_tags_to_attributes(
                settings,
                attributes,
                entity_names=model_entity_names,
            )
        except Exception as exc:  # noqa: BLE001 — never fail pack init on LLM errors
            llm_result = {
                "tagged_count": 0,
                "skipped_count": 0,
                "reason": "error",
                "error": str(exc),
            }

    if merge_existing:
        existing = load_semantic_model_draft(settings)
        if existing.get("entities") or existing.get("relationships"):
            approved_entities = {
                str(e.get("silver_entity") or ""): e
                for e in existing.get("entities") or []
                if isinstance(e, dict) and str(e.get("status") or "") == "approved"
            }
            for entity in entities:
                silver = str(entity.get("silver_entity") or "")
                if silver in approved_entities:
                    entity.update({k: v for k, v in approved_entities[silver].items() if k != "silver_entity"})

    description = str(pack.get("description") or "").strip()
    draft: dict[str, Any] = {
        "version": "0.1.0",
        "status": "draft",
        "source": source,
        "updated_at": datetime.now(UTC).isoformat(),
        "updated_by": username,
        "description": description,
        "entities": entities,
        "attributes": attributes,
        "relationships": relationships,
        "questions": questions,
    }

    saved = save_semantic_model_draft(settings, draft, username=username)
    workflow = load_semantic_model_workflow(settings)
    workflow["init_completed"] = True
    workflow["init_at"] = saved["updated_at"]
    workflow["init_by"] = username
    save_semantic_model_workflow(settings, workflow)

    return {
        "status": "initialized",
        "entity_count": len(entities),
        "relationship_count": len(relationships),
        "attribute_count": len(attributes),
        "question_count": len(questions),
        "source_pack": source,
        "llm_tagging": llm_result,
    }


def run_semantic_init(
    settings: DnaSettings,
    *,
    username: str = "system",
    force: bool = False,
    enable_llm_tagging: bool = True,
) -> dict[str, Any]:
    workflow = load_semantic_model_workflow(settings)
    if workflow.get("init_completed") and not force:
        draft = load_semantic_model_draft(settings)
        return {
            "status": "skipped",
            "reason": "init_already_completed",
            "entity_count": len(draft.get("entities") or []),
        }
    return build_semantic_model_from_source(
        settings,
        username=username,
        merge_existing=not force,
        enable_llm_tagging=enable_llm_tagging,
    )


def enrich_semantic_model_llm_tags(
    settings: DnaSettings,
    *,
    username: str = "system",
) -> dict[str, Any]:
    """Apply LLM concept tags to an existing draft (safe for background workers)."""
    from meshflow.dna.semantic_column_tagger import apply_llm_tags_to_attributes

    draft = load_semantic_model_draft(settings)
    attributes = list(draft.get("attributes") or [])
    entity_names = {
        str(entity.get("silver_entity") or "").strip().lower()
        for entity in draft.get("entities") or []
        if isinstance(entity, dict) and str(entity.get("silver_entity") or "").strip()
    }
    try:
        llm_result = apply_llm_tags_to_attributes(
            settings,
            attributes,
            entity_names=entity_names,
        )
    except Exception as exc:  # noqa: BLE001 — background enrichment must not raise to CFN/API
        return {"status": "error", "error": str(exc)}

    draft["attributes"] = attributes
    draft["updated_at"] = datetime.now(UTC).isoformat()
    draft["updated_by"] = username
    save_semantic_model_draft(settings, draft, username=username)
    return {"status": "enriched", "llm_tagging": llm_result}


def maybe_auto_semantic_init(
    settings: DnaSettings,
    *,
    username: str = "system",
) -> dict[str, Any]:
    """Run semantic init once when silver exists and init has not completed."""
    from meshflow.dna.semantic_model import ensure_semantic_model_seed, load_semantic_model_workflow

    ensure_semantic_model_seed(settings)
    workflow = load_semantic_model_workflow(settings)
    if workflow.get("init_completed"):
        return {"status": "skipped", "reason": "init_already_completed"}
    if not list_silver_entities(settings):
        return {"status": "skipped", "reason": "no_silver_entities"}
    return run_semantic_init(settings, username=username, force=False)
