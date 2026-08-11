"""Latest per-source profiling baseline — documentation + approved builds, read at init."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from meshflow.dna.settings import DnaSettings
from meshflow.dna.store import read_yaml_artifact, write_yaml_artifact
from meshflow.storage.paths import governance_source_semantic_latest_profile_key

_BASELINE_MARKER = "latest_source_profile"
_MIN_CONSENSUS_WEIGHT = 0.34
_REFERENCE_CITATION = "reference:approved_builds"


def _index_entities(items: list[Any]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        silver = str(item.get("silver_entity") or "").strip().lower()
        if silver:
            indexed[silver] = dict(item)
    return indexed


def _relationship_from_consensus_key(key: str, *, weight: float, ratio: float) -> dict[str, Any] | None:
    text = str(key or "").strip()
    if "->" not in text or "." not in text:
        return None
    left, right = text.split("->", 1)
    if "." not in left or "." not in right:
        return None
    from_entity, from_column = left.rsplit(".", 1)
    to_entity, to_column = right.rsplit(".", 1)
    from_entity = from_entity.strip().lower()
    to_entity = to_entity.strip().lower()
    from_column = from_column.strip()
    to_column = to_column.strip() or "id"
    if not from_entity or not from_column or not to_entity:
        return None
    rel_id = f"rel_{from_entity}_{from_column.lower()}_{to_entity}"
    return {
        "id": rel_id,
        "from_entity": from_entity,
        "from_column": from_column,
        "to_entity": to_entity,
        "to_column": to_column,
        "cardinality": "many_to_one",
        "status": "proposed",
        "confidence": round(min(1.0, float(weight or 0.7)), 4),
        "citation": _REFERENCE_CITATION,
        "reference_weight": weight,
        "reference_ratio": ratio,
    }


def _documentation_baseline(source: str) -> dict[str, Any]:
    from meshflow.dna.semantic_knowledge_base import load_connector_documentation_hints

    return load_connector_documentation_hints(source)


def build_latest_source_profile(settings: DnaSettings, source: str | None = None) -> dict[str, Any]:
    """Merge connector documentation with approved-build consensus into one baseline."""
    from meshflow.dna.semantic_source_reference import load_source_semantic_consensus

    connector = (source or settings.source).strip().lower()
    documentation = _documentation_baseline(connector)
    consensus = load_source_semantic_consensus(settings, connector) or {}
    approved_build_count = int(consensus.get("build_count") or 0)

    entities = _index_entities(list(documentation.get("entities") or []))
    relationships: dict[str, dict[str, Any]] = {}
    for rel in documentation.get("relationships") or []:
        if not isinstance(rel, dict):
            continue
        rel_id = str(rel.get("id") or "").strip().lower()
        if rel_id:
            relationships[rel_id] = dict(rel)

    for entity_name, role_info in (consensus.get("entity_roles") or {}).items():
        if not isinstance(role_info, dict):
            continue
        weight = float(role_info.get("weight") or 0.0)
        if weight < _MIN_CONSENSUS_WEIGHT:
            continue
        entry = entities.setdefault(
            entity_name,
            {"silver_entity": entity_name, "status": "proposed"},
        )
        entry["role"] = str(role_info.get("role") or entry.get("role") or "reference")
        entry["citation"] = _REFERENCE_CITATION
        entry["reference_weight"] = weight

    for entity_name, pk_info in (consensus.get("primary_keys") or {}).items():
        if not isinstance(pk_info, dict):
            continue
        weight = float(pk_info.get("weight") or 0.0)
        column = str(pk_info.get("column") or "").strip()
        if not column or weight < _MIN_CONSENSUS_WEIGHT:
            continue
        entry = entities.setdefault(
            entity_name,
            {"silver_entity": entity_name, "status": "proposed"},
        )
        entry["primary_key"] = column
        entry["primary_key_status"] = "proposed"
        entry["citation"] = _REFERENCE_CITATION
        entry["reference_weight"] = weight

    for entity_name, fk_items in (consensus.get("foreign_keys") or {}).items():
        if not isinstance(fk_items, list):
            continue
        entry = entities.setdefault(
            entity_name,
            {"silver_entity": entity_name, "status": "proposed"},
        )
        merged_fks: list[dict[str, str]] = list(entry.get("foreign_keys") or [])
        seen = {str(item.get("column") or "") for item in merged_fks if isinstance(item, dict)}
        for item in fk_items:
            if not isinstance(item, dict):
                continue
            weight = float(item.get("weight") or 0.0)
            column = str(item.get("column") or "").strip()
            if not column or weight < _MIN_CONSENSUS_WEIGHT:
                continue
            if column in seen:
                continue
            seen.add(column)
            merged_fks.append(
                {
                    "column": column,
                    "to_entity": str(item.get("to_entity") or "").strip().lower(),
                    "to_column": str(item.get("to_column") or "id").strip(),
                    "citation": _REFERENCE_CITATION,
                    "reference_weight": weight,
                }
            )
        if merged_fks:
            entry["foreign_keys"] = merged_fks

    for item in consensus.get("relationships") or []:
        if not isinstance(item, dict):
            continue
        weight = float(item.get("weight") or 0.0)
        if weight < _MIN_CONSENSUS_WEIGHT:
            continue
        rel = _relationship_from_consensus_key(
            str(item.get("key") or ""),
            weight=weight,
            ratio=float(item.get("ratio") or 0.0),
        )
        if rel and rel["id"] not in relationships:
            relationships[rel["id"]] = rel

    column_hints = dict(documentation.get("column_hints") or {})
    entity_column_hints = dict(documentation.get("entity_column_hints") or {})
    column_tags = dict(consensus.get("column_tags") or {})

    return {
        "source": connector,
        "baseline": _BASELINE_MARKER,
        "generated_at": datetime.now(UTC).isoformat(),
        "documentation_included": True,
        "approved_build_count": approved_build_count,
        "description": str(documentation.get("description") or "").strip(),
        "entities": [entities[name] for name in sorted(entities)],
        "relationships": [relationships[key] for key in sorted(relationships)],
        "column_hints": column_hints,
        "entity_column_hints": entity_column_hints,
        "column_tags": column_tags,
        "questions": list(documentation.get("questions") or []),
    }


def load_latest_source_profile(settings: DnaSettings, source: str | None = None) -> dict[str, Any] | None:
    connector = (source or settings.source).strip().lower()
    payload = read_yaml_artifact(settings, governance_source_semantic_latest_profile_key(connector))
    return payload if isinstance(payload, dict) and payload.get("baseline") == _BASELINE_MARKER else None


def save_latest_source_profile(settings: DnaSettings, profile: dict[str, Any]) -> dict[str, Any]:
    connector = str(profile.get("source") or settings.source).strip().lower()
    write_yaml_artifact(settings, governance_source_semantic_latest_profile_key(connector), profile)
    return profile


def rebuild_latest_source_profile(settings: DnaSettings, source: str | None = None) -> dict[str, Any]:
    profile = build_latest_source_profile(settings, source)
    return save_latest_source_profile(settings, profile)


def ensure_latest_source_profile(settings: DnaSettings, source: str | None = None) -> dict[str, Any]:
    """Build the latest profile only when missing (first init for this source)."""
    existing = load_latest_source_profile(settings, source)
    if existing:
        return {"built": False, "profile": existing}
    profile = rebuild_latest_source_profile(settings, source)
    return {"built": True, "profile": profile}


def latest_profile_to_hints(profile: dict[str, Any]) -> dict[str, Any]:
    """Shape consumed by structure proposal and key profiling."""
    return {
        "source": str(profile.get("source") or "").strip().lower(),
        "description": str(profile.get("description") or "").strip(),
        "entities": list(profile.get("entities") or []),
        "relationships": list(profile.get("relationships") or []),
        "column_hints": dict(profile.get("column_hints") or {}),
        "entity_column_hints": dict(profile.get("entity_column_hints") or {}),
        "column_tags": dict(profile.get("column_tags") or {}),
        "questions": list(profile.get("questions") or []),
        "baseline": _BASELINE_MARKER,
        "baseline_meta": {
            "generated_at": profile.get("generated_at"),
            "approved_build_count": profile.get("approved_build_count"),
            "documentation_included": profile.get("documentation_included"),
        },
    }


def load_profiling_baseline_hints(settings: DnaSettings) -> dict[str, Any]:
    """Read-only baseline for init/re-run profiling (latest profile file only)."""
    profile = load_latest_source_profile(settings)
    if not profile:
        raise ValueError(
            "Latest source profile is missing — initialize the data source before re-running profiling"
        )
    return latest_profile_to_hints(profile)


def apply_latest_profile_tags_to_attributes(
    attributes: list[dict[str, Any]],
    profile: dict[str, Any] | None,
) -> int:
    """Pre-fill column tags from the latest source profile before LLM tagging."""
    if not profile:
        return 0
    column_tags = profile.get("column_tags") if isinstance(profile.get("column_tags"), dict) else {}
    if not column_tags:
        return 0
    applied = 0
    for attribute in attributes:
        if not isinstance(attribute, dict):
            continue
        if attribute.get("concepts"):
            continue
        if str(attribute.get("role") or "") == "foreign_key":
            continue
        entity = str(attribute.get("entity") or "").strip().lower()
        column = str(attribute.get("column") or "").strip()
        ref = column_tags.get(f"{entity}.{column}")
        if not isinstance(ref, dict):
            continue
        weight = float(ref.get("weight") or 0.0)
        if weight < _MIN_CONSENSUS_WEIGHT:
            continue
        concepts = [str(c) for c in ref.get("concepts") or [] if str(c).strip()]
        if not concepts:
            continue
        attribute["concepts"] = concepts
        attribute["status"] = "proposed"
        attribute["citation"] = _REFERENCE_CITATION
        attribute["notes"] = (
            f"Suggested from {ref.get('count', 0)} approved build(s) "
            f"({int(float(ref.get('ratio') or 0) * 100)}% consensus)"
        )
        applied += 1
    return applied


def merge_latest_profile_relationships(
    draft: dict[str, Any],
    profile: dict[str, Any] | None,
) -> int:
    """Add relationship proposals from the latest source profile."""
    if not profile:
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
    for item in profile.get("relationships") or []:
        if not isinstance(item, dict):
            continue
        from_entity = str(item.get("from_entity") or "").strip().lower()
        to_entity = str(item.get("to_entity") or "").strip().lower()
        from_column = str(item.get("from_column") or "").strip()
        to_column = str(item.get("to_column") or "id").strip()
        if from_entity not in entities or to_entity not in entities or not from_column:
            continue
        rel_key = (from_entity, from_column, to_entity, to_column)
        if rel_key in existing:
            continue
        draft.setdefault("relationships", []).append(dict(item))
        existing.add(rel_key)
        added += 1
    return added
