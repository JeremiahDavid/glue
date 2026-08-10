"""Source semantic model — entities, attributes, relationships between silver and gold."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from meshflow.dna.field_semantics import (
    list_silver_entities,
    load_field_semantics_draft,
    load_operational_concept_catalog,
    load_production_field_semantics,
    save_field_semantics_draft,
)
from meshflow.dna.settings import DnaSettings
from meshflow.dna.store import (
    read_json_artifact,
    read_yaml_artifact,
    write_json_artifact,
    write_yaml_artifact,
)
from meshflow.storage.paths import (
    governance_semantic_model_draft_key,
    governance_semantic_model_key,
    governance_semantic_model_manifest_key,
    governance_semantic_model_workflow_key,
)

SOURCE_SEMANTIC_PACK_DIR = "source_semantic"
_MAX_SCHEMA_ERRORS = 5
_ENTITY_ROLES = frozenset({"fact", "dimension", "bridge", "reference"})
_ITEM_STATUSES = frozenset({"proposed", "approved", "rejected"})
_QUESTION_STATUSES = frozenset({"open", "resolved", "deferred"})
DOCUMENT_LATER_CHOICE_ID = "document_later"
QUESTION_ACTION_TYPES = frozenset(
    {"primary_key", "foreign_key", "relationship", "column_tag", "acknowledge"}
)
_ATTRIBUTE_ROLES = frozenset(
    {"foreign_key", "measure", "identifier", "dimension", "date", "status"}
)
_CARDINALITIES = frozenset({"many_to_one", "one_to_many", "one_to_one", "many_to_many"})

# Minimum coverage before gold publish is allowed.
_MIN_APPROVED_FACT_ENTITIES = 1
_MIN_APPROVED_RELATIONSHIPS = 1
_MIN_ATTRIBUTE_TAG_RATIO = 0.15
BUILDER_STEPS = ("keys", "relationships", "tags")


def semantic_model_schema_path() -> Path:
    return Path(__file__).resolve().parent / "schema" / "semantic-model.schema.json"


def source_semantic_pack_path(source: str) -> Path:
    connector = source.strip().lower()
    return Path(__file__).resolve().parent / "packs" / SOURCE_SEMANTIC_PACK_DIR / f"{connector}.yaml"


@lru_cache(maxsize=1)
def _semantic_model_validator() -> Draft202012Validator:
    schema_path = semantic_model_schema_path()
    if not schema_path.is_file():
        raise FileNotFoundError(f"Semantic model schema not found: {schema_path}")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise ValueError(f"Invalid semantic-model.schema.json: {exc.message}") from exc
    return Draft202012Validator(schema)


def _format_schema_path(error: Any) -> str:
    parts = [str(part) for part in error.absolute_path]
    return ".".join(parts) if parts else "(root)"


def validate_semantic_model_schema(payload: dict[str, Any]) -> None:
    if not isinstance(payload, dict):
        raise ValueError("Semantic model must be a mapping")

    validator = _semantic_model_validator()
    errors = sorted(validator.iter_errors(payload), key=lambda err: list(err.absolute_path))
    if not errors:
        return

    lines: list[str] = []
    for error in errors[:_MAX_SCHEMA_ERRORS]:
        path = _format_schema_path(error)
        lines.append(f"{path}: {error.message}")
    suffix = ""
    if len(errors) > _MAX_SCHEMA_ERRORS:
        suffix = f" (+{len(errors) - _MAX_SCHEMA_ERRORS} more)"
    raise ValueError("Semantic model schema error — " + "; ".join(lines) + suffix)


def load_source_semantic_pack(source: str) -> dict[str, Any] | None:
    """Load connector-standard semantic hints (legacy alias for knowledge-base hints)."""
    from meshflow.dna.semantic_knowledge_base import load_connector_standard_hints

    payload = load_connector_standard_hints(source)
    if not payload:
        return None
    return payload


def _normalize_semantic_model(payload: dict[str, Any], *, settings: DnaSettings) -> dict[str, Any]:
    normalized: dict[str, Any] = {
        "version": str(payload.get("version") or "0.1.0").strip(),
        "status": str(payload.get("status") or "draft").strip().lower(),
        "source": str(payload.get("source") or settings.source).strip().lower(),
        "updated_at": str(payload.get("updated_at") or datetime.now(UTC).isoformat()),
        "updated_by": str(payload.get("updated_by") or ""),
        "description": str(payload.get("description") or "").strip(),
        "entities": [],
        "attributes": [],
        "relationships": [],
        "questions": [],
    }
    if normalized["status"] not in {"draft", "production"}:
        raise ValueError("status must be 'draft' or 'production'")

    entities: list[dict[str, Any]] = []
    seen_entities: set[str] = set()
    for item in payload.get("entities") or []:
        if not isinstance(item, dict):
            continue
        entity_id = str(item.get("id") or "").strip().lower()
        silver_entity = str(item.get("silver_entity") or "").strip().lower()
        role = str(item.get("role") or "").strip().lower()
        status = str(item.get("status") or "proposed").strip().lower()
        if not entity_id or not silver_entity:
            raise ValueError("entities require id and silver_entity")
        if role not in _ENTITY_ROLES:
            raise ValueError(f"entities[{entity_id}].role must be one of {_ENTITY_ROLES}")
        if status not in _ITEM_STATUSES:
            raise ValueError(f"entities[{entity_id}].status must be one of {_ITEM_STATUSES}")
        if entity_id in seen_entities:
            raise ValueError(f"Duplicate entity id: {entity_id!r}")
        seen_entities.add(entity_id)
        entry: dict[str, Any] = {
            "id": entity_id,
            "silver_entity": silver_entity,
            "role": role,
            "status": status,
        }
        for key in ("grain", "primary_key", "description", "citation"):
            value = str(item.get(key) or "").strip()
            if value:
                entry[key] = value
        pk_stats = item.get("pk_stats")
        if isinstance(pk_stats, dict):
            entry["pk_stats"] = pk_stats
        pk_status = str(item.get("primary_key_status") or "").strip().lower()
        if pk_status:
            if pk_status not in _ITEM_STATUSES:
                raise ValueError(f"entities[{entity_id}].primary_key_status invalid")
            entry["primary_key_status"] = pk_status
        entities.append(entry)
    normalized["entities"] = entities

    attributes: list[dict[str, Any]] = []
    seen_attrs: set[tuple[str, str]] = set()
    for item in payload.get("attributes") or []:
        if not isinstance(item, dict):
            continue
        entity = str(item.get("entity") or "").strip().lower()
        column = str(item.get("column") or "").strip()
        status = str(item.get("status") or "proposed").strip().lower()
        if not entity or not column:
            raise ValueError("attributes require entity and column")
        pair = (entity, column)
        if pair in seen_attrs:
            raise ValueError(f"Duplicate attribute for {entity}.{column}")
        seen_attrs.add(pair)
        if status not in _ITEM_STATUSES:
            raise ValueError(f"attributes[{entity}.{column}].status invalid")
        concepts = [str(c).strip().lower() for c in item.get("concepts") or [] if str(c).strip()]
        entry = {"entity": entity, "column": column, "status": status}
        if concepts:
            entry["concepts"] = concepts
        role = str(item.get("role") or "").strip().lower()
        if role:
            if role not in _ATTRIBUTE_ROLES:
                raise ValueError(f"attributes[{entity}.{column}].role invalid")
            entry["role"] = role
        for key in ("data_type", "notes", "citation", "fk_target_entity", "fk_target_column"):
            value = str(item.get(key) or "").strip()
            if value:
                entry[key] = value.lower() if key == "fk_target_entity" else value
        join_stats = item.get("join_stats")
        if isinstance(join_stats, dict):
            entry["join_stats"] = join_stats
        attributes.append(entry)
    normalized["attributes"] = attributes

    relationships: list[dict[str, Any]] = []
    seen_rels: set[str] = set()
    for item in payload.get("relationships") or []:
        if not isinstance(item, dict):
            continue
        rel_id = str(item.get("id") or "").strip().lower()
        from_entity = str(item.get("from_entity") or "").strip().lower()
        from_column = str(item.get("from_column") or "").strip()
        to_entity = str(item.get("to_entity") or "").strip().lower()
        to_column = str(item.get("to_column") or "").strip()
        cardinality = str(item.get("cardinality") or "").strip().lower()
        status = str(item.get("status") or "proposed").strip().lower()
        if not rel_id or not from_entity or not from_column or not to_entity or not to_column:
            raise ValueError("relationships require id, from/to entity and column")
        if rel_id in seen_rels:
            raise ValueError(f"Duplicate relationship id: {rel_id!r}")
        seen_rels.add(rel_id)
        if cardinality not in _CARDINALITIES:
            raise ValueError(f"relationships[{rel_id}].cardinality invalid")
        if status not in _ITEM_STATUSES:
            raise ValueError(f"relationships[{rel_id}].status invalid")
        entry: dict[str, Any] = {
            "id": rel_id,
            "from_entity": from_entity,
            "from_column": from_column,
            "to_entity": to_entity,
            "to_column": to_column,
            "cardinality": cardinality,
            "status": status,
        }
        confidence = item.get("confidence")
        if confidence is not None:
            entry["confidence"] = float(confidence)
        for key in ("description", "citation"):
            value = str(item.get(key) or "").strip()
            if value:
                entry[key] = value
        join_stats = item.get("join_stats")
        if isinstance(join_stats, dict):
            entry["join_stats"] = join_stats
        relationships.append(entry)
    normalized["relationships"] = relationships

    questions: list[dict[str, Any]] = []
    seen_questions: set[str] = set()
    for item in payload.get("questions") or []:
        if not isinstance(item, dict):
            continue
        question_id = str(item.get("id") or "").strip().lower()
        text = str(item.get("text") or "").strip()
        status = str(item.get("status") or "open").strip().lower()
        if not question_id or not text:
            raise ValueError("questions require id and text")
        if question_id in seen_questions:
            raise ValueError(f"Duplicate question id: {question_id!r}")
        seen_questions.add(question_id)
        if status not in _QUESTION_STATUSES:
            raise ValueError(f"questions[{question_id}].status invalid")
        entry: dict[str, Any] = {
            "id": question_id,
            "text": text,
            "status": status,
        }
        if item.get("blocks_publish"):
            entry["blocks_publish"] = True
        resolution = str(item.get("resolution") or "").strip()
        if resolution:
            entry["resolution"] = resolution
        action = normalize_question_action(item.get("action"))
        if action:
            entry["action"] = action
        questions.append(entry)
    normalized["questions"] = questions

    return normalized


def default_semantic_model_draft(settings: DnaSettings, *, username: str = "") -> dict[str, Any]:
    return {
        "version": "0.1.0",
        "status": "draft",
        "source": settings.source.strip().lower(),
        "updated_at": datetime.now(UTC).isoformat(),
        "updated_by": username,
        "description": "",
        "entities": [],
        "attributes": [],
        "relationships": [],
        "questions": [],
    }


def _default_builder_steps() -> dict[str, Any]:
    return {
        "current_step": BUILDER_STEPS[0],
        "steps_completed": {step: False for step in BUILDER_STEPS},
    }


def normalize_builder_workflow(workflow: dict[str, Any]) -> dict[str, Any]:
    """Ensure workflow has multi-step builder fields (backward compatible)."""
    normalized = dict(workflow)
    steps = normalized.get("steps_completed")
    if not isinstance(steps, dict):
        steps = {step: False for step in BUILDER_STEPS}
    else:
        steps = {step: bool(steps.get(step)) for step in BUILDER_STEPS}
    normalized["steps_completed"] = steps
    current = str(normalized.get("current_step") or "").strip().lower()
    if current not in BUILDER_STEPS:
        if normalized.get("init_completed"):
            if steps.get("tags"):
                current = BUILDER_STEPS[-1]
            elif steps.get("relationships"):
                current = BUILDER_STEPS[2]
            elif steps.get("keys"):
                current = BUILDER_STEPS[1]
            else:
                current = BUILDER_STEPS[0]
        else:
            current = BUILDER_STEPS[0]
    normalized["current_step"] = current
    profiling = str(normalized.get("profiling_status") or "idle").strip().lower()
    if profiling not in {"idle", "in_progress", "completed", "error"}:
        profiling = "idle"
    normalized["profiling_status"] = profiling
    tagging = str(normalized.get("tagging_status") or "idle").strip().lower()
    if tagging not in {"idle", "in_progress", "completed", "error"}:
        tagging = "idle"
    normalized["tagging_status"] = tagging
    return normalized


def load_semantic_model_workflow(settings: DnaSettings) -> dict[str, Any]:
    pack_id = settings.dna_config_id
    payload = read_json_artifact(settings, governance_semantic_model_workflow_key(pack_id))
    if not payload:
        return normalize_builder_workflow(
            {
                "pack_id": pack_id,
                "active_version": None,
                "history": [],
                "draft_updated_at": None,
                "init_completed": False,
            }
        )
    return normalize_builder_workflow(payload)


def save_semantic_model_workflow(settings: DnaSettings, workflow: dict[str, Any]) -> str:
    pack_id = settings.dna_config_id
    workflow = normalize_builder_workflow(dict(workflow))
    workflow["pack_id"] = pack_id
    return write_json_artifact(settings, governance_semantic_model_workflow_key(pack_id), workflow)


def update_profiling_workflow(
    settings: DnaSettings,
    *,
    status: str,
    username: str = "",
    error: str = "",
) -> dict[str, Any]:
    allowed = {"idle", "in_progress", "completed", "error"}
    key = status.strip().lower()
    if key not in allowed:
        raise ValueError(f"profiling status must be one of {allowed}")
    workflow = load_semantic_model_workflow(settings)
    workflow["profiling_status"] = key
    now = datetime.now(UTC).isoformat()
    if key == "in_progress":
        workflow["profiling_started_at"] = now
        workflow.pop("profiling_error", None)
    elif key == "completed":
        workflow["profiling_completed_at"] = now
        workflow.pop("profiling_error", None)
    elif key == "error":
        workflow["profiling_error"] = str(error or "Profiling failed").strip()
        workflow["profiling_completed_at"] = now
    elif key == "idle":
        workflow.pop("profiling_error", None)
    if username:
        workflow["profiling_by"] = username
    save_semantic_model_workflow(settings, workflow)
    return workflow


def update_tagging_workflow(
    settings: DnaSettings,
    *,
    status: str,
    username: str = "",
    error: str = "",
) -> dict[str, Any]:
    allowed = {"idle", "in_progress", "completed", "error"}
    key = status.strip().lower()
    if key not in allowed:
        raise ValueError(f"tagging status must be one of {allowed}")
    workflow = load_semantic_model_workflow(settings)
    workflow["tagging_status"] = key
    now = datetime.now(UTC).isoformat()
    if key == "in_progress":
        workflow["tagging_started_at"] = now
        workflow.pop("tagging_error", None)
    elif key == "completed":
        workflow["tagging_completed_at"] = now
        workflow.pop("tagging_error", None)
    elif key == "error":
        workflow["tagging_error"] = str(error or "Semantic tagging failed").strip()
        workflow["tagging_completed_at"] = now
    elif key == "idle":
        workflow.pop("tagging_error", None)
    if username:
        workflow["tagging_by"] = username
    save_semantic_model_workflow(settings, workflow)
    return workflow


def load_semantic_model_draft(settings: DnaSettings) -> dict[str, Any]:
    pack_id = settings.dna_config_id
    payload = read_yaml_artifact(settings, governance_semantic_model_draft_key(pack_id))
    if not payload:
        return default_semantic_model_draft(settings)
    normalized = _normalize_semantic_model(payload, settings=settings)
    normalized["status"] = "draft"
    return normalized


def save_semantic_model_draft(
    settings: DnaSettings,
    payload: dict[str, Any],
    *,
    username: str,
) -> dict[str, Any]:
    normalized = _normalize_semantic_model(payload, settings=settings)
    normalized["status"] = "draft"
    normalized["updated_at"] = datetime.now(UTC).isoformat()
    normalized["updated_by"] = username
    validate_semantic_model_schema(normalized)
    write_yaml_artifact(
        settings,
        governance_semantic_model_draft_key(settings.dna_config_id),
        normalized,
    )
    workflow = load_semantic_model_workflow(settings)
    workflow["draft_updated_at"] = normalized["updated_at"]
    save_semantic_model_workflow(settings, workflow)
    return normalized


def load_production_semantic_model(settings: DnaSettings) -> dict[str, Any] | None:
    workflow = load_semantic_model_workflow(settings)
    version = workflow.get("active_version")
    if not version:
        return None
    pack_id = settings.dna_config_id
    payload = read_yaml_artifact(settings, governance_semantic_model_key(pack_id, str(version)))
    if not payload:
        return None
    normalized = _normalize_semantic_model(payload, settings=settings)
    normalized["status"] = "production"
    normalized["version"] = str(version)
    return normalized


def _bump_patch_version(version: str) -> str:
    parts = str(version or "0.1.0").strip().split(".")
    if len(parts) != 3:
        return "0.1.1"
    try:
        major, minor, patch = (int(parts[0]), int(parts[1]), int(parts[2]))
    except ValueError:
        return "0.1.1"
    return f"{major}.{minor}.{patch + 1}"


def _sync_field_semantics_from_model(
    settings: DnaSettings,
    model: dict[str, Any],
    *,
    username: str,
) -> None:
    """Mirror approved/proposed attribute tags into field semantics draft."""
    draft = load_field_semantics_draft(settings)
    mappings: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for attribute in model.get("attributes") or []:
        if not isinstance(attribute, dict):
            continue
        if str(attribute.get("status") or "") == "rejected":
            continue
        concepts = [str(c) for c in attribute.get("concepts") or [] if str(c).strip()]
        if not concepts:
            continue
        entity = str(attribute.get("entity") or "").strip().lower()
        column = str(attribute.get("column") or "").strip()
        if not entity or not column:
            continue
        pair = (entity, column)
        if pair in seen:
            continue
        seen.add(pair)
        entry: dict[str, Any] = {
            "silver_entity": entity,
            "column": column,
            "concepts": concepts,
        }
        notes = str(attribute.get("notes") or "").strip()
        if notes:
            entry["notes"] = notes
        mappings.append(entry)
    draft["mappings"] = mappings
    draft["source"] = model.get("source") or draft.get("source")
    save_field_semantics_draft(settings, draft, username=username)


def publish_semantic_model(
    settings: DnaSettings,
    *,
    username: str,
    version: str | None = None,
) -> dict[str, Any]:
    draft = load_semantic_model_draft(settings)
    for entity in draft.get("entities") or []:
        if not isinstance(entity, dict):
            continue
        if str(entity.get("primary_key_status") or "").strip().lower() == "approved":
            entity["status"] = "approved"
    draft["updated_by"] = username
    draft["updated_at"] = datetime.now(UTC).isoformat()
    validate_semantic_model_schema(draft)

    readiness = evaluate_publish_readiness(draft)
    if not readiness["ready"]:
        raise ValueError(
            "Semantic model is not ready to publish — "
            + "; ".join(readiness.get("errors") or ["unknown"])
        )

    workflow = load_semantic_model_workflow(settings)
    current = workflow.get("active_version")
    next_version = (version or "").strip() or _bump_patch_version(
        str(current or draft.get("version") or "0.1.0")
    )

    published = dict(draft)
    published["status"] = "production"
    published["version"] = next_version

    pack_id = settings.dna_config_id
    write_yaml_artifact(
        settings,
        governance_semantic_model_key(pack_id, next_version),
        published,
    )
    manifest = {
        "pack_id": pack_id,
        "version": next_version,
        "status": "production",
        "published_at": published["updated_at"],
        "published_by": username,
        "coverage": semantic_model_coverage(draft),
    }
    write_json_artifact(
        settings,
        governance_semantic_model_manifest_key(pack_id, next_version),
        manifest,
    )

    history = workflow.get("history")
    if not isinstance(history, list):
        history = []
    history.append(
        {
            "version": next_version,
            "status": "production",
            "approver": username,
            "at": published["updated_at"],
            "notes": "Published semantic model",
        }
    )
    workflow["active_version"] = next_version
    workflow["history"] = history
    workflow["draft_updated_at"] = published["updated_at"]
    save_semantic_model_workflow(settings, workflow)

    write_yaml_artifact(
        settings,
        governance_semantic_model_draft_key(pack_id),
        published,
    )
    _sync_field_semantics_from_model(settings, published, username=username)

    reference_record: dict[str, Any] | None = None
    try:
        from meshflow.dna.semantic_source_reference import record_approved_semantic_build

        reference_record = record_approved_semantic_build(
            settings,
            published,
            pack_id=pack_id,
            version=next_version,
            username=username,
        )
    except Exception:  # noqa: BLE001 — publish must succeed even if reference index fails
        reference_record = None

    dna_sync: dict[str, Any] | None = None
    try:
        from meshflow.dna.semantic_codegen import apply_semantic_model_to_dna_pack

        dna_sync = apply_semantic_model_to_dna_pack(
            settings,
            published,
            username=username,
            notes=f"Auto-sync from semantic model v{next_version}",
        )
    except ValueError:
        dna_sync = None

    result = dict(published)
    if reference_record:
        result["source_reference"] = {
            "build_count": reference_record.get("build_count"),
            "profile_key": reference_record.get("profile_key"),
        }
    if dna_sync:
        result["dna_sync"] = dna_sync
    return result


def discard_semantic_model_draft(settings: DnaSettings, *, username: str) -> dict[str, Any]:
    production = load_production_semantic_model(settings)
    if production:
        draft = dict(production)
        draft["status"] = "draft"
    else:
        draft = default_semantic_model_draft(settings, username=username)
    return save_semantic_model_draft(settings, draft, username=username)


def _production_entity_by_silver(production: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not production:
        return {}
    return {
        str(entity.get("silver_entity") or "").strip().lower(): entity
        for entity in production.get("entities") or []
        if isinstance(entity, dict) and str(entity.get("silver_entity") or "").strip()
    }


def _production_attribute_by_pair(production: dict[str, Any] | None) -> dict[tuple[str, str], dict[str, Any]]:
    if not production:
        return {}
    indexed: dict[tuple[str, str], dict[str, Any]] = {}
    for attribute in production.get("attributes") or []:
        if not isinstance(attribute, dict):
            continue
        entity = str(attribute.get("entity") or "").strip().lower()
        column = str(attribute.get("column") or "").strip()
        if entity and column:
            indexed[(entity, column)] = attribute
    return indexed


def _copy_entity_key_fields(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key in (
        "primary_key",
        "primary_key_status",
        "pk_stats",
        "status",
        "role",
        "description",
        "grain",
    ):
        if key in source:
            target[key] = source[key]


def _copy_foreign_key_fields(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key in (
        "status",
        "role",
        "fk_target_entity",
        "fk_target_column",
        "to_entity",
        "to_column",
        "join_stats",
        "citation",
    ):
        if key in source:
            target[key] = source[key]


def _copy_tag_fields(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key in ("status", "concepts", "role", "citation"):
        if key in source:
            target[key] = source[key]


def discard_semantic_model_step_decisions(
    settings: DnaSettings,
    step: str,
    *,
    username: str,
) -> dict[str, Any]:
    normalized_step = str(step or "").strip().lower()
    if normalized_step not in BUILDER_STEPS:
        raise ValueError(f"step must be one of {BUILDER_STEPS}")
    draft = load_semantic_model_draft(settings)
    production = load_production_semantic_model(settings)
    prod_entities = _production_entity_by_silver(production)
    prod_attributes = _production_attribute_by_pair(production)

    if normalized_step == "keys":
        for entity in draft.get("entities") or []:
            if not isinstance(entity, dict):
                continue
            silver = str(entity.get("silver_entity") or "").strip().lower()
            prod_entity = prod_entities.get(silver)
            if prod_entity:
                _copy_entity_key_fields(entity, prod_entity)
            elif str(entity.get("primary_key_status") or "proposed") != "proposed":
                entity["primary_key_status"] = "proposed"
        for attribute in draft.get("attributes") or []:
            if not isinstance(attribute, dict):
                continue
            if str(attribute.get("role") or "").strip().lower() != "foreign_key":
                continue
            pair = (
                str(attribute.get("entity") or "").strip().lower(),
                str(attribute.get("column") or "").strip(),
            )
            prod_attribute = prod_attributes.get(pair)
            if prod_attribute:
                _copy_foreign_key_fields(attribute, prod_attribute)
            elif str(attribute.get("status") or "proposed") != "proposed":
                attribute["status"] = "proposed"
    elif normalized_step == "relationships":
        if production:
            draft["relationships"] = [
                dict(item) for item in production.get("relationships") or [] if isinstance(item, dict)
            ]
        else:
            for rel in draft.get("relationships") or []:
                if isinstance(rel, dict) and str(rel.get("status") or "proposed") != "proposed":
                    rel["status"] = "proposed"
    else:
        for attribute in draft.get("attributes") or []:
            if not isinstance(attribute, dict):
                continue
            if str(attribute.get("role") or "").strip().lower() == "foreign_key":
                continue
            pair = (
                str(attribute.get("entity") or "").strip().lower(),
                str(attribute.get("column") or "").strip(),
            )
            prod_attribute = prod_attributes.get(pair)
            if prod_attribute:
                _copy_tag_fields(attribute, prod_attribute)
            elif str(attribute.get("status") or "proposed") != "proposed":
                attribute["status"] = "proposed"

    return save_semantic_model_draft(settings, draft, username=username)


def step_decisions_diff_count(settings: DnaSettings, step: str) -> int:
    normalized_step = str(step or "").strip().lower()
    if normalized_step not in BUILDER_STEPS:
        return 0
    draft = load_semantic_model_draft(settings)
    production = load_production_semantic_model(settings)
    prod_entities = _production_entity_by_silver(production)
    prod_attributes = _production_attribute_by_pair(production)
    count = 0

    if normalized_step == "keys":
        for entity in draft.get("entities") or []:
            if not isinstance(entity, dict):
                continue
            silver = str(entity.get("silver_entity") or "").strip().lower()
            prod_entity = prod_entities.get(silver)
            if production:
                if not prod_entity:
                    if str(entity.get("primary_key_status") or "proposed") != "proposed":
                        count += 1
                else:
                    for key in ("primary_key", "primary_key_status", "status"):
                        if entity.get(key) != prod_entity.get(key):
                            count += 1
                            break
            elif str(entity.get("primary_key_status") or "proposed") != "proposed":
                count += 1
        for attribute in draft.get("attributes") or []:
            if not isinstance(attribute, dict):
                continue
            if str(attribute.get("role") or "").strip().lower() != "foreign_key":
                continue
            pair = (
                str(attribute.get("entity") or "").strip().lower(),
                str(attribute.get("column") or "").strip(),
            )
            prod_attribute = prod_attributes.get(pair)
            status = str(attribute.get("status") or "proposed")
            if production:
                if not prod_attribute and status != "proposed":
                    count += 1
                elif prod_attribute and status != str(prod_attribute.get("status") or "proposed"):
                    count += 1
            elif status != "proposed":
                count += 1
        return count

    if normalized_step == "relationships":
        draft_rels = [r for r in draft.get("relationships") or [] if isinstance(r, dict)]
        if production:
            prod_by_id = {
                str(rel.get("id") or ""): rel
                for rel in production.get("relationships") or []
                if isinstance(rel, dict) and str(rel.get("id") or "")
            }
            seen_ids: set[str] = set()
            for rel in draft_rels:
                rel_id = str(rel.get("id") or "")
                if not rel_id:
                    count += 1
                    continue
                seen_ids.add(rel_id)
                prod_rel = prod_by_id.get(rel_id)
                if not prod_rel or yaml.safe_dump(rel, sort_keys=True) != yaml.safe_dump(
                    prod_rel, sort_keys=True
                ):
                    count += 1
            for rel_id in prod_by_id:
                if rel_id not in seen_ids:
                    count += 1
            return count
        return sum(1 for rel in draft_rels if str(rel.get("status") or "proposed") != "proposed")

    for attribute in draft.get("attributes") or []:
        if not isinstance(attribute, dict):
            continue
        if str(attribute.get("role") or "").strip().lower() == "foreign_key":
            continue
        if not attribute.get("concepts") and str(attribute.get("status") or "proposed") == "proposed":
            continue
        pair = (
            str(attribute.get("entity") or "").strip().lower(),
            str(attribute.get("column") or "").strip(),
        )
        prod_attribute = prod_attributes.get(pair)
        status = str(attribute.get("status") or "proposed")
        concepts = attribute.get("concepts") or []
        if production:
            if not prod_attribute:
                if status != "proposed" or concepts:
                    count += 1
            else:
                if status != str(prod_attribute.get("status") or "proposed"):
                    count += 1
                elif concepts != (prod_attribute.get("concepts") or []):
                    count += 1
        elif status != "proposed":
            count += 1
    return count


def step_outstanding_proposal_count(settings: DnaSettings, step: str) -> int:
    """Count proposals still awaiting approve/reject for a builder step."""
    normalized_step = str(step or "").strip().lower()
    if normalized_step not in BUILDER_STEPS:
        return 0
    draft = load_semantic_model_draft(settings)

    if normalized_step == "keys":
        count = 0
        for entity in draft.get("entities") or []:
            if not isinstance(entity, dict):
                continue
            if str(entity.get("primary_key_status") or "proposed") == "proposed":
                count += 1
        for attribute in draft.get("attributes") or []:
            if not isinstance(attribute, dict):
                continue
            if str(attribute.get("role") or "").strip().lower() != "foreign_key":
                continue
            if str(attribute.get("status") or "proposed") == "proposed":
                count += 1
        return count

    if normalized_step == "relationships":
        return sum(
            1
            for rel in draft.get("relationships") or []
            if isinstance(rel, dict) and str(rel.get("status") or "proposed") == "proposed"
        )

    count = 0
    for attribute in draft.get("attributes") or []:
        if not isinstance(attribute, dict):
            continue
        if str(attribute.get("role") or "").strip().lower() == "foreign_key":
            continue
        if not attribute.get("concepts"):
            continue
        if str(attribute.get("status") or "proposed") == "proposed":
            count += 1
    return count


def step_decisions_differ_from_production(settings: DnaSettings, step: str) -> bool:
    return step_decisions_diff_count(settings, step) > 0


def ensure_semantic_model_seed(settings: DnaSettings, *, username: str = "system") -> dict[str, Any]:
    pack_id = settings.dna_config_id
    draft_key = governance_semantic_model_draft_key(pack_id)
    workflow_key = governance_semantic_model_workflow_key(pack_id)
    draft_exists = read_yaml_artifact(settings, draft_key) is not None
    workflow_exists = read_json_artifact(settings, workflow_key) is not None
    if draft_exists and workflow_exists:
        return {"status": "skipped", "pack_id": pack_id}

    draft = default_semantic_model_draft(settings, username=username)
    write_yaml_artifact(settings, draft_key, draft)
    if not workflow_exists:
        save_semantic_model_workflow(
            settings,
            normalize_builder_workflow(
                {
                    "pack_id": pack_id,
                    "active_version": None,
                    "history": [],
                    "draft_updated_at": draft["updated_at"],
                    "init_completed": False,
                }
            ),
        )
    return {"status": "initialized", "pack_id": pack_id}


def semantic_model_coverage(model: dict[str, Any]) -> dict[str, Any]:
    entities = model.get("entities") or []
    attributes = model.get("attributes") or []
    relationships = model.get("relationships") or []
    questions = model.get("questions") or []

    silver_entities = {str(e.get("silver_entity") or "") for e in entities if e.get("silver_entity")}
    tagged_columns = {
        (str(a.get("entity") or ""), str(a.get("column") or ""))
        for a in attributes
        if a.get("concepts") and str(a.get("status") or "") != "rejected"
    }

    def _count_status(items: list[dict[str, Any]], approved: str = "approved") -> dict[str, int]:
        counts = {"proposed": 0, "approved": 0, "rejected": 0}
        for item in items:
            if not isinstance(item, dict):
                continue
            status = str(item.get("status") or "proposed").lower()
            if status in counts:
                counts[status] += 1
        return counts

    entity_counts = _count_status(entities)
    rel_counts = _count_status(relationships)
    attr_counts = _count_status(attributes)
    pk_approved = sum(
        1
        for entity in entities
        if isinstance(entity, dict) and str(entity.get("primary_key_status") or "") == "approved"
    )
    pk_proposed = sum(
        1
        for entity in entities
        if isinstance(entity, dict) and str(entity.get("primary_key_status") or "proposed") == "proposed"
        and str(entity.get("primary_key") or "").strip()
    )
    fk_approved = sum(
        1
        for attribute in attributes
        if isinstance(attribute, dict)
        and str(attribute.get("role") or "") == "foreign_key"
        and str(attribute.get("status") or "") == "approved"
    )
    fk_proposed = sum(
        1
        for attribute in attributes
        if isinstance(attribute, dict)
        and str(attribute.get("role") or "") == "foreign_key"
        and str(attribute.get("status") or "proposed") == "proposed"
    )
    open_questions = sum(
        1
        for q in questions
        if isinstance(q, dict)
        and str(q.get("status") or "open") == "open"
        and q.get("blocks_publish")
    )

    total_columns = 0
    tagged_on_silver = 0
    for entity_name in silver_entities:
        cols = {column for ent, column in tagged_columns if ent == entity_name}
        tagged_on_silver += len(cols)

    attribute_ratio = 0.0
    if attributes:
        tagged_attr = sum(1 for a in attributes if a.get("concepts") and a.get("status") != "rejected")
        attribute_ratio = tagged_attr / len(attributes)

    return {
        "entity_count": len(entities),
        "entity_approved": entity_counts["approved"],
        "entity_proposed": entity_counts["proposed"],
        "primary_keys_approved": pk_approved,
        "primary_keys_proposed": pk_proposed,
        "foreign_keys_approved": fk_approved,
        "foreign_keys_proposed": fk_proposed,
        "relationship_count": len(relationships),
        "relationship_approved": rel_counts["approved"],
        "relationship_proposed": rel_counts["proposed"],
        "attribute_count": len(attributes),
        "attribute_approved": attr_counts["approved"],
        "attribute_proposed": attr_counts["proposed"],
        "attribute_tag_ratio": round(attribute_ratio, 4),
        "tagged_column_count": len(tagged_columns),
        "open_blocking_questions": open_questions,
        "fact_entity_approved": sum(
            1
            for e in entities
            if isinstance(e, dict)
            and str(e.get("role") or "") == "fact"
            and (
                str(e.get("status") or "") == "approved"
                or str(e.get("primary_key_status") or "") == "approved"
            )
        ),
    }


def evaluate_publish_readiness(model: dict[str, Any]) -> dict[str, Any]:
    coverage = semantic_model_coverage(model)
    errors: list[str] = []

    if coverage["fact_entity_approved"] < _MIN_APPROVED_FACT_ENTITIES:
        errors.append(
            f"At least {_MIN_APPROVED_FACT_ENTITIES} fact entity must be approved "
            f"(currently {coverage['fact_entity_approved']})"
        )
    if coverage["relationship_approved"] < _MIN_APPROVED_RELATIONSHIPS:
        errors.append(
            f"At least {_MIN_APPROVED_RELATIONSHIPS} relationship must be approved "
            f"(currently {coverage['relationship_approved']})"
        )
    if coverage["attribute_tag_ratio"] < _MIN_ATTRIBUTE_TAG_RATIO and coverage["attribute_count"] > 0:
        errors.append(
            f"Attribute concept coverage must be at least "
            f"{int(_MIN_ATTRIBUTE_TAG_RATIO * 100)}% "
            f"(currently {int(coverage['attribute_tag_ratio'] * 100)}%)"
        )
    if coverage["open_blocking_questions"] > 0:
        errors.append(
            f"{coverage['open_blocking_questions']} blocking question(s) must be resolved before publish"
        )

    return {
        "ready": not errors,
        "errors": errors,
        "coverage": coverage,
    }


def semantic_model_publish_gate(settings: DnaSettings) -> dict[str, Any]:
    """Gate gold DNA publish on a published, ready semantic model."""
    workflow = load_semantic_model_workflow(settings)
    if not workflow.get("init_completed"):
        return {"ready": True, "skipped": True, "reason": "semantic_init_not_run"}

    production = load_production_semantic_model(settings)
    if production is None:
        return {
            "ready": False,
            "skipped": False,
            "errors": ["Publish the semantic model in Semantic Builder before running gold compile"],
        }

    readiness = evaluate_publish_readiness(production)
    if not readiness["ready"]:
        return {
            "ready": False,
            "skipped": False,
            "errors": readiness["errors"],
            "coverage": readiness["coverage"],
        }
    return {"ready": True, "skipped": False, "version": production.get("version")}


def _comparable_model_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "source": payload.get("source"),
        "description": payload.get("description"),
        "entities": payload.get("entities") or [],
        "attributes": payload.get("attributes") or [],
        "relationships": payload.get("relationships") or [],
        "questions": payload.get("questions") or [],
    }


def draft_differs_from_production(settings: DnaSettings) -> bool:
    draft = load_semantic_model_draft(settings)
    production = load_production_semantic_model(settings)
    if production is None:
        return bool(
            draft.get("entities")
            or draft.get("attributes")
            or draft.get("relationships")
            or draft.get("questions")
        )
    return yaml.safe_dump(_comparable_model_payload(draft), sort_keys=True) != yaml.safe_dump(
        _comparable_model_payload(production),
        sort_keys=True,
    )


def update_relationship_status(
    settings: DnaSettings,
    relationship_id: str,
    status: str,
    *,
    username: str,
) -> dict[str, Any]:
    if status not in _ITEM_STATUSES:
        raise ValueError(f"status must be one of {_ITEM_STATUSES}")
    draft = load_semantic_model_draft(settings)
    rel_id = relationship_id.strip().lower()
    found = False
    for rel in draft.get("relationships") or []:
        if isinstance(rel, dict) and str(rel.get("id") or "").lower() == rel_id:
            rel["status"] = status
            found = True
            break
    if not found:
        raise ValueError(f"Relationship not found: {relationship_id!r}")
    return save_semantic_model_draft(settings, draft, username=username)


def update_entity_status(
    settings: DnaSettings,
    entity_id: str,
    status: str,
    *,
    username: str,
) -> dict[str, Any]:
    if status not in _ITEM_STATUSES:
        raise ValueError(f"status must be one of {_ITEM_STATUSES}")
    draft = load_semantic_model_draft(settings)
    ent_id = entity_id.strip().lower()
    found = False
    for entity in draft.get("entities") or []:
        if isinstance(entity, dict) and str(entity.get("id") or "").lower() == ent_id:
            entity["status"] = status
            found = True
            break
    if not found:
        raise ValueError(f"Entity not found: {entity_id!r}")
    return save_semantic_model_draft(settings, draft, username=username)


def normalize_question_action(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    action_type = str(raw.get("type") or "").strip().lower()
    if action_type not in QUESTION_ACTION_TYPES:
        return None
    action: dict[str, Any] = {"type": action_type}
    entity = str(raw.get("entity") or "").strip().lower()
    if entity:
        action["entity"] = entity
    column = str(raw.get("column") or "").strip()
    if column:
        action["column"] = column
    relationship_id = str(raw.get("relationship_id") or "").strip().lower()
    if relationship_id:
        action["relationship_id"] = relationship_id
    choices_raw = raw.get("choices")
    if isinstance(choices_raw, list):
        choices: list[dict[str, Any]] = []
        for item in choices_raw:
            if not isinstance(item, dict):
                continue
            choice_id = str(item.get("id") or item.get("value") or "").strip()
            label = str(item.get("label") or "").strip()
            value = str(item.get("value") or choice_id).strip()
            if not choice_id or not label:
                continue
            entry: dict[str, Any] = {"id": choice_id, "label": label, "value": value}
            choice_column = str(item.get("column") or "").strip()
            if choice_column:
                entry["column"] = choice_column
            concepts_raw = item.get("concepts")
            if isinstance(concepts_raw, list):
                concepts = [str(c).strip() for c in concepts_raw if str(c).strip()]
                if concepts:
                    entry["concepts"] = concepts
            choices.append(entry)
        if choices:
            action["choices"] = choices
    return action


def question_from_key_conflict(conflict: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(conflict, dict):
        return None
    qid = str(conflict.get("id") or "").strip().lower()
    text = str(conflict.get("text") or "").strip()
    if not qid or not text:
        return None
    kind = str(conflict.get("kind") or "").strip().lower()
    entity = str(conflict.get("entity") or "").strip().lower()
    column = str(conflict.get("column") or "").strip()
    action: dict[str, Any] = {"type": kind if kind in QUESTION_ACTION_TYPES else "acknowledge"}
    if entity:
        action["entity"] = entity
    if column:
        action["column"] = column
    choices: list[dict[str, Any]] = []
    if kind == "primary_key":
        profile_val = conflict.get("profile_value")
        doc_val = conflict.get("documentation_value")
        if profile_val:
            profile_col = str(profile_val).strip()
            choices.append(
                {
                    "id": "profile",
                    "label": f"Assign PK: {profile_col}",
                    "value": profile_col,
                }
            )
        if doc_val:
            doc_col = str(doc_val).strip()
            choices.append(
                {
                    "id": "documentation",
                    "label": f"Assign PK: {doc_col}",
                    "value": doc_col,
                }
            )
    elif kind == "foreign_key":
        if conflict.get("profile_value") is None:
            choices = [
                {"id": "approve", "label": "Mark as foreign key", "value": "approve"},
                {"id": "reject", "label": "Reject FK proposal", "value": "reject"},
            ]
        else:
            choices = [
                {"id": "approve", "label": "Approve foreign key", "value": "approve"},
                {"id": "reject", "label": "Reject foreign key", "value": "reject"},
            ]
    if choices:
        action["choices"] = choices
    return {
        "id": qid,
        "text": text,
        "status": "open",
        "blocks_publish": False,
        "action": action,
    }


def _entity_id_for_ref(draft: dict[str, Any], entity_ref: str) -> str:
    key = entity_ref.strip().lower()
    for entity in draft.get("entities") or []:
        if not isinstance(entity, dict):
            continue
        if str(entity.get("id") or "").lower() == key or str(entity.get("silver_entity") or "").lower() == key:
            return str(entity.get("id") or key)
    raise ValueError(f"Entity not found: {entity_ref!r}")


def _silver_entity_for_ref(draft: dict[str, Any], entity_ref: str) -> str:
    key = entity_ref.strip().lower()
    for entity in draft.get("entities") or []:
        if not isinstance(entity, dict):
            continue
        if str(entity.get("id") or "").lower() == key or str(entity.get("silver_entity") or "").lower() == key:
            return str(entity.get("silver_entity") or key)
    raise ValueError(f"Entity not found: {entity_ref!r}")


def _find_question_choice(action: dict[str, Any], choice_id: str) -> dict[str, Any] | None:
    key = choice_id.strip()
    for item in action.get("choices") or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("id") or "").strip() == key or str(item.get("value") or "").strip() == key:
            return item
    return None


def _apply_question_action_to_draft(
    draft: dict[str, Any],
    question: dict[str, Any],
    *,
    choice_id: str,
    resolution_note: str = "",
) -> str:
    action = question.get("action")
    if not isinstance(action, dict):
        if resolution_note.strip():
            return resolution_note.strip()
        return "Acknowledged"

    action_type = str(action.get("type") or "").strip().lower()
    choice = _find_question_choice(action, choice_id) if choice_id.strip() else None
    resolution = resolution_note.strip() or (str(choice.get("label") or "") if choice else "")

    if action_type == "primary_key":
        if not choice:
            raise ValueError("choice is required for primary key decisions")
        entity_id = _entity_id_for_ref(draft, str(action.get("entity") or ""))
        pk_column = str(choice.get("value") or "").strip()
        if not pk_column:
            raise ValueError("primary key choice requires a column value")
        for entity in draft.get("entities") or []:
            if isinstance(entity, dict) and str(entity.get("id") or "").lower() == entity_id:
                entity["primary_key"] = pk_column
                entity["primary_key_status"] = "approved"
                break
        return resolution or f"Assigned primary key {pk_column}"

    if action_type == "foreign_key":
        if not choice:
            raise ValueError("choice is required for foreign key decisions")
        entity_name = _silver_entity_for_ref(draft, str(action.get("entity") or ""))
        column = str(action.get("column") or "").strip()
        if not column:
            raise ValueError("foreign key action requires column")
        choice_value = str(choice.get("value") or "").strip().lower()
        status = "approved" if choice_value == "approve" else "rejected"
        found = False
        for attribute in draft.get("attributes") or []:
            if not isinstance(attribute, dict):
                continue
            if (
                str(attribute.get("entity") or "").strip().lower() == entity_name
                and str(attribute.get("column") or "").strip() == column
            ):
                attribute["role"] = "foreign_key"
                attribute["status"] = status
                found = True
                break
        if not found and status == "approved":
            draft.setdefault("attributes", []).append(
                {
                    "entity": entity_name,
                    "column": column,
                    "role": "foreign_key",
                    "status": "approved",
                }
            )
        return resolution or f"Foreign key {status}"

    if action_type == "relationship":
        if not choice:
            raise ValueError("choice is required for relationship decisions")
        rel_id = str(action.get("relationship_id") or "").strip().lower()
        if not rel_id:
            raise ValueError("relationship action requires relationship_id")
        choice_value = str(choice.get("value") or "").strip().lower()
        status = "approved" if choice_value == "approve" else "rejected"
        for rel in draft.get("relationships") or []:
            if isinstance(rel, dict) and str(rel.get("id") or "").lower() == rel_id:
                rel["status"] = status
                break
        else:
            raise ValueError(f"Relationship not found: {rel_id!r}")
        return resolution or f"Relationship {status}"

    if action_type == "column_tag":
        if not choice:
            raise ValueError("choice is required for column tag decisions")
        entity_name = _silver_entity_for_ref(draft, str(action.get("entity") or ""))
        column = str(choice.get("column") or action.get("column") or "").strip()
        concepts_raw = choice.get("concepts")
        concepts = (
            [str(c).strip() for c in concepts_raw if str(c).strip()]
            if isinstance(concepts_raw, list)
            else []
        )
        if not column:
            raise ValueError("column tag action requires column")
        if not concepts:
            concept_val = str(choice.get("value") or "").strip()
            if concept_val:
                concepts = [concept_val]
        if not concepts:
            raise ValueError("column tag choice requires concepts")
        found = False
        for attribute in draft.get("attributes") or []:
            if not isinstance(attribute, dict):
                continue
            if (
                str(attribute.get("entity") or "").strip().lower() == entity_name
                and str(attribute.get("column") or "").strip() == column
            ):
                attribute["concepts"] = concepts
                attribute["status"] = "approved"
                found = True
                break
        if not found:
            draft.setdefault("attributes", []).append(
                {
                    "entity": entity_name,
                    "column": column,
                    "concepts": concepts,
                    "status": "approved",
                }
            )
        return resolution or f"Tagged {entity_name}.{column}"

    if resolution_note.strip():
        return resolution_note.strip()
    return resolution or "Acknowledged"


def merge_preserved_questions(
    proposed: list[dict[str, Any]],
    existing: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Keep resolved decisions when profiling rebuilds the draft question list."""
    resolved_by_id: dict[str, dict[str, Any]] = {}
    for item in existing:
        if not isinstance(item, dict):
            continue
        qid = str(item.get("id") or "").strip().lower()
        if not qid:
            continue
        if str(item.get("status") or "open").strip().lower() in ("resolved", "deferred"):
            resolved_by_id[qid] = item

    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in proposed:
        if not isinstance(item, dict):
            continue
        qid = str(item.get("id") or "").strip().lower()
        if not qid:
            continue
        merged.append(resolved_by_id.get(qid, item))
        seen.add(qid)

    for qid, item in resolved_by_id.items():
        if qid not in seen:
            merged.append(item)

    return merged


