"""Approved semantic build snapshots and cross-tenant source consensus for profiling."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime
from typing import Any

from meshflow.dna.settings import DnaSettings
from meshflow.dna.store import read_json_artifact, read_yaml_artifact, write_json_artifact, write_yaml_artifact
from meshflow.storage.paths import (
    governance_source_semantic_reference_build_key,
    governance_source_semantic_reference_consensus_key,
    governance_source_semantic_reference_index_key,
)

_REFERENCE_CITATION = "reference:approved_builds"
_MIN_CONSENSUS_RATIO = 0.34


def extract_reference_profile(
    model: dict[str, Any],
    *,
    pack_id: str,
    version: str,
    published_by: str,
    published_at: str | None = None,
) -> dict[str, Any]:
    """Normalize a published semantic model into a source-level reference profile."""
    source = str(model.get("source") or "").strip().lower()
    primary_keys: dict[str, str] = {}
    entity_roles: dict[str, str] = {}
    for entity in model.get("entities") or []:
        if not isinstance(entity, dict):
            continue
        silver = str(entity.get("silver_entity") or "").strip().lower()
        if not silver:
            continue
        entity_roles[silver] = str(entity.get("role") or "").strip().lower()
        pk = str(entity.get("primary_key") or "").strip()
        if pk:
            primary_keys[silver] = pk

    foreign_keys: dict[str, list[dict[str, str]]] = defaultdict(list)
    column_tags: list[dict[str, Any]] = []
    for attribute in model.get("attributes") or []:
        if not isinstance(attribute, dict):
            continue
        if str(attribute.get("status") or "") == "rejected":
            continue
        entity = str(attribute.get("entity") or "").strip().lower()
        column = str(attribute.get("column") or "").strip()
        if not entity or not column:
            continue
        role = str(attribute.get("role") or "").strip().lower()
        if role == "foreign_key":
            foreign_keys[entity].append(
                {
                    "column": column,
                    "to_entity": str(attribute.get("fk_target_entity") or "").strip().lower(),
                    "to_column": str(attribute.get("fk_target_column") or "id").strip(),
                }
            )
            continue
        concepts = [str(c) for c in attribute.get("concepts") or [] if str(c).strip()]
        if not concepts:
            continue
        entry: dict[str, Any] = {
            "entity": entity,
            "column": column,
            "concepts": concepts,
        }
        if role:
            entry["role"] = role
        column_tags.append(entry)

    relationships: list[dict[str, str]] = []
    for rel in model.get("relationships") or []:
        if not isinstance(rel, dict):
            continue
        if str(rel.get("status") or "") == "rejected":
            continue
        relationships.append(
            {
                "from_entity": str(rel.get("from_entity") or "").strip().lower(),
                "from_column": str(rel.get("from_column") or "").strip(),
                "to_entity": str(rel.get("to_entity") or "").strip().lower(),
                "to_column": str(rel.get("to_column") or "id").strip(),
                "cardinality": str(rel.get("cardinality") or "many_to_one").strip().lower(),
            }
        )

    return {
        "source": source,
        "pack_id": pack_id.strip().lower(),
        "version": str(version).strip(),
        "published_at": published_at or datetime.now(UTC).isoformat(),
        "published_by": published_by,
        "entity_roles": dict(entity_roles),
        "primary_keys": dict(primary_keys),
        "foreign_keys": {key: list(items) for key, items in foreign_keys.items()},
        "relationships": relationships,
        "column_tags": column_tags,
    }


def _build_index_entry(profile: dict[str, Any]) -> dict[str, Any]:
    return {
        "pack_id": profile.get("pack_id"),
        "version": profile.get("version"),
        "published_at": profile.get("published_at"),
        "published_by": profile.get("published_by"),
        "entity_count": len(profile.get("primary_keys") or {}),
        "relationship_count": len(profile.get("relationships") or []),
        "tag_count": len(profile.get("column_tags") or []),
    }


def _upsert_index_entry(index: dict[str, Any], entry: dict[str, Any]) -> None:
    builds = list(index.get("builds") or [])
    pack_id = str(entry.get("pack_id") or "").strip().lower()
    version = str(entry.get("version") or "").strip()
    builds = [
        item
        for item in builds
        if not (
            isinstance(item, dict)
            and str(item.get("pack_id") or "").strip().lower() == pack_id
            and str(item.get("version") or "").strip() == version
        )
    ]
    builds.append(entry)
    builds.sort(key=lambda item: str(item.get("published_at") or ""), reverse=True)
    index["builds"] = builds
    index["build_count"] = len(builds)
    index["updated_at"] = datetime.now(UTC).isoformat()


def build_source_consensus(profiles: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate approved builds — higher weight for elements common across builds."""
    if not profiles:
        return {"build_count": 0}

    source = str(profiles[0].get("source") or "").strip().lower()
    build_count = len(profiles)

    pk_counts: dict[str, Counter[str]] = defaultdict(Counter)
    fk_counts: dict[str, Counter[str]] = defaultdict(Counter)
    rel_counts: Counter[str] = Counter()
    tag_counts: dict[str, Counter[str]] = defaultdict(Counter)
    role_counts: dict[str, Counter[str]] = defaultdict(Counter)

    for profile in profiles:
        for entity, pk in (profile.get("primary_keys") or {}).items():
            if entity and pk:
                pk_counts[str(entity).strip().lower()][str(pk).strip()] += 1
        for entity, role in (profile.get("entity_roles") or {}).items():
            if entity and role:
                role_counts[str(entity).strip().lower()][str(role).strip().lower()] += 1
        for entity, fks in (profile.get("foreign_keys") or {}).items():
            for item in fks or []:
                if not isinstance(item, dict):
                    continue
                column = str(item.get("column") or "").strip()
                to_entity = str(item.get("to_entity") or "").strip().lower()
                to_column = str(item.get("to_column") or "id").strip()
                if not column:
                    continue
                key = f"{column}->{to_entity}.{to_column}"
                fk_counts[str(entity).strip().lower()][key] += 1
        for rel in profile.get("relationships") or []:
            if not isinstance(rel, dict):
                continue
            key = (
                f"{rel.get('from_entity')}.{rel.get('from_column')}"
                f"->{rel.get('to_entity')}.{rel.get('to_column')}"
            )
            rel_counts[key] += 1
        for tag in profile.get("column_tags") or []:
            if not isinstance(tag, dict):
                continue
            entity = str(tag.get("entity") or "").strip().lower()
            column = str(tag.get("column") or "").strip()
            for concept in tag.get("concepts") or []:
                concept_id = str(concept).strip().lower()
                if entity and column and concept_id:
                    tag_counts[f"{entity}.{column}"][concept_id] += 1

    def _ratio(count: int) -> float:
        return round(count / build_count, 4) if build_count else 0.0

    def _weight(count: int) -> float:
        return round(min(1.0, 0.25 + 0.75 * _ratio(count)), 4)

    primary_keys: dict[str, Any] = {}
    for entity, counter in pk_counts.items():
        column, count = counter.most_common(1)[0]
        primary_keys[entity] = {
            "column": column,
            "count": count,
            "ratio": _ratio(count),
            "weight": _weight(count),
        }

    foreign_keys: dict[str, Any] = {}
    for entity, counter in fk_counts.items():
        entries = []
        for key, count in counter.most_common():
            column, rest = key.split("->", 1)
            to_entity, to_column = rest.split(".", 1)
            entries.append(
                {
                    "column": column,
                    "to_entity": to_entity,
                    "to_column": to_column,
                    "count": count,
                    "ratio": _ratio(count),
                    "weight": _weight(count),
                }
            )
        foreign_keys[entity] = entries

    relationships = [
        {
            "key": key,
            "count": count,
            "ratio": _ratio(count),
            "weight": _weight(count),
        }
        for key, count in rel_counts.most_common()
    ]

    column_tags: dict[str, Any] = {}
    for pair, counter in tag_counts.items():
        concept, count = counter.most_common(1)[0]
        column_tags[pair] = {
            "concepts": [concept],
            "count": count,
            "ratio": _ratio(count),
            "weight": _weight(count),
        }

    entity_roles: dict[str, Any] = {}
    for entity, counter in role_counts.items():
        role, count = counter.most_common(1)[0]
        entity_roles[entity] = {
            "role": role,
            "count": count,
            "ratio": _ratio(count),
            "weight": _weight(count),
        }

    return {
        "source": source,
        "build_count": build_count,
        "updated_at": datetime.now(UTC).isoformat(),
        "entity_roles": entity_roles,
        "primary_keys": primary_keys,
        "foreign_keys": foreign_keys,
        "relationships": relationships,
        "column_tags": column_tags,
    }


