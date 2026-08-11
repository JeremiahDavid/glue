"""Field semantics — silver column tagging, draft/publish, and assistant context."""

from __future__ import annotations

import io
import json
import re
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from meshflow.dna.settings import DnaSettings
from meshflow.dna.store import (
    read_json_artifact,
    read_silver_entity,
    read_yaml_artifact,
    write_json_artifact,
    write_yaml_artifact,
)
from meshflow.storage.paths import (
    governance_field_semantics_draft_key,
    governance_field_semantics_key,
    governance_field_semantics_manifest_key,
    governance_field_semantics_workflow_key,
    prefix_path,
    silver_entity_parquet_key,
    silver_entity_prefix,
)

OPERATIONAL_CONCEPT_CATALOG_NAME = "operational_concept_catalog.yaml"
_MAX_SCHEMA_ERRORS = 5
_SLUG_RE = re.compile(r"[^a-z0-9]+")
_CAMEL_BOUNDARY_RE = re.compile(r"([a-z0-9])([A-Z])")
_PREVIEW_LIMIT = 20

# Master-dimension shortcuts for common BC display/number fields on dimension tables only.
_ENTITY_DISPLAY_NAME_CONCEPTS: dict[str, str] = {
    "customers": "customer_name",
    "vendors": "vendor_name",
    "items": "item_name",
}
_ENTITY_NUMBER_CONCEPTS: dict[str, str] = {
    "customers": "customer_number",
    "items": "item_number",
}


def field_semantics_schema_path() -> Path:
    return Path(__file__).resolve().parent / "schema" / "field-semantics.schema.json"


def operational_concept_catalog_path() -> Path:
    return Path(__file__).resolve().parent / "packs" / OPERATIONAL_CONCEPT_CATALOG_NAME


@lru_cache(maxsize=1)
def _field_semantics_validator() -> Draft202012Validator:
    schema_path = field_semantics_schema_path()
    if not schema_path.is_file():
        raise FileNotFoundError(f"Field semantics schema not found: {schema_path}")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise ValueError(f"Invalid field-semantics.schema.json: {exc.message}") from exc
    return Draft202012Validator(schema)


def _format_schema_path(error: Any) -> str:
    parts = [str(part) for part in error.absolute_path]
    return ".".join(parts) if parts else "(root)"


def validate_field_semantics_schema(payload: dict[str, Any]) -> None:
    if not isinstance(payload, dict):
        raise ValueError("Field semantics must be a mapping")

    validator = _field_semantics_validator()
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
    raise ValueError("Field semantics schema error — " + "; ".join(lines) + suffix)


def load_operational_concept_catalog() -> dict[str, Any]:
    path = operational_concept_catalog_path()
    if not path.is_file():
        raise FileNotFoundError(f"Operational concept catalog not found: {path}")
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Operational concept catalog must be a mapping")
    return payload