def resolve_question(
    settings: DnaSettings,
    question_id: str,
    *,
    username: str,
    resolution: str = "",
    choice: str = "",
) -> dict[str, Any]:
    draft = load_semantic_model_draft(settings)
    qid = question_id.strip().lower()
    question: dict[str, Any] | None = None
    for item in draft.get("questions") or []:
        if isinstance(item, dict) and str(item.get("id") or "").lower() == qid:
            question = item
            break
    if question is None:
        raise ValueError(f"Question not found: {question_id!r}")
    status = str(question.get("status") or "open")
    if status not in ("open", "deferred"):
        raise ValueError(f"Question is not open: {question_id!r}")

    choice_id = choice.strip()
    if choice_id == DOCUMENT_LATER_CHOICE_ID:
        question["status"] = "deferred"
        question["resolution"] = "Document later"
        question["blocks_publish"] = False
        return save_semantic_model_draft(settings, draft, username=username)

    action = question.get("action")
    if isinstance(action, dict) and action.get("choices"):
        if not choice_id:
            raise ValueError("choice is required for this decision")
        applied = _apply_question_action_to_draft(
            draft,
            question,
            choice_id=choice_id,
            resolution_note=resolution,
        )
        question["resolution"] = applied
    elif resolution.strip():
        question["resolution"] = resolution.strip()
    elif choice_id:
        question["resolution"] = choice_id
    else:
        question["resolution"] = _apply_question_action_to_draft(
            draft,
            question,
            choice_id="",
            resolution_note=resolution,
        )

    question["status"] = "resolved"
    return save_semantic_model_draft(settings, draft, username=username)