def load_source_semantic_consensus(settings: DnaSettings, source: str | None = None) -> dict[str, Any] | None:
    connector = (source or settings.source).strip().lower()
    payload = read_yaml_artifact(settings, governance_source_semantic_reference_consensus_key(connector))
    if not payload or not int(payload.get("build_count") or 0):
        return None
    return payload


def load_source_reference_profiles(settings: DnaSettings, source: str | None = None) -> list[dict[str, Any]]:
    connector = (source or settings.source).strip().lower()
    index = read_json_artifact(settings, governance_source_semantic_reference_index_key(connector)) or {}
    profiles: list[dict[str, Any]] = []
    for entry in index.get("builds") or []:
        if not isinstance(entry, dict):
            continue
        pack_id = str(entry.get("pack_id") or "").strip().lower()
        version = str(entry.get("version") or "").strip()
        if not pack_id or not version:
            continue
        profile = read_yaml_artifact(
            settings,
            governance_source_semantic_reference_build_key(connector, pack_id, version),
        )
        if profile:
            profiles.append(profile)
    return profiles


def rebuild_source_consensus(settings: DnaSettings, source: str) -> dict[str, Any]:
    connector = source.strip().lower()
    profiles = load_source_reference_profiles(settings, connector)
    consensus = build_source_consensus(profiles)
    write_yaml_artifact(settings, governance_source_semantic_reference_consensus_key(connector), consensus)
    return consensus