def _concept_index(catalog: dict[str, Any]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for item in catalog.get("concepts") or []:
        if isinstance(item, dict) and item.get("id"):
            index[str(item["id"])] = item
    return index


_catalog_lookup_cache: tuple[set[str], dict[str, str]] | None = None


def _catalog_lookup() -> tuple[set[str], dict[str, str]]:
    global _catalog_lookup_cache
    if _catalog_lookup_cache is not None:
        return _catalog_lookup_cache

    catalog = load_operational_concept_catalog()
    known: set[str] = set()
    alias_to_id: dict[str, str] = {}
    for item in catalog.get("concepts") or []:
        if not isinstance(item, dict):
            continue
        concept_id = str(item.get("id") or "").strip().lower()
        if not concept_id:
            continue
        known.add(concept_id)
        alias_to_id[concept_id] = concept_id
        for alias in item.get("aliases") or []:
            alias_text = str(alias).strip()
            if not alias_text:
                continue
            try:
                alias_key = slugify_concept_id(alias_text)
            except ValueError:
                continue
            alias_to_id[alias_key] = concept_id

    _catalog_lookup_cache = (known, alias_to_id)
    return _catalog_lookup_cache


def catalog_concept_ids() -> set[str]:
    known, _ = _catalog_lookup()
    return set(known)


def filter_catalog_concepts(concepts: list[str]) -> list[str]:
    """Return concept ids known to the operational catalog (aliases resolved)."""
    known, alias_to_id = _catalog_lookup()
    result: list[str] = []
    seen: set[str] = set()
    for raw in concepts:
        candidate = str(raw).strip().lower()
        if not candidate:
            continue
        resolved = candidate if candidate in known else alias_to_id.get(candidate)
        if resolved and resolved not in seen:
            seen.add(resolved)
            result.append(resolved)
    return result


def camel_to_snake(name: str) -> str:
    """Convert camelCase / PascalCase identifiers to snake_case."""
    text = _CAMEL_BOUNDARY_RE.sub(r"\1_\2", str(name or "").strip())
    return _SLUG_RE.sub("_", text.lower()).strip("_")


def _title_words(text: str) -> str:
    return " ".join(part.capitalize() for part in camel_to_snake(text).split("_") if part)


def entity_singular_label(entity: str) -> str:
    """Human label for a silver entity (singular when obvious)."""
    name = entity.strip().lower()
    if name.endswith("_lines"):
        name = name[:-6]
    words = [part for part in name.split("_") if part]
    if words and words[-1].endswith("s") and not words[-1].endswith("ss"):
        words[-1] = words[-1][:-1]
    if words:
        return " ".join(word.capitalize() for word in words)
    return _title_words(name)


def entity_column_concept_id(entity: str, column: str) -> str:
    """Stable entity-scoped concept id: table + field (e.g. items_display_name)."""
    entity_part = camel_to_snake(entity)
    column_part = camel_to_snake(column)
    return f"{entity_part}_{column_part}" if entity_part else column_part


def coerce_entity_column_concepts(
    entity: str,
    column: str,
    concepts: list[str] | None = None,
    *,
    hint_role: str = "",
) -> list[str]:
    """Resolve concepts for LLM output using the same rules as init tagging."""
    return resolve_entity_column_concepts(
        entity,
        column,
        hint={"role": hint_role, "concepts": concepts or []},
    )


def entity_column_concept_label(entity: str, column: str) -> str:
    """Readable label for an entity-scoped concept (e.g. purchase_invoices.orderNumber)."""
    column_key = column.strip().lower()
    entity_label = entity_singular_label(entity)
    if column_key == "displayname":
        return f"{entity_label} Name"
    if column_key == "number":
        return f"{entity_label} Number"
    column_label = _title_words(column)
    if column_key.endswith("number") and column_key != "number":
        domain = entity_label.split()[0] if entity_label else ""
        if domain and domain.lower() not in column_label.lower():
            return f"{domain} {column_label}"
    return f"{entity_label} {column_label}"


def resolve_entity_column_concepts(
    entity: str,
    column: str,
    *,
    hint: dict[str, Any] | None = None,
    column_tags: dict[str, Any] | None = None,
) -> list[str]:
    """Resolve tag concepts for one silver column using entity context first."""
    entity_name = entity.strip().lower()
    column_name = column.strip()
    if not entity_name or not column_name:
        return []

    tag_entry = (column_tags or {}).get(f"{entity_name}.{column_name}")
    if isinstance(tag_entry, dict):
        tagged = filter_catalog_concepts([str(c) for c in tag_entry.get("concepts") or [] if str(c).strip()])
        if tagged:
            return tagged
        raw_tagged = [str(c).strip().lower() for c in tag_entry.get("concepts") or [] if str(c).strip()]
        if raw_tagged:
            return raw_tagged

    column_key = column_name.lower()
    if column_key == "displayname":
        master = _ENTITY_DISPLAY_NAME_CONCEPTS.get(entity_name)
        if master:
            return [master]
    if column_key == "number":
        master = _ENTITY_NUMBER_CONCEPTS.get(entity_name)
        if master:
            return [master]

    scoped_id = entity_column_concept_id(entity_name, column_name)
    return [scoped_id]


def _custom_concept_index(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for item in payload.get("custom_concepts") or []:
        if isinstance(item, dict) and item.get("id"):
            index[str(item["id"])] = item
    return index


def register_entity_scoped_custom_concepts(
    payload: dict[str, Any],
    *,
    mappings: list[dict[str, Any]],
) -> None:
    """Add custom concept entries for entity-scoped tags not in the operational catalog."""
    known = catalog_concept_ids()
    custom_index = _custom_concept_index(payload)
    custom_list = [dict(item) for item in payload.get("custom_concepts") or [] if isinstance(item, dict)]
    for mapping in mappings:
        if not isinstance(mapping, dict):
            continue
        entity = str(mapping.get("silver_entity") or "").strip().lower()
        column = str(mapping.get("column") or "").strip()
        for concept_id in mapping.get("concepts") or []:
            normalized = str(concept_id).strip().lower()
            if not normalized or normalized in known or normalized in custom_index:
                continue
            label = (
                entity_column_concept_label(entity, column)
                if entity and column
                else normalized.replace("_", " ").title()
            )
            entry = {
                "id": normalized,
                "label": label,
                "category": "entity_column",
                "description": f"Entity-scoped concept for {entity}.{column}" if entity and column else "",
            }
            custom_index[normalized] = entry
            custom_list.append(entry)
    payload["custom_concepts"] = custom_list


def _validate_concept_refs(payload: dict[str, Any]) -> None:
    catalog = load_operational_concept_catalog()
    known = set(_concept_index(catalog))
    known.update(_custom_concept_index(payload))
    for mapping in payload.get("mappings") or []:
        if not isinstance(mapping, dict):
            continue
        for concept_id in mapping.get("concepts") or []:
            if str(concept_id) not in known:
                raise ValueError(f"Unknown concept id: {concept_id!r}")


def _normalize_field_semantics(payload: dict[str, Any], *, settings: DnaSettings) -> dict[str, Any]:
    normalized: dict[str, Any] = {
        "version": str(payload.get("version") or "1.0.0").strip(),
        "status": str(payload.get("status") or "draft").strip().lower(),
        "source": str(payload.get("source") or settings.source).strip().lower(),
        "updated_at": str(payload.get("updated_at") or datetime.now(UTC).isoformat()),
        "updated_by": str(payload.get("updated_by") or ""),
        "custom_concepts": [],
        "mappings": [],
    }
    if normalized["status"] not in {"draft", "production"}:
        raise ValueError("status must be 'draft' or 'production'")

    custom: list[dict[str, Any]] = []
    seen_custom: set[str] = set()
    for item in payload.get("custom_concepts") or []:
        if not isinstance(item, dict):
            continue
        concept_id = str(item.get("id") or "").strip().lower()
        label = str(item.get("label") or "").strip()
        category = str(item.get("category") or "").strip().lower()
        if not concept_id or not label or not category:
            raise ValueError("custom_concepts entries require id, label, and category")
        if concept_id in seen_custom:
            raise ValueError(f"Duplicate custom concept id: {concept_id!r}")
        seen_custom.add(concept_id)
        entry: dict[str, Any] = {
            "id": concept_id,
            "label": label,
            "category": category,
        }
        description = str(item.get("description") or "").strip()
        if description:
            entry["description"] = description
        custom.append(entry)
    normalized["custom_concepts"] = custom

    mappings: list[dict[str, Any]] = []
    seen_pairs: set[tuple[str, str]] = set()
    for item in payload.get("mappings") or []:
        if not isinstance(item, dict):
            continue
        silver_entity = str(item.get("silver_entity") or "").strip().lower()
        column = str(item.get("column") or "").strip()
        concepts_raw = item.get("concepts") or []
        if not silver_entity or not column:
            raise ValueError("mappings require silver_entity and column")
        pair = (silver_entity, column)
        if pair in seen_pairs:
            raise ValueError(f"Duplicate mapping for {silver_entity}.{column}")
        seen_pairs.add(pair)
        concepts = [str(c).strip().lower() for c in concepts_raw if str(c).strip()]
        if not concepts:
            raise ValueError(f"mappings[{silver_entity}.{column}] requires at least one concept")
        entry = {
            "silver_entity": silver_entity,
            "column": column,
            "concepts": concepts,
        }
        notes = str(item.get("notes") or "").strip()
        if notes:
            entry["notes"] = notes
        mappings.append(entry)
    normalized["mappings"] = mappings
    return normalized


def default_field_semantics_draft(settings: DnaSettings, *, username: str = "") -> dict[str, Any]:
    return {
        "version": "1.0.0",
        "status": "draft",
        "source": settings.source.strip().lower(),
        "updated_at": datetime.now(UTC).isoformat(),
        "updated_by": username,
        "custom_concepts": [],
        "mappings": [],
    }


def load_field_semantics_workflow(settings: DnaSettings) -> dict[str, Any]:
    pack_id = settings.dna_config_id
    payload = read_json_artifact(settings, governance_field_semantics_workflow_key(pack_id))
    if not payload:
        return {
            "pack_id": pack_id,
            "active_version": None,
            "history": [],
            "draft_updated_at": None,
        }
    return payload


def save_field_semantics_workflow(settings: DnaSettings, workflow: dict[str, Any]) -> str:
    pack_id = settings.dna_config_id
    workflow = dict(workflow)
    workflow["pack_id"] = pack_id
    return write_json_artifact(settings, governance_field_semantics_workflow_key(pack_id), workflow)


def load_field_semantics_draft(settings: DnaSettings) -> dict[str, Any]:
    pack_id = settings.dna_config_id
    payload = read_yaml_artifact(settings, governance_field_semantics_draft_key(pack_id))
    if not payload:
        return default_field_semantics_draft(settings)
    normalized = _normalize_field_semantics(payload, settings=settings)
    normalized["status"] = "draft"
    return normalized


def save_field_semantics_draft(
    settings: DnaSettings,
    payload: dict[str, Any],
    *,
    username: str,
) -> dict[str, Any]:
    normalized = _normalize_field_semantics(payload, settings=settings)
    normalized["status"] = "draft"
    normalized["updated_at"] = datetime.now(UTC).isoformat()
    normalized["updated_by"] = username
    _validate_concept_refs(normalized)
    validate_field_semantics_schema(normalized)
    write_yaml_artifact(
        settings,
        governance_field_semantics_draft_key(settings.dna_config_id),
        normalized,
    )
    workflow = load_field_semantics_workflow(settings)
    workflow["draft_updated_at"] = normalized["updated_at"]
    save_field_semantics_workflow(settings, workflow)
    return normalized


def load_production_field_semantics(settings: DnaSettings) -> dict[str, Any] | None:
    workflow = load_field_semantics_workflow(settings)
    version = workflow.get("active_version")
    if not version:
        return None
    pack_id = settings.dna_config_id
    payload = read_yaml_artifact(settings, governance_field_semantics_key(pack_id, str(version)))
    if not payload:
        return None
    normalized = _normalize_field_semantics(payload, settings=settings)
    normalized["status"] = "production"
    normalized["version"] = str(version)
    return normalized


def _bump_patch_version(version: str) -> str:
    parts = str(version or "1.0.0").strip().split(".")
    if len(parts) != 3:
        return "1.0.1"
    try:
        major, minor, patch = (int(parts[0]), int(parts[1]), int(parts[2]))
    except ValueError:
        return "1.0.1"
    return f"{major}.{minor}.{patch + 1}"


def publish_field_semantics(
    settings: DnaSettings,
    *,
    username: str,
    version: str | None = None,
) -> dict[str, Any]:
    draft = load_field_semantics_draft(settings)
    draft["updated_by"] = username
    draft["updated_at"] = datetime.now(UTC).isoformat()
    _validate_concept_refs(draft)
    validate_field_semantics_schema(draft)

    workflow = load_field_semantics_workflow(settings)
    current = workflow.get("active_version")
    next_version = (version or "").strip() or _bump_patch_version(str(current or draft.get("version") or "1.0.0"))

    published = dict(draft)
    published["status"] = "production"
    published["version"] = next_version

    pack_id = settings.dna_config_id
    write_yaml_artifact(
        settings,
        governance_field_semantics_key(pack_id, next_version),
        published,
    )
    manifest = {
        "pack_id": pack_id,
        "version": next_version,
        "status": "production",
        "published_at": published["updated_at"],
        "published_by": username,
        "mapping_count": len(published.get("mappings") or []),
        "custom_concept_count": len(published.get("custom_concepts") or []),
    }
    write_json_artifact(
        settings,
        governance_field_semantics_manifest_key(pack_id, next_version),
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
            "notes": "Published field semantics",
        }
    )
    workflow["active_version"] = next_version
    workflow["history"] = history
    workflow["draft_updated_at"] = published["updated_at"]
    save_field_semantics_workflow(settings, workflow)

    write_yaml_artifact(
        settings,
        governance_field_semantics_draft_key(pack_id),
        published,
    )
    return published


def discard_field_semantics_draft(settings: DnaSettings, *, username: str) -> dict[str, Any]:
    production = load_production_field_semantics(settings)
    if production:
        draft = dict(production)
        draft["status"] = "draft"
    else:
        draft = default_field_semantics_draft(settings, username=username)
    return save_field_semantics_draft(settings, draft, username=username)


def ensure_field_semantics_seed(settings: DnaSettings, *, username: str = "system") -> dict[str, Any]:
    """Idempotent seed of draft + workflow when field semantics artifacts are missing."""
    pack_id = settings.dna_config_id
    draft_key = governance_field_semantics_draft_key(pack_id)
    workflow_key = governance_field_semantics_workflow_key(pack_id)
    draft_exists = read_yaml_artifact(settings, draft_key) is not None
    workflow_exists = read_json_artifact(settings, workflow_key) is not None
    if draft_exists and workflow_exists:
        return {"status": "skipped", "pack_id": pack_id}

    draft = default_field_semantics_draft(settings, username=username)
    write_yaml_artifact(settings, draft_key, draft)
    if not workflow_exists:
        save_field_semantics_workflow(
            settings,
            {
                "pack_id": pack_id,
                "active_version": None,
                "history": [],
                "draft_updated_at": draft["updated_at"],
            },
        )
    return {"status": "initialized", "pack_id": pack_id}


def list_silver_entities(settings: DnaSettings) -> list[str]:
    from meshflow.entity_registry import catalog_entity_names

    source = settings.source.strip().lower()
    connector = source
    if connector == "dbc":
        connector = "dbc"
    try:
        names = catalog_entity_names(connector, {})
    except (ValueError, ImportError):
        names = []
    return sorted({name.strip().lower() for name in names if name.strip()})


def _parquet_schema_columns(settings: DnaSettings, entity: str) -> list[str]:
    import pyarrow.parquet as pq

    entity_name = entity.strip().lower()
    if settings.s3_bucket:
        import boto3

        key = silver_entity_parquet_key(settings.source, entity_name)
        payload = boto3.client("s3").get_object(Bucket=settings.s3_bucket, Key=key)["Body"].read()
        schema = pq.read_schema(io.BytesIO(payload))
        return [str(field.name) for field in schema]
    path = prefix_path(
        settings.data_dir,
        silver_entity_prefix(settings.source, entity_name),
        "data.parquet",
    )
    if not path.is_file():
        return []
    schema = pq.read_schema(path)
    return [str(field.name) for field in schema]


def discover_silver_columns(settings: DnaSettings, entity: str) -> list[str]:
    columns = _parquet_schema_columns(settings, entity)
    if columns:
        return columns
    rows = read_silver_entity(settings, entity)
    if not rows:
        return []
    keys: set[str] = set()
    for row in rows[:50]:
        if isinstance(row, dict):
            keys.update(row.keys())
    return sorted(keys)


def preview_silver_entity(
    settings: DnaSettings,
    entity: str,
    *,
    limit: int = _PREVIEW_LIMIT,
) -> list[dict[str, Any]]:
    rows = read_silver_entity(settings, entity)
    return rows[: max(1, limit)]


def _resolve_concept_labels(payload: dict[str, Any]) -> dict[str, str]:
    catalog = load_operational_concept_catalog()
    labels = {cid: str(meta.get("label") or cid) for cid, meta in _concept_index(catalog).items()}
    for cid, meta in _custom_concept_index(payload).items():
        labels[cid] = str(meta.get("label") or cid)
    return labels


def field_semantics_summary(payload: dict[str, Any]) -> dict[str, Any]:
    mappings = payload.get("mappings") or []
    entities = sorted({str(m.get("silver_entity") or "") for m in mappings if m.get("silver_entity")})
    return {
        "version": payload.get("version"),
        "status": payload.get("status"),
        "source": payload.get("source"),
        "mapping_count": len(mappings),
        "entity_count": len(entities),
        "custom_concept_count": len(payload.get("custom_concepts") or []),
    }


def _comparable_semantics_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "source": payload.get("source"),
        "custom_concepts": payload.get("custom_concepts") or [],
        "mappings": payload.get("mappings") or [],
    }