def update_attribute_status(
    settings: DnaSettings,
    entity: str,
    column: str,
    status: str,
    *,
    username: str,
    concepts: list[str] | None = None,
) -> dict[str, Any]:
    if status not in _ITEM_STATUSES:
        raise ValueError(f"status must be one of {_ITEM_STATUSES}")
    entity_name = entity.strip().lower()
    column_name = column.strip()
    draft = load_semantic_model_draft(settings)
    found = False
    for attribute in draft.get("attributes") or []:
        if not isinstance(attribute, dict):
            continue
        if (
            str(attribute.get("entity") or "").strip().lower() == entity_name
            and str(attribute.get("column") or "").strip() == column_name
        ):
            attribute["status"] = status
            if concepts is not None:
                attribute["concepts"] = [str(c).strip().lower() for c in concepts if str(c).strip()]
            found = True
            break
    if not found:
        entry: dict[str, Any] = {
            "entity": entity_name,
            "column": column_name,
            "status": status,
        }
        if concepts:
            entry["concepts"] = [str(c).strip().lower() for c in concepts if str(c).strip()]
        draft.setdefault("attributes", []).append(entry)
    return save_semantic_model_draft(settings, draft, username=username)


def approve_all_proposed_tags(settings: DnaSettings, *, username: str) -> dict[str, Any]:
    draft = load_semantic_model_draft(settings)
    changed = 0
    for attribute in draft.get("attributes") or []:
        if not isinstance(attribute, dict):
            continue
        if str(attribute.get("status") or "") != "proposed":
            continue
        if not attribute.get("concepts"):
            continue
        attribute["status"] = "approved"
        changed += 1
    saved = save_semantic_model_draft(settings, draft, username=username)
    return {"draft": saved, "approved_count": changed}