def record_approved_semantic_build(
    settings: DnaSettings,
    model: dict[str, Any],
    *,
    pack_id: str,
    version: str,
    username: str,
) -> dict[str, Any]:
    """Persist a full approved semantic profile and refresh source consensus."""
    profile = extract_reference_profile(
        model,
        pack_id=pack_id,
        version=version,
        published_by=username,
        published_at=str(model.get("updated_at") or ""),
    )
    source = profile["source"]
    write_yaml_artifact(
        settings,
        governance_source_semantic_reference_build_key(source, pack_id, version),
        profile,
    )
    index = read_json_artifact(settings, governance_source_semantic_reference_index_key(source)) or {
        "source": source,
        "builds": [],
    }
    index["source"] = source
    _upsert_index_entry(index, _build_index_entry(profile))
    write_json_artifact(settings, governance_source_semantic_reference_index_key(source), index)
    consensus = rebuild_source_consensus(settings, source)
    latest_profile: dict[str, Any] | None = None
    try:
        from meshflow.dna.semantic_source_profile import rebuild_latest_source_profile

        latest_profile = rebuild_latest_source_profile(settings, source)
    except Exception:  # noqa: BLE001 — approved build recording must succeed
        latest_profile = None
    return {
        "profile_key": governance_source_semantic_reference_build_key(source, pack_id, version),
        "build_count": consensus.get("build_count", 0),
        "consensus": consensus,
        "latest_profile_generated_at": (latest_profile or {}).get("generated_at"),
    }


def source_reference_summary(settings: DnaSettings, source: str | None = None) -> dict[str, Any]:
    connector = (source or settings.source).strip().lower()
    index = read_json_artifact(settings, governance_source_semantic_reference_index_key(connector)) or {}
    consensus = load_source_semantic_consensus(settings, connector)
    return {
        "source": connector,
        "approved_build_count": int(index.get("build_count") or 0),
        "consensus_build_count": int((consensus or {}).get("build_count") or 0),
        "consensus_updated_at": (consensus or {}).get("updated_at"),
    }


def reference_pk_weight(consensus: dict[str, Any] | None, entity: str, column: str) -> float:
    if not consensus:
        return 0.0
    entry = (consensus.get("primary_keys") or {}).get(entity.strip().lower())
    if not isinstance(entry, dict):
        return 0.0
    if str(entry.get("column") or "") == column:
        return float(entry.get("weight") or 0.0)
    return 0.0


def reference_fk_weight(
    consensus: dict[str, Any] | None,
    entity: str,
    column: str,
    to_entity: str,
    to_column: str,
) -> float:
    if not consensus:
        return 0.0
    for item in (consensus.get("foreign_keys") or {}).get(entity.strip().lower()) or []:
        if not isinstance(item, dict):
            continue
        if (
            str(item.get("column") or "") == column
            and str(item.get("to_entity") or "") == to_entity.strip().lower()
            and str(item.get("to_column") or "") == to_column
        ):
            return float(item.get("weight") or 0.0)
    return 0.0


def reference_column_tag(
    consensus: dict[str, Any] | None,
    entity: str,
    column: str,
) -> dict[str, Any] | None:
    if not consensus:
        return None
    entry = (consensus.get("column_tags") or {}).get(f"{entity.strip().lower()}.{column.strip()}")
    return entry if isinstance(entry, dict) else None


