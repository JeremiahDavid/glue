"""Initialize a draft semantic model from silver profiling and connector knowledge."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from meshflow.dna.field_semantics import load_production_field_semantics
from meshflow.dna.semantic_knowledge_base import load_tenant_semantic_overrides, merge_semantic_hints
from meshflow.dna.semantic_source_profile import ensure_latest_source_profile, latest_profile_to_hints
from meshflow.dna.semantic_model import (
    load_semantic_model_draft,
    load_semantic_model_workflow,
    merge_preserved_questions,
    save_semantic_model_draft,
    save_semantic_model_workflow,
)
from meshflow.dna.semantic_structure import (
    build_attributes_for_entities,
    propose_semantic_structure,
)
from meshflow.dna.settings import DnaSettings


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


def _build_attributes(
    settings: DnaSettings,
    *,
    model_entity_names: set[str],
    column_hints: dict[str, Any],
    column_tags: dict[str, Any] | None = None,
    entity_column_hints: dict[str, Any] | None = None,
    source: str,
) -> list[dict[str, Any]]:
    seen_attrs: set[tuple[str, str]] = set()
    attributes = build_attributes_for_entities(
        settings,
        entity_names=model_entity_names,
        column_hints=column_hints,
        column_tags=column_tags,
        existing_pairs=seen_attrs,
        source=source,
        entity_column_hints=entity_column_hints,
    )
    _merge_field_semantics_attributes(settings, attributes, seen=seen_attrs)
    return attributes


def build_semantic_model_from_source(
    settings: DnaSettings,
    *,
    username: str = "system",
    merge_existing: bool = True,
    enable_llm_tagging: bool = True,
) -> dict[str, Any]:
    """Profile silver tables and apply connector knowledge + tenant overrides.

    LLM column tagging is optional. Portal HTTP init should pass
    ``enable_llm_tagging=False`` (API Gateway ~29s limit) and enqueue tagging
    asynchronously; DNA Step Functions / offline jobs can keep it enabled.
    """
    source = settings.source.strip().lower()
    baseline_result = ensure_latest_source_profile(settings, source)
    hints = merge_semantic_hints(
        latest_profile_to_hints(baseline_result["profile"]),
        load_tenant_semantic_overrides(settings),
    )
    structure = propose_semantic_structure(settings, hints)

    entities = structure["entities"]
    relationships = structure["relationships"]
    questions = structure["questions"]
    column_hints = structure.get("column_hints") or {}
    column_tags = hints.get("column_tags") if isinstance(hints.get("column_tags"), dict) else {}
    entity_column_hints = (
        hints.get("entity_column_hints") if isinstance(hints.get("entity_column_hints"), dict) else {}
    )
    fk_attributes = list(structure.get("attributes") or [])
    model_entity_names = {str(entity.get("silver_entity") or "") for entity in entities}
    attributes = _build_attributes(
        settings,
        model_entity_names=model_entity_names,
        column_hints=column_hints if isinstance(column_hints, dict) else {},
        column_tags=column_tags,
        entity_column_hints=entity_column_hints,
        source=source,
    )
    existing_pairs = {
        (str(a.get("entity") or ""), str(a.get("column") or "")) for a in attributes if isinstance(a, dict)
    }
    for item in fk_attributes:
        if not isinstance(item, dict):
            continue
        pair = (str(item.get("entity") or ""), str(item.get("column") or ""))
        if pair in existing_pairs:
            for attribute in attributes:
                if (
                    str(attribute.get("entity") or "") == pair[0]
                    and str(attribute.get("column") or "") == pair[1]
                ):
                    attribute.update(
                        {
                            k: v
                            for k, v in item.items()
                            if k in {"role", "status", "citation", "fk_target_entity", "fk_target_column"}
                        }
                    )
            continue
        attributes.append(item)
        existing_pairs.add(pair)

    llm_result: dict[str, Any] = {"tagged_count": 0, "skipped_count": 0, "reason": "deferred_to_step_3"}
    if enable_llm_tagging:
        from meshflow.dna.semantic_column_tagger import (
            _entity_context_by_name,
            apply_llm_tags_to_attributes,
        )

        try:
            llm_result = apply_llm_tags_to_attributes(
                settings,
                attributes,
                entity_names=model_entity_names,
                entity_context_by_name=_entity_context_by_name(entities),
            )
        except Exception as exc:  # noqa: BLE001 — never fail pack init on LLM errors
            llm_result = {
                "tagged_count": 0,
                "skipped_count": 0,
                "reason": "error",
                "error": str(exc),
            }

    existing = load_semantic_model_draft(settings)
    if merge_existing:
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

    questions = merge_preserved_questions(questions, existing.get("questions") or [])

    description = str(hints.get("description") or "").strip()
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
    workflow["current_step"] = "keys"
    workflow["steps_completed"] = {"keys": False, "relationships": False, "tags": False}
    save_semantic_model_workflow(settings, workflow)

    from meshflow.dna.semantic_structure import sync_semantic_draft_from_catalog

    sync_semantic_draft_from_catalog(settings, username=username)

    return {
        "status": "initialized",
        "entity_count": len(entities),
        "silver_entity_count": structure.get("silver_entity_count", len(entities)),
        "relationship_count": len(relationships),
        "attribute_count": len(attributes),
        "question_count": len(questions),
        "source": source,
        "llm_tagging": llm_result,
        "baseline_profile": {
            "built": bool(baseline_result.get("built")),
            "generated_at": (baseline_result.get("profile") or {}).get("generated_at"),
            "approved_build_count": (baseline_result.get("profile") or {}).get("approved_build_count"),
        },
    }


def regenerate_keys_from_profiling(
    settings: DnaSettings,
    *,
    username: str = "system",
) -> dict[str, Any]:
    """Re-profile silver and refresh proposed PK/FK rows without rebuilding column tags."""
    from meshflow.dna.semantic_knowledge_base import load_merged_semantic_hints
    from meshflow.dna.semantic_model import (
        load_semantic_model_draft,
        load_semantic_model_workflow,
        merge_preserved_questions,
        save_semantic_model_draft,
        save_semantic_model_workflow,
    )
    from meshflow.dna.semantic_structure import propose_semantic_structure

    hints = load_merged_semantic_hints(settings)
    structure = propose_semantic_structure(settings, hints)
    new_entities = list(structure.get("entities") or [])
    fk_attributes = list(structure.get("attributes") or [])
    new_questions = list(structure.get("questions") or [])

    draft = load_semantic_model_draft(settings)
    existing_entities_by_silver = {
        str(entity.get("silver_entity") or "").strip().lower(): entity
        for entity in draft.get("entities") or []
        if isinstance(entity, dict) and str(entity.get("silver_entity") or "").strip()
    }
    approved_entities = {
        str(entity.get("silver_entity") or "").strip().lower(): entity
        for entity in draft.get("entities") or []
        if isinstance(entity, dict) and str(entity.get("status") or "") == "approved"
    }

    for entity in new_entities:
        if not isinstance(entity, dict):
            continue
        silver = str(entity.get("silver_entity") or "").strip().lower()
        existing = existing_entities_by_silver.get(silver)
        if existing and str(existing.get("primary_key_status") or "").strip().lower() == "approved":
            if existing.get("primary_key"):
                entity["primary_key"] = existing.get("primary_key")
            entity["primary_key_status"] = "approved"
        if silver in approved_entities:
            approved = approved_entities[silver]
            entity.update({k: v for k, v in approved.items() if k != "silver_entity"})

    new_fk_by_pair = {
        (
            str(attribute.get("entity") or "").strip().lower(),
            str(attribute.get("column") or "").strip(),
        ): attribute
        for attribute in fk_attributes
        if isinstance(attribute, dict)
    }

    kept_attributes: list[dict[str, Any]] = []
    for attribute in draft.get("attributes") or []:
        if not isinstance(attribute, dict):
            continue
        entity = str(attribute.get("entity") or "").strip().lower()
        column = str(attribute.get("column") or "").strip()
        role = str(attribute.get("role") or "").strip().lower()
        status = str(attribute.get("status") or "proposed").strip().lower()
        if role == "foreign_key" and status != "approved":
            if (entity, column) in new_fk_by_pair:
                continue
        kept_attributes.append(attribute)

    kept_pairs = {
        (
            str(attribute.get("entity") or "").strip().lower(),
            str(attribute.get("column") or "").strip(),
        )
        for attribute in kept_attributes
        if isinstance(attribute, dict)
    }
    for pair, fk_attribute in new_fk_by_pair.items():
        if pair not in kept_pairs:
            kept_attributes.append(fk_attribute)

    draft["entities"] = new_entities
    draft["attributes"] = kept_attributes
    draft["questions"] = merge_preserved_questions(new_questions, draft.get("questions") or [])
    draft["updated_by"] = username
    draft["updated_at"] = datetime.now(UTC).isoformat()

    saved = save_semantic_model_draft(settings, draft, username=username)
    workflow = load_semantic_model_workflow(settings)
    workflow["init_completed"] = True
    workflow["current_step"] = "keys"
    steps_completed = dict(workflow.get("steps_completed") or {})
    steps_completed["keys"] = False
    workflow["steps_completed"] = steps_completed
    save_semantic_model_workflow(settings, workflow)

    return {
        "status": "keys_regenerated",
        "entity_count": len(new_entities),
        "attribute_count": len(kept_attributes),
        "fk_proposed_count": len(fk_attributes),
        "question_count": len(draft["questions"]),
        "silver_entity_count": structure.get("silver_entity_count", len(new_entities)),
        "source": settings.source.strip().lower(),
        "updated_at": saved["updated_at"],
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
    if workflow.get("init_completed") and force:
        return regenerate_keys_from_profiling(settings, username=username)
    return build_semantic_model_from_source(
        settings,
        username=username,
        merge_existing=not force,
        enable_llm_tagging=enable_llm_tagging,
    )


def run_semantic_profiling_job(
    settings: DnaSettings,
    *,
    username: str = "system",
    force: bool = False,
) -> dict[str, Any]:
    """Run semantic init/profiling (for background Lambda workers)."""
    from meshflow.dna.semantic_model import update_profiling_workflow

    try:
        result = run_semantic_init(
            settings,
            username=username,
            force=force,
            enable_llm_tagging=False,
        )
        if result.get("status") != "skipped":
            update_profiling_workflow(settings, status="completed", username=username)
        else:
            update_profiling_workflow(settings, status="idle", username=username)
        return result
    except Exception as exc:
        update_profiling_workflow(settings, status="error", username=username, error=str(exc))
        raise


def enrich_semantic_model_llm_tags(
    settings: DnaSettings,
    *,
    username: str = "system",
) -> dict[str, Any]:
    """Apply LLM concept tags to an existing draft (safe for background workers)."""
    from meshflow.dna.semantic_column_tagger import apply_llm_tags_to_attributes

    draft = load_semantic_model_draft(settings)
    attributes = list(draft.get("attributes") or [])
    entities = draft.get("entities") or []
    entity_names = {
        str(entity.get("silver_entity") or "").strip().lower()
        for entity in entities
        if isinstance(entity, dict) and str(entity.get("silver_entity") or "").strip()
    }
    from meshflow.dna.semantic_column_tagger import _entity_context_by_name

    try:
        llm_result = apply_llm_tags_to_attributes(
            settings,
            attributes,
            entity_names=entity_names,
            entity_context_by_name=_entity_context_by_name(entities),
        )
    except Exception as exc:  # noqa: BLE001 — background enrichment must not raise to CFN/API
        return {"status": "error", "error": str(exc)}

    draft["attributes"] = attributes
    draft["updated_at"] = datetime.now(UTC).isoformat()
    draft["updated_by"] = username
    save_semantic_model_draft(settings, draft, username=username)
    return {"status": "enriched", "llm_tagging": llm_result}


def run_semantic_llm_tagging_job(
    settings: DnaSettings,
    *,
    username: str = "system",
) -> dict[str, Any]:
    """Run LLM column tagging (for background Lambda workers)."""
    from meshflow.dna.semantic_model import update_tagging_workflow

    try:
        result = enrich_semantic_model_llm_tags(settings, username=username)
        if result.get("status") == "error":
            update_tagging_workflow(
                settings,
                status="error",
                username=username,
                error=str(result.get("error") or "Semantic tagging failed"),
            )
        else:
            update_tagging_workflow(settings, status="completed", username=username)
        return result
    except Exception as exc:
        update_tagging_workflow(settings, status="error", username=username, error=str(exc))
        raise


def maybe_auto_semantic_init(
    settings: DnaSettings,
    *,
    username: str = "system",
) -> dict[str, Any]:
    """Run semantic init once when silver exists and init has not completed."""
    from meshflow.dna.semantic_model import ensure_semantic_model_seed, load_semantic_model_workflow
    from meshflow.dna.semantic_structure import list_silver_entities_with_data

    ensure_semantic_model_seed(settings)
    workflow = load_semantic_model_workflow(settings)
    if workflow.get("init_completed"):
        return {"status": "skipped", "reason": "init_already_completed"}
    if not list_silver_entities_with_data(settings):
        return {"status": "skipped", "reason": "no_silver_entities"}
    return run_semantic_init(settings, username=username, force=False)