def approve_all_proposed_entities_and_joins(settings: DnaSettings, *, username: str) -> dict[str, Any]:
    draft = load_semantic_model_draft(settings)
    entity_count = 0
    rel_count = 0
    for entity in draft.get("entities") or []:
        if isinstance(entity, dict) and str(entity.get("status") or "") == "proposed":
            entity["status"] = "approved"
            entity_count += 1
    for rel in draft.get("relationships") or []:
        if isinstance(rel, dict) and str(rel.get("status") or "") == "proposed":
            rel["status"] = "approved"
            rel_count += 1
    saved = save_semantic_model_draft(settings, draft, username=username)
    return {
        "draft": saved,
        "entities_approved": entity_count,
        "relationships_approved": rel_count,
    }


def _approved_primary_key_for_entity(draft: dict[str, Any], silver_entity: str) -> str | None:
    entity_name = silver_entity.strip().lower()
    for entity in draft.get("entities") or []:
        if not isinstance(entity, dict):
            continue
        if str(entity.get("silver_entity") or "").strip().lower() != entity_name:
            continue
        if str(entity.get("primary_key_status") or "").strip().lower() != "approved":
            return None
        pk = str(entity.get("primary_key") or "").strip()
        return pk or None
    return None


def _approved_foreign_key(
    draft: dict[str, Any],
    *,
    entity: str,
    column: str,
) -> dict[str, str] | None:
    entity_name = entity.strip().lower()
    column_name = column.strip()
    for attribute in draft.get("attributes") or []:
        if not isinstance(attribute, dict):
            continue
        if str(attribute.get("entity") or "").strip().lower() != entity_name:
            continue
        if str(attribute.get("column") or "").strip() != column_name:
            continue
        if str(attribute.get("role") or "").strip().lower() != "foreign_key":
            continue
        if str(attribute.get("status") or "").strip().lower() != "approved":
            return None
        target_entity = str(attribute.get("fk_target_entity") or attribute.get("to_entity") or "").strip().lower()
        target_column = str(attribute.get("fk_target_column") or attribute.get("to_column") or "").strip()
        if not target_entity:
            return None
        return {
            "to_entity": target_entity,
            "to_column": target_column or "id",
        }
    return None