def apply_reference_consensus_to_key_proposals(
    proposals: dict[str, Any],
    consensus: dict[str, Any] | None,
    *,
    source: str,
) -> dict[str, Any]:
    """Boost PK/FK proposals using cross-tenant approved-build consensus."""
    if not consensus or int(consensus.get("build_count") or 0) <= 0:
        return proposals

    conflicts = list(proposals.get("conflicts") or [])
    merged_pk = dict(proposals.get("primary_keys") or {})
    merged_fk = {key: list(value) for key, value in (proposals.get("foreign_keys") or {}).items()}

    for entity_name, pk_info in (consensus.get("primary_keys") or {}).items():
        if not isinstance(pk_info, dict):
            continue
        ref_column = str(pk_info.get("column") or "").strip()
        weight = float(pk_info.get("weight") or 0.0)
        ratio = float(pk_info.get("ratio") or 0.0)
        if not ref_column or weight <= 0:
            continue

        current = merged_pk.get(entity_name) or {
            "column": ref_column,
            "status": "proposed",
            "citation": "profile:primary_key",
            "profile_candidates": [],
        }
        profile_column = str(current.get("column") or "")
        boosted_candidates = list(current.get("profile_candidates") or [])
        for candidate in boosted_candidates:
            if isinstance(candidate, dict) and str(candidate.get("column") or "") == ref_column:
                candidate["score"] = round(
                    min(1.0, float(candidate.get("score") or 0) + weight * 0.3),
                    4,
                )
                candidate["reference_weight"] = weight
        if not any(str(c.get("column") or "") == ref_column for c in boosted_candidates if isinstance(c, dict)):
            boosted_candidates.append(
                {
                    "column": ref_column,
                    "score": round(min(1.0, 0.55 + weight * 0.35), 4),
                    "reference_weight": weight,
                    "citation": _REFERENCE_CITATION,
                }
            )
        boosted_candidates.sort(
            key=lambda item: (-float(item.get("score") or 0), str(item.get("column") or ""))
        )

        chosen = profile_column or ref_column
        citation = str(current.get("citation") or "profile:primary_key")
        if weight >= 0.5 and ratio >= _MIN_CONSENSUS_RATIO:
            if profile_column and profile_column != ref_column:
                conflicts.append(
                    {
                        "id": f"conflict_ref_pk_{entity_name}",
                        "entity": entity_name,
                        "column": profile_column,
                        "kind": "primary_key",
                        "profile_value": profile_column,
                        "documentation_value": ref_column,
                        "text": (
                            f"Primary key for {entity_name}: profiling suggests {profile_column!r} "
                            f"but {int(ratio * 100)}% of approved {source} builds use {ref_column!r}."
                        ),
                    }
                )
            chosen = ref_column
            citation = _REFERENCE_CITATION

        merged_pk[entity_name] = {
            **current,
            "column": chosen,
            "citation": citation,
            "profile_candidates": boosted_candidates,
            "reference_weight": weight,
            "reference_ratio": ratio,
        }

    for entity_name, fk_items in (consensus.get("foreign_keys") or {}).items():
        if not isinstance(fk_items, list):
            continue
        existing = {str(item.get("column") or ""): item for item in merged_fk.get(entity_name, []) if isinstance(item, dict)}
        for ref in fk_items:
            if not isinstance(ref, dict):
                continue
            column = str(ref.get("column") or "").strip()
            to_entity = str(ref.get("to_entity") or "").strip().lower()
            to_column = str(ref.get("to_column") or "id").strip()
            weight = float(ref.get("weight") or 0.0)
            if not column or weight < _MIN_CONSENSUS_RATIO:
                continue
            if column in existing:
                item = existing[column]
                item["confidence"] = round(
                    min(1.0, float(item.get("confidence") or 0.5) + weight * 0.25),
                    4,
                )
                item["reference_weight"] = weight
                if weight >= 0.5:
                    item["citation"] = f"profile+{_REFERENCE_CITATION}"
            else:
                existing[column] = {
                    "column": column,
                    "to_entity": to_entity,
                    "to_column": to_column,
                    "confidence": round(min(1.0, 0.5 + weight * 0.4), 4),
                    "status": "proposed",
                    "citation": _REFERENCE_CITATION,
                    "reference_weight": weight,
                }
        merged_fk[entity_name] = sorted(
            existing.values(),
            key=lambda item: (-float(item.get("confidence") or 0), str(item.get("column") or "")),
        )

    return {
        **proposals,
        "primary_keys": merged_pk,
        "foreign_keys": merged_fk,
        "conflicts": conflicts,
        "reference_consensus": {
            "build_count": consensus.get("build_count"),
            "updated_at": consensus.get("updated_at"),
        },
    }


def apply_reference_tags_to_attributes(
    attributes: list[dict[str, Any]],
    consensus: dict[str, Any] | None,
) -> int:
    """Pre-fill column tags from approved-build consensus before LLM tagging."""
    if not consensus:
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
        ref = reference_column_tag(consensus, entity, column)
        if not ref:
            continue
        weight = float(ref.get("weight") or 0.0)
        if weight < _MIN_CONSENSUS_RATIO:
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