def draft_differs_from_production(settings: DnaSettings) -> bool:
    draft = load_field_semantics_draft(settings)
    production = load_production_field_semantics(settings)
    if production is None:
        return bool(draft.get("mappings") or draft.get("custom_concepts"))
    return yaml.safe_dump(_comparable_semantics_payload(draft), sort_keys=True) != yaml.safe_dump(
        _comparable_semantics_payload(production),
        sort_keys=True,
    )


def build_assistant_field_semantics_context(settings: DnaSettings) -> dict[str, Any]:
    payload = load_production_field_semantics(settings)
    if not payload:
        return {
            "published": False,
            "summary": field_semantics_summary(default_field_semantics_draft(settings)),
            "mappings": [],
            "concepts_by_id": {},
        }

    labels = _resolve_concept_labels(payload)
    enriched: list[dict[str, Any]] = []
    for mapping in payload.get("mappings") or []:
        if not isinstance(mapping, dict):
            continue
        concepts = [str(c) for c in mapping.get("concepts") or []]
        enriched.append(
            {
                "silver_entity": mapping.get("silver_entity"),
                "column": mapping.get("column"),
                "concepts": concepts,
                "concept_labels": [labels.get(c, c) for c in concepts],
                "notes": mapping.get("notes") or "",
            }
        )
    return {
        "published": True,
        "summary": field_semantics_summary(payload),
        "mappings": enriched,
        "custom_concepts": payload.get("custom_concepts") or [],
        "concepts_by_id": labels,
    }


def slugify_concept_id(label: str) -> str:
    slug = _SLUG_RE.sub("_", label.strip().lower()).strip("_")
    if not slug:
        raise ValueError("Concept label must contain at least one letter or number")
    if not slug[0].isalpha():
        slug = f"c_{slug}"
    return slug[:48]