def _assert_relationship_uses_approved_keys(
    draft: dict[str, Any],
    *,
    from_entity: str,
    from_column: str,
    to_entity: str,
    to_column: str,
) -> None:
    fk = _approved_foreign_key(
        draft,
        entity=from_entity,
        column=from_column,
    )
    if fk is None:
        raise ValueError(
            f"Relationship source {from_entity}.{from_column} must be an approved foreign key from step 1."
        )
    approved_pk = _approved_primary_key_for_entity(draft, to_entity)
    if not approved_pk:
        raise ValueError(f"Relationship target {to_entity} must have an approved primary key from step 1.")
    if to_column != approved_pk:
        raise ValueError(
            f"Relationship must target approved primary key {to_entity}.{approved_pk}, not {to_column!r}."
        )
    if fk["to_entity"] != to_entity.strip().lower():
        raise ValueError(
            f"Approved foreign key {from_entity}.{from_column} targets {fk['to_entity']}, not {to_entity}."
        )
    if fk["to_column"] != to_column:
        raise ValueError(
            f"Approved foreign key {from_entity}.{from_column} targets column {fk['to_column']}, not {to_column!r}."
        )


def update_entity_primary_key(
    settings: DnaSettings,
    entity_id: str,
    *,
    primary_key: str,
    primary_key_status: str,
    username: str,
) -> dict[str, Any]:
    if primary_key_status not in _ITEM_STATUSES:
        raise ValueError(f"primary_key_status must be one of {_ITEM_STATUSES}")
    draft = load_semantic_model_draft(settings)
    ent_id = entity_id.strip().lower()
    found = False
    silver_entity = ""
    for entity in draft.get("entities") or []:
        if isinstance(entity, dict) and str(entity.get("id") or "").lower() == ent_id:
            silver_entity = str(entity.get("silver_entity") or "").strip().lower()
            if primary_key_status == "approved":
                from meshflow.dna.semantic_join_stats import compute_primary_key_stats

                stats = compute_primary_key_stats(settings, silver_entity, primary_key.strip())
                if stats["row_count"] == 0:
                    raise ValueError(
                        f"Cannot approve primary key {silver_entity}.{primary_key.strip()} — "
                        "no silver rows found for this entity."
                    )
                entity["pk_stats"] = stats
            else:
                from meshflow.dna.semantic_join_stats import compute_primary_key_stats

                try:
                    entity["pk_stats"] = compute_primary_key_stats(settings, silver_entity, primary_key.strip())
                except Exception:
                    entity.pop("pk_stats", None)
            entity["primary_key"] = primary_key.strip()
            entity["primary_key_status"] = primary_key_status
            found = True
            break
    if not found:
        raise ValueError(f"Entity not found: {entity_id!r}")
    return save_semantic_model_draft(settings, draft, username=username)


def update_entity_primary_key_status(
    settings: DnaSettings,
    entity_id: str,
    status: str,
    *,
    username: str,
) -> dict[str, Any]:
    if status not in _ITEM_STATUSES:
        raise ValueError(f"status must be one of {_ITEM_STATUSES}")
    draft = load_semantic_model_draft(settings)
    ent_id = entity_id.strip().lower()
    found = False
    for entity in draft.get("entities") or []:
        if isinstance(entity, dict) and str(entity.get("id") or "").lower() == ent_id:
            if not str(entity.get("primary_key") or "").strip():
                entity["primary_key"] = "id"
            silver_entity = str(entity.get("silver_entity") or "").strip().lower()
            pk_column = str(entity.get("primary_key") or "id").strip()
            if status == "approved":
                from meshflow.dna.semantic_join_stats import compute_primary_key_stats

                stats = compute_primary_key_stats(settings, silver_entity, pk_column)
                if stats["row_count"] == 0:
                    raise ValueError(
                        f"Cannot approve primary key {silver_entity}.{pk_column} — "
                        "no silver rows found for this entity."
                    )
                entity["pk_stats"] = stats
                entity["status"] = "approved"
            entity["primary_key_status"] = status
            found = True
            break
    if not found:
        raise ValueError(f"Entity not found: {entity_id!r}")
    return save_semantic_model_draft(settings, draft, username=username)


def update_attribute_key_role(
    settings: DnaSettings,
    entity: str,
    column: str,
    *,
    role: str,
    status: str,
    username: str,
    fk_target_entity: str | None = None,
    fk_target_column: str | None = None,
) -> dict[str, Any]:
    if status not in _ITEM_STATUSES:
        raise ValueError(f"status must be one of {_ITEM_STATUSES}")
    if role and role not in _ATTRIBUTE_ROLES:
        raise ValueError(f"role must be one of {_ATTRIBUTE_ROLES}")
    entity_name = entity.strip().lower()
    column_name = column.strip()
    draft = load_semantic_model_draft(settings)
    found = False
    for attribute in draft.get("attributes") or []:
        if not isinstance(attribute, dict):
            continue
        if (
            str(attribute.get("entity") or "").strip().lower() == entity_name
            and str(attribute.get("column") or "").strip() == column_name
        ):
            if role:
                attribute["role"] = role
            attribute["status"] = status
            if fk_target_entity:
                attribute["fk_target_entity"] = fk_target_entity.strip().lower()
            if fk_target_column:
                attribute["fk_target_column"] = fk_target_column.strip()
            found = True
            break
    if not found:
        entry: dict[str, Any] = {
            "entity": entity_name,
            "column": column_name,
            "role": role or "foreign_key",
            "status": status,
        }
        if fk_target_entity:
            entry["fk_target_entity"] = fk_target_entity.strip().lower()
        if fk_target_column:
            entry["fk_target_column"] = fk_target_column.strip()
        draft.setdefault("attributes", []).append(entry)
    return save_semantic_model_draft(settings, draft, username=username)


def add_relationship_to_draft(
    settings: DnaSettings,
    *,
    relationship: dict[str, Any],
    username: str,
    require_approved_keys: bool = True,
) -> dict[str, Any]:
    draft = load_semantic_model_draft(settings)
    rel_id = str(relationship.get("id") or "").strip().lower()
    if not rel_id:
        raise ValueError("relationship id is required")
    from_entity = str(relationship.get("from_entity") or "").strip().lower()
    from_column = str(relationship.get("from_column") or "").strip()
    to_entity = str(relationship.get("to_entity") or "").strip().lower()
    to_column = str(relationship.get("to_column") or "id").strip()
    if require_approved_keys:
        _assert_relationship_uses_approved_keys(
            draft,
            from_entity=from_entity,
            from_column=from_column,
            to_entity=to_entity,
            to_column=to_column,
        )
    for rel in draft.get("relationships") or []:
        if isinstance(rel, dict) and str(rel.get("id") or "").lower() == rel_id:
            raise ValueError(f"Relationship already exists: {rel_id!r}")
    entry = {
        "id": rel_id,
        "from_entity": from_entity,
        "from_column": from_column,
        "to_entity": to_entity,
        "to_column": to_column,
        "cardinality": str(relationship.get("cardinality") or "many_to_one").strip().lower(),
        "status": str(relationship.get("status") or "proposed").strip().lower(),
    }
    if entry["status"] not in _ITEM_STATUSES:
        raise ValueError("relationship status invalid")
    for key in ("description", "citation"):
        value = str(relationship.get(key) or "").strip()
        if value:
            entry[key] = value
    if relationship.get("confidence") is not None:
        entry["confidence"] = float(relationship["confidence"])
    join_stats = relationship.get("join_stats")
    if isinstance(join_stats, dict):
        entry["join_stats"] = join_stats
    elif require_approved_keys:
        from meshflow.dna.semantic_join_stats import compute_join_stats

        entry["join_stats"] = compute_join_stats(
            settings,
            from_entity=from_entity,
            from_column=from_column,
            to_entity=to_entity,
            to_column=to_column,
        )
        entry["confidence"] = round(float(entry["join_stats"].get("match_rate") or 0.0), 4)
    draft.setdefault("relationships", []).append(entry)
    return save_semantic_model_draft(settings, draft, username=username)


def _draft_columns_by_entity(draft: dict[str, Any]) -> dict[str, list[str]]:
    """Column names already present in the semantic draft (no silver I/O)."""
    columns_by_entity: dict[str, set[str]] = {}
    for entity in draft.get("entities") or []:
        if not isinstance(entity, dict):
            continue
        silver = str(entity.get("silver_entity") or "").strip().lower()
        if not silver:
            continue
        cols = columns_by_entity.setdefault(silver, set())
        pk = str(entity.get("primary_key") or "").strip()
        if pk:
            cols.add(pk)
    for attribute in draft.get("attributes") or []:
        if not isinstance(attribute, dict):
            continue
        silver = str(attribute.get("entity") or "").strip().lower()
        column = str(attribute.get("column") or "").strip()
        if silver and column:
            columns_by_entity.setdefault(silver, set()).add(column)
    return {silver: sorted(cols) for silver, cols in columns_by_entity.items()}


def build_semantic_builder_options(settings: DnaSettings) -> dict[str, Any]:
    """Dropdown catalog for manual PK/FK/relationship/tag builder forms."""
    draft = load_semantic_model_draft(settings)
    draft_columns = _draft_columns_by_entity(draft)
    entities: list[dict[str, Any]] = []
    columns_by_entity: dict[str, list[str]] = {}
    for entity in draft.get("entities") or []:
        if not isinstance(entity, dict):
            continue
        silver = str(entity.get("silver_entity") or "").strip().lower()
        ent_id = str(entity.get("id") or silver).strip().lower()
        if not silver:
            continue
        columns = list(draft_columns.get(silver) or [])
        columns_by_entity[silver] = columns
        entities.append(
            {
                "id": ent_id,
                "silver_entity": silver,
                "label": silver,
                "primary_key": str(entity.get("primary_key") or "").strip(),
                "role": str(entity.get("role") or "").strip().lower(),
            }
        )
    catalog = load_operational_concept_catalog()
    from meshflow.dna.field_semantics import catalog_concept_ids, entity_column_concept_label

    known_concepts = catalog_concept_ids()
    concepts: list[dict[str, str]] = []
    seen_concepts: set[str] = set()
    for item in catalog.get("concepts") or []:
        if not isinstance(item, dict):
            continue
        concept_id = str(item.get("id") or "").strip().lower()
        if not concept_id:
            continue
        seen_concepts.add(concept_id)
        concepts.append(
            {
                "id": concept_id,
                "label": str(item.get("label") or concept_id).strip(),
            }
        )
    for attribute in draft.get("attributes") or []:
        if not isinstance(attribute, dict):
            continue
        entity_name = str(attribute.get("entity") or "").strip().lower()
        column_name = str(attribute.get("column") or "").strip()
        for concept_id in attribute.get("concepts") or []:
            normalized = str(concept_id).strip().lower()
            if not normalized or normalized in seen_concepts:
                continue
            seen_concepts.add(normalized)
            label = (
                entity_column_concept_label(entity_name, column_name)
                if normalized not in known_concepts and entity_name and column_name
                else normalized.replace("_", " ").title()
            )
            concepts.append({"id": normalized, "label": label})
    concepts.sort(key=lambda item: item["label"].lower())
    return {
        "entities": entities,
        "columns_by_entity": columns_by_entity,
        "concepts": concepts,
        "cardinalities": sorted(_CARDINALITIES),
    }


def manual_assign_primary_key(
    settings: DnaSettings,
    entity_ref: str,
    column: str,
    *,
    username: str,
    status: str = "proposed",
) -> dict[str, Any]:
    draft = load_semantic_model_draft(settings)
    entity_id = _entity_id_for_ref(draft, entity_ref)
    pk_column = column.strip()
    if not pk_column:
        raise ValueError("column is required")
    return update_entity_primary_key(
        settings,
        entity_id,
        primary_key=pk_column,
        primary_key_status=status,
        username=username,
    )


def manual_assign_foreign_key(
    settings: DnaSettings,
    entity: str,
    column: str,
    to_entity: str,
    to_column: str,
    *,
    username: str,
    status: str = "proposed",
) -> dict[str, Any]:
    entity_name = entity.strip().lower()
    column_name = column.strip()
    target_entity = to_entity.strip().lower()
    target_column = to_column.strip() or "id"
    if not entity_name or not column_name or not target_entity:
        raise ValueError("entity, column, and to_entity are required")
    return update_attribute_key_role(
        settings,
        entity_name,
        column_name,
        role="foreign_key",
        status=status,
        username=username,
        fk_target_entity=target_entity,
        fk_target_column=target_column,
    )


def manual_create_relationship(
    settings: DnaSettings,
    from_entity: str,
    from_column: str,
    to_entity: str,
    to_column: str,
    cardinality: str,
    *,
    username: str,
    status: str = "proposed",
) -> dict[str, Any]:
    from_name = from_entity.strip().lower()
    from_col = from_column.strip()
    to_name = to_entity.strip().lower()
    to_col = to_column.strip() or "id"
    card = cardinality.strip().lower() or "many_to_one"
    if card not in _CARDINALITIES:
        raise ValueError(f"cardinality must be one of {sorted(_CARDINALITIES)}")
    if not from_name or not from_col or not to_name:
        raise ValueError("from_entity, from_column, and to_entity are required")
    rel_id = f"rel_{from_name}_{from_col}_{to_name}".lower()
    rel_id = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in rel_id)
    return add_relationship_to_draft(
        settings,
        relationship={
            "id": rel_id,
            "from_entity": from_name,
            "from_column": from_col,
            "to_entity": to_name,
            "to_column": to_col,
            "cardinality": card,
            "status": status,
            "citation": "manual:builder",
        },
        username=username,
    )


def manual_assign_column_tag(
    settings: DnaSettings,
    entity: str,
    column: str,
    concepts: list[str],
    *,
    username: str,
    status: str = "proposed",
) -> dict[str, Any]:
    entity_name = entity.strip().lower()
    column_name = column.strip()
    concept_ids = [str(c).strip().lower() for c in concepts if str(c).strip()]
    if not entity_name or not column_name:
        raise ValueError("entity and column are required")
    if not concept_ids:
        raise ValueError("at least one concept is required")
    return update_attribute_status(
        settings,
        entity_name,
        column_name,
        status,
        username=username,
        concepts=concept_ids,
    )


def approve_proposed_keys(
    settings: DnaSettings,
    *,
    username: str,
    primary: bool = True,
    foreign: bool = True,
    only_unique: bool = False,
) -> dict[str, Any]:
    """Approve proposed primary and/or foreign keys in the draft.

    When ``only_unique`` is True, primary keys that are not 100% unique are skipped
    instead of approved. Empty tables are always skipped.
    """
    from meshflow.dna.semantic_join_stats import compute_primary_key_stats

    draft = load_semantic_model_draft(settings)
    pk_count = 0
    fk_count = 0
    skipped_empty = 0
    skipped_non_unique = 0
    if primary:
        for entity in draft.get("entities") or []:
            if not isinstance(entity, dict):
                continue
            pk_status = str(entity.get("primary_key_status") or "proposed").strip().lower()
            pk_column = str(entity.get("primary_key") or "").strip()
            if pk_status == "proposed" and pk_column:
                silver = str(entity.get("silver_entity") or "").strip().lower()
                stats = compute_primary_key_stats(settings, silver, pk_column)
                if stats["row_count"] == 0:
                    skipped_empty += 1
                    continue
                if only_unique and not stats.get("pk_unique"):
                    skipped_non_unique += 1
                    entity["pk_stats"] = stats
                    continue
                entity["pk_stats"] = stats
                entity["primary_key_status"] = "approved"
                entity["status"] = "approved"
                pk_count += 1
    if foreign:
        for attribute in draft.get("attributes") or []:
            if not isinstance(attribute, dict):
                continue
            if str(attribute.get("role") or "").strip().lower() != "foreign_key":
                continue
            if str(attribute.get("status") or "proposed").strip().lower() == "proposed":
                attribute["status"] = "approved"
                fk_count += 1
    saved = draft
    if pk_count or fk_count:
        saved = save_semantic_model_draft(settings, draft, username=username)
    return {
        "draft": saved,
        "primary_keys_approved": pk_count,
        "foreign_keys_approved": fk_count,
        "primary_keys_skipped_empty": skipped_empty,
        "primary_keys_skipped_non_unique": skipped_non_unique,
    }


def generate_relationships_from_keys(
    settings: DnaSettings,
    *,
    username: str,
    approve_proposed: bool = True,
) -> dict[str, Any]:
    """Approve proposed keys (optional) and build join proposals for step 2."""
    keys_approved: dict[str, Any] = {"primary_keys_approved": 0, "foreign_keys_approved": 0}
    if approve_proposed:
        keys_approved = approve_proposed_keys(settings, username=username)
    build_result = build_relationships_from_approved_keys(settings, username=username)
    return {"keys_approved": keys_approved, **build_result}


def build_relationships_from_approved_keys(
    settings: DnaSettings,
    *,
    username: str,
    merge_existing: bool = True,
) -> dict[str, Any]:
    from meshflow.dna.semantic_key_profiler import propose_relationships_from_approved_keys

    draft = load_semantic_model_draft(settings)
    entities = list(draft.get("entities") or [])
    proposed = propose_relationships_from_approved_keys(
        settings,
        entities=entities,
        attributes=list(draft.get("attributes") or []),
    )
    existing_by_key = {
        (
            str(rel.get("from_entity") or "").lower(),
            str(rel.get("from_column") or ""),
            str(rel.get("to_entity") or "").lower(),
            str(rel.get("to_column") or ""),
        ): rel
        for rel in draft.get("relationships") or []
        if isinstance(rel, dict)
    }
    added = 0
    refreshed = 0
    for rel in proposed:
        key = (
            str(rel.get("from_entity") or "").lower(),
            str(rel.get("from_column") or ""),
            str(rel.get("to_entity") or "").lower(),
            str(rel.get("to_column") or ""),
        )
        existing = existing_by_key.get(key)
        if existing is not None:
            if isinstance(rel.get("join_stats"), dict):
                existing["join_stats"] = rel["join_stats"]
                existing["confidence"] = rel.get("confidence", existing.get("confidence"))
                refreshed += 1
            continue
        if merge_existing:
            draft.setdefault("relationships", []).append(rel)
            existing_by_key[key] = rel
            added += 1
    if added or refreshed:
        save_semantic_model_draft(settings, draft, username=username)
    return {"added": added, "refreshed": refreshed, "proposed_count": len(proposed)}


def _merge_reference_relationships(settings: DnaSettings, draft: dict[str, Any]) -> int:
    from meshflow.dna.semantic_source_profile import load_latest_source_profile, merge_latest_profile_relationships

    profile = load_latest_source_profile(settings)
    if profile:
        return merge_latest_profile_relationships(draft, profile)

    from meshflow.dna.semantic_source_reference import load_source_semantic_consensus

    consensus = load_source_semantic_consensus(settings)
    if not consensus:
        return 0
    entities = {
        str(e.get("silver_entity") or "").strip().lower()
        for e in draft.get("entities") or []
        if isinstance(e, dict)
    }
    existing = {
        (
            str(rel.get("from_entity") or "").lower(),
            str(rel.get("from_column") or ""),
            str(rel.get("to_entity") or "").lower(),
            str(rel.get("to_column") or ""),
        )
        for rel in draft.get("relationships") or []
        if isinstance(rel, dict)
    }
    added = 0
    for item in consensus.get("relationships") or []:
        if not isinstance(item, dict):
            continue
        if float(item.get("weight") or 0) < 0.5:
            continue
        key = str(item.get("key") or "")
        if "->" not in key:
            continue
        left, right = key.split("->", 1)
        if "." not in left or "." not in right:
            continue
        from_entity, from_column = left.rsplit(".", 1)
        to_entity, to_column = right.rsplit(".", 1)
        if from_entity not in entities or to_entity not in entities:
            continue
        rel_key = (from_entity, from_column, to_entity, to_column)
        if rel_key in existing:
            continue
        rel_id = f"rel_{from_entity}_{from_column.lower()}_{to_entity}"
        draft.setdefault("relationships", []).append(
            {
                "id": rel_id,
                "from_entity": from_entity,
                "from_column": from_column,
                "to_entity": to_entity,
                "to_column": to_column,
                "cardinality": "many_to_one",
                "status": "proposed",
                "confidence": float(item.get("weight") or 0.7),
                "citation": "reference:approved_builds",
                "description": key,
            }
        )
        existing.add(rel_key)
        added += 1
    return added


def complete_builder_step(
    settings: DnaSettings,
    step: str,
    *,
    username: str,
    enable_llm_tagging: bool = True,
) -> dict[str, Any]:
    step_name = step.strip().lower()
    if step_name not in BUILDER_STEPS:
        raise ValueError(f"step must be one of {BUILDER_STEPS}")
    workflow = load_semantic_model_workflow(settings)
    steps = workflow.get("steps_completed") or {}
    steps[step_name] = True
    workflow["steps_completed"] = steps
    step_index = BUILDER_STEPS.index(step_name)
    if step_index < len(BUILDER_STEPS) - 1:
        workflow["current_step"] = BUILDER_STEPS[step_index + 1]
    else:
        workflow["current_step"] = step_name
    workflow[f"step_{step_name}_completed_at"] = datetime.now(UTC).isoformat()
    workflow[f"step_{step_name}_completed_by"] = username
    save_semantic_model_workflow(settings, workflow)

    side_effects: dict[str, Any] = {}
    if step_name == "keys":
        side_effects = generate_relationships_from_keys(settings, username=username)
    elif step_name == "relationships":
        if enable_llm_tagging:
            from meshflow.dna.semantic_init import enrich_semantic_model_llm_tags

            side_effects = enrich_semantic_model_llm_tags(settings, username=username)
        else:
            side_effects = {
                "status": "deferred",
                "llm_tagging": {
                    "tagged_count": 0,
                    "skipped_count": 0,
                    "reason": "deferred_to_background",
                },
            }
    return {"workflow": workflow, "side_effects": side_effects}


def sync_builder_current_step(settings: DnaSettings, page_step: str) -> dict[str, Any]:
    """Move workflow current_step back when the user revisits an earlier builder page."""
    step_name = page_step.strip().lower()
    if step_name not in BUILDER_STEPS:
        raise ValueError(f"step must be one of {BUILDER_STEPS}")
    workflow = load_semantic_model_workflow(settings)
    if not workflow.get("init_completed"):
        return workflow
    current = str(workflow.get("current_step") or BUILDER_STEPS[0])
    try:
        current_idx = BUILDER_STEPS.index(current)
        step_idx = BUILDER_STEPS.index(step_name)
    except ValueError:
        return workflow
    if step_idx < current_idx:
        workflow["current_step"] = step_name
        save_semantic_model_workflow(settings, workflow)
    return workflow


def builder_step_summary(settings: DnaSettings) -> dict[str, Any]:
    workflow = load_semantic_model_workflow(settings)
    draft = load_semantic_model_draft(settings)
    entities = [e for e in draft.get("entities") or [] if isinstance(e, dict)]
    attributes = [a for a in draft.get("attributes") or [] if isinstance(a, dict)]
    pk_approved = sum(
        1 for e in entities if str(e.get("primary_key_status") or "") == "approved"
    )
    fk_approved = sum(
        1
        for a in attributes
        if str(a.get("role") or "") == "foreign_key" and str(a.get("status") or "") == "approved"
    )
    rel_approved = sum(
        1 for r in draft.get("relationships") or [] if str(r.get("status") or "") == "approved"
    )
    tag_approved = sum(
        1
        for a in attributes
        if a.get("concepts") and str(a.get("status") or "") == "approved"
    )
    return {
        "current_step": workflow.get("current_step"),
        "steps_completed": workflow.get("steps_completed") or {},
        "keys": {
            "primary_keys_approved": pk_approved,
            "foreign_keys_approved": fk_approved,
            "entity_count": len(entities),
        },
        "relationships": {
            "approved": rel_approved,
            "total": len(draft.get("relationships") or []),
        },
        "tags": {
            "approved": tag_approved,
            "total_with_concepts": sum(1 for a in attributes if a.get("concepts")),
        },
    }


def build_assistant_semantic_model_context(settings: DnaSettings) -> dict[str, Any]:
    model = load_production_semantic_model(settings) or load_semantic_model_draft(settings)
    coverage = semantic_model_coverage(model)
    return {
        "published": load_production_semantic_model(settings) is not None,
        "version": model.get("version"),
        "status": model.get("status"),
        "coverage": coverage,
        "entities": model.get("entities") or [],
        "relationships": model.get("relationships") or [],
        "open_questions": [
            q
            for q in model.get("questions") or []
            if isinstance(q, dict) and str(q.get("status") or "open") == "open"
        ],
    }
