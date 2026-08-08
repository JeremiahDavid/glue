"""Profile-driven primary and foreign key inference with documentation merge."""

from __future__ import annotations

import re
from typing import Any

from meshflow.dna.field_semantics import discover_silver_columns, preview_silver_entity
from meshflow.dna.semantic_profiling import profile_entity_columns
from meshflow.dna.settings import DnaSettings

_FK_SUFFIX_RE = re.compile(r"(id|no|number|code)$", re.IGNORECASE)
_MEASURE_NAME_RE = re.compile(
    r"(amount|quantity|price|cost|rate|total|balance|count|percent|qty|weight|volume)",
    re.IGNORECASE,
)
_DATE_NAME_RE = re.compile(r"(date|time|timestamp|at$)", re.IGNORECASE)

# Column name (lower) -> silver entity for FK target lookup.
_FK_COLUMN_TARGETS: dict[str, str] = {
    "customerid": "customers",
    "customernumber": "customers",
    "customerno": "customers",
    "vendorid": "vendors",
    "vendornumber": "vendors",
    "itemid": "items",
    "itemnumber": "items",
    "employeeid": "employees",
    "accountid": "accounts",
    "locationid": "locations",
    "currencyid": "currencies",
    "documentid": "",
    "contactid": "contacts",
    "dimensionid": "dimensions",
    "dimensionvalueid": "dimension_values",
}

_MIN_PK_DISTINCT_RATIO = 0.92
_MIN_FK_OVERLAP_RATIO = 0.75
_STRONG_FK_OVERLAP_RATIO = 0.95


def _distinct_ratio(profile: dict[str, Any]) -> float:
    non_null = int(profile.get("non_null_count") or 0)
    if non_null <= 0:
        return 0.0
    return float(profile.get("distinct_count") or 0) / non_null


def _pk_name_score(column: str) -> float:
    name = column.strip()
    lowered = name.lower()
    if lowered == "id":
        return 1.0
    if lowered in {"key", "code", "number", "no"}:
        return 0.75
    if lowered.endswith("_id") or lowered.endswith("_key") or lowered.endswith("_code"):
        return 0.35
    if name.endswith("Id") and lowered != "id":
        return -0.4
    if _MEASURE_NAME_RE.search(name) or _DATE_NAME_RE.search(name):
        return -0.5
    return 0.1


def score_primary_key_candidate(column: str, profile: dict[str, Any]) -> float:
    """Higher score = stronger PK candidate (profile + column name)."""
    ratio = _distinct_ratio(profile)
    if ratio < _MIN_PK_DISTINCT_RATIO:
        return 0.0
    null_rate = float(profile.get("null_rate") or 0)
    if null_rate > 0.05:
        return 0.0
    score = ratio * 0.7 + _pk_name_score(column) * 0.3
    dtype = str(profile.get("inferred_dtype") or "")
    if dtype in {"string", "number"}:
        score += 0.05
    return round(min(score, 1.0), 4)


def _fk_name_target(column: str, *, from_entity: str) -> str | None:
    lowered = column.strip().lower()
    direct = _FK_COLUMN_TARGETS.get(lowered)
    if direct is not None:
        return direct or None
    if not _FK_SUFFIX_RE.search(lowered):
        return None
    stem = re.sub(r"(id|no|number|code)$", "", lowered, flags=re.IGNORECASE).strip()
    if not stem:
        return None
    if stem.endswith("s"):
        return stem
    return f"{stem}s"


def _column_values(settings: DnaSettings, entity: str, column: str, *, rows: list[dict[str, Any]] | None = None) -> set[str]:
    sample = rows if rows is not None else preview_silver_entity(settings, entity.strip().lower(), limit=500)
    values: set[str] = set()
    for row in sample:
        if not isinstance(row, dict) or column not in row:
            continue
        value = row.get(column)
        if value is None or str(value).strip() == "":
            continue
        values.add(str(value).strip())
    return values


def value_overlap_ratio(
    settings: DnaSettings,
    *,
    from_entity: str,
    from_column: str,
    to_entity: str,
    to_column: str,
    from_rows: list[dict[str, Any]] | None = None,
    to_rows: list[dict[str, Any]] | None = None,
) -> float:
    """Share of non-null FK values that exist in the target PK column."""
    fk_values = _column_values(settings, from_entity, from_column, rows=from_rows)
    if not fk_values:
        return 0.0
    pk_values = _column_values(settings, to_entity, to_column, rows=to_rows)
    if not pk_values:
        return 0.0
    matched = fk_values & pk_values
    return round(len(matched) / len(fk_values), 4)


def score_foreign_key_candidate(
    settings: DnaSettings,
    *,
    entity: str,
    column: str,
    profile: dict[str, Any],
    pk_by_entity: dict[str, str],
    entity_rows: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Return ranked FK targets for a column (name hint + cardinality overlap)."""
    name_target = _fk_name_target(column, from_entity=entity)
    candidates: list[dict[str, Any]] = []
    from_rows = entity_rows.get(entity.strip().lower())
    null_rate = float(profile.get("null_rate") or 0)
    if null_rate > 0.98:
        return []

    targets: set[str] = set()
    if name_target:
        targets.add(name_target)
    for target_entity, pk_column in pk_by_entity.items():
        if target_entity == entity.strip().lower():
            continue
        targets.add(target_entity)

    for target_entity in sorted(targets):
        pk_column = pk_by_entity.get(target_entity)
        if not pk_column:
            continue
        overlap = value_overlap_ratio(
            settings,
            from_entity=entity,
            from_column=column,
            to_entity=target_entity,
            to_column=pk_column,
            from_rows=from_rows,
            to_rows=entity_rows.get(target_entity),
        )
        if overlap < _MIN_FK_OVERLAP_RATIO and name_target != target_entity:
            continue
        name_bonus = 0.15 if name_target == target_entity else 0.0
        confidence = round(min(overlap * 0.85 + name_bonus, 1.0), 4)
        if overlap >= _STRONG_FK_OVERLAP_RATIO:
            confidence = max(confidence, 0.9)
        candidates.append(
            {
                "to_entity": target_entity,
                "to_column": pk_column,
                "overlap_ratio": overlap,
                "confidence": confidence,
                "name_hint": name_target == target_entity,
            }
        )
    candidates.sort(key=lambda item: (-float(item["confidence"]), -float(item["overlap_ratio"])))
    return candidates


def infer_primary_keys_for_entity(
    settings: DnaSettings,
    entity: str,
    *,
    profiles: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Rank PK candidates for one silver entity from profiling."""
    entity_name = entity.strip().lower()
    column_profiles = profiles or profile_entity_columns(settings, entity_name)
    ranked: list[dict[str, Any]] = []
    for column, profile in column_profiles.items():
        score = score_primary_key_candidate(column, profile)
        if score <= 0:
            continue
        ranked.append(
            {
                "column": column,
                "score": score,
                "distinct_ratio": round(_distinct_ratio(profile), 4),
                "null_rate": profile.get("null_rate"),
                "citation": "profile:primary_key",
            }
        )
    ranked.sort(
        key=lambda item: (
            -float(item["score"]),
            0 if str(item["column"]).strip().lower() == "id" else 1,
            str(item["column"]),
        )
    )
    return ranked


def infer_foreign_keys_for_entity(
    settings: DnaSettings,
    entity: str,
    *,
    pk_by_entity: dict[str, str],
    profiles: dict[str, dict[str, Any]] | None = None,
    entity_rows: dict[str, list[dict[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    """Rank FK candidates for one silver entity."""
    entity_name = entity.strip().lower()
    column_profiles = profiles or profile_entity_columns(settings, entity_name)
    rows_cache = entity_rows or {}
    if entity_name not in rows_cache:
        rows_cache = dict(rows_cache)
        rows_cache[entity_name] = preview_silver_entity(settings, entity_name, limit=500)

    results: list[dict[str, Any]] = []
    for column, profile in column_profiles.items():
        pk_rank = score_primary_key_candidate(column, profile)
        if pk_rank >= 0.98:
            continue
        targets = score_foreign_key_candidate(
            settings,
            entity=entity_name,
            column=column,
            profile=profile,
            pk_by_entity=pk_by_entity,
            entity_rows=rows_cache,
        )
        if not targets:
            continue
        best = targets[0]
        results.append(
            {
                "column": column,
                "to_entity": best["to_entity"],
                "to_column": best["to_column"],
                "overlap_ratio": best["overlap_ratio"],
                "confidence": best["confidence"],
                "citation": "profile:foreign_key",
            }
        )
    results.sort(key=lambda item: (-float(item["confidence"]), str(item["column"])))
    return results


def _hint_pk_by_entity(hints: dict[str, Any]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for item in hints.get("entities") or []:
        if not isinstance(item, dict):
            continue
        silver = str(item.get("silver_entity") or "").strip().lower()
        pk = str(item.get("primary_key") or "").strip()
        if silver and pk:
            mapping[silver] = pk
    return mapping


def _hint_fk_columns(hints: dict[str, Any]) -> dict[str, list[str]]:
    """Map silver_entity -> columns hinted as foreign_key in column_hints (by column name)."""
    column_hints = hints.get("column_hints") if isinstance(hints.get("column_hints"), dict) else {}
    fk_names = {
        name
        for name, hint in column_hints.items()
        if isinstance(hint, dict) and str(hint.get("role") or "").strip().lower() == "foreign_key"
    }
    return {"*": sorted(fk_names)}


def _documentation_fk_for_entity(entity: str, column: str, hints: dict[str, Any]) -> bool:
    column_hints = hints.get("column_hints") if isinstance(hints.get("column_hints"), dict) else {}
    hint = column_hints.get(column)
    if isinstance(hint, dict) and str(hint.get("role") or "").strip().lower() == "foreign_key":
        return True
    generic = column_hints.get("Id")
    if column.endswith("Id") and isinstance(generic, dict):
        return str(generic.get("role") or "").strip().lower() == "foreign_key"
    return False


def propose_keys_from_profiling(
    settings: DnaSettings,
    silver_entities: list[str],
    hints: dict[str, Any],
) -> dict[str, Any]:
    """Build PK/FK proposals from silver profiling, then merge documentation hints."""
    entities_sorted = sorted({name.strip().lower() for name in silver_entities if name.strip()})
    entity_rows: dict[str, list[dict[str, Any]]] = {
        name: preview_silver_entity(settings, name, limit=500) for name in entities_sorted
    }
    profiles_by_entity = {
        name: profile_entity_columns(settings, name) for name in entities_sorted
    }

    pk_ranked: dict[str, list[dict[str, Any]]] = {
        name: infer_primary_keys_for_entity(settings, name, profiles=profiles_by_entity[name])
        for name in entities_sorted
    }
    profile_pk: dict[str, str] = {}
    for name, ranked in pk_ranked.items():
        if ranked:
            profile_pk[name] = str(ranked[0]["column"])

    fk_ranked: dict[str, list[dict[str, Any]]] = {
        name: infer_foreign_keys_for_entity(
            settings,
            name,
            pk_by_entity=profile_pk,
            profiles=profiles_by_entity[name],
            entity_rows=entity_rows,
        )
        for name in entities_sorted
    }

    doc_pk = _hint_pk_by_entity(hints)
    conflicts: list[dict[str, Any]] = []
    merged_pk: dict[str, dict[str, Any]] = {}

    for entity_name in entities_sorted:
        profile_choice = profile_pk.get(entity_name)
        doc_choice = doc_pk.get(entity_name)
        chosen = profile_choice or doc_choice or "id"
        citation = "profile:primary_key"
        if doc_choice and profile_choice and doc_choice != profile_choice:
            conflicts.append(
                {
                    "id": f"conflict_pk_{entity_name}",
                    "entity": entity_name,
                    "column": profile_choice,
                    "kind": "primary_key",
                    "profile_value": profile_choice,
                    "documentation_value": doc_choice,
                    "text": (
                        f"Primary key for {entity_name}: profiling suggests "
                        f"{profile_choice!r} but documentation specifies {doc_choice!r}."
                    ),
                }
            )
            chosen = profile_choice
        elif doc_choice and not profile_choice:
            chosen = doc_choice
            citation = f"connector_knowledge/{settings.source.strip().lower()}/hints.yaml"

        merged_pk[entity_name] = {
            "column": chosen,
            "status": "proposed",
            "citation": citation,
            "profile_candidates": pk_ranked.get(entity_name) or [],
        }

    merged_fk: dict[str, list[dict[str, Any]]] = {name: [] for name in entities_sorted}
    profile_fk_columns = {name: {item["column"] for item in items} for name, items in fk_ranked.items()}

    for entity_name in entities_sorted:
        seen_columns: set[str] = set()
        for item in fk_ranked.get(entity_name) or []:
            column = str(item["column"])
            seen_columns.add(column)
            doc_says_fk = _documentation_fk_for_entity(entity_name, column, hints)
            citation = str(item.get("citation") or "profile:foreign_key")
            if doc_says_fk:
                citation = f"profile+docs:foreign_key"
            merged_fk[entity_name].append(
                {
                    "column": column,
                    "to_entity": item["to_entity"],
                    "to_column": item["to_column"],
                    "overlap_ratio": item.get("overlap_ratio"),
                    "confidence": item.get("confidence"),
                    "status": "proposed",
                    "citation": citation,
                }
            )

        columns = discover_silver_columns(settings, entity_name)
        for column in columns:
            if column in seen_columns:
                continue
            if not _documentation_fk_for_entity(entity_name, column, hints):
                continue
            targets = score_foreign_key_candidate(
                settings,
                entity=entity_name,
                column=column,
                profile=profiles_by_entity[entity_name].get(column)
                or profile_entity_columns(settings, entity_name, columns=[column]).get(column, {}),
                pk_by_entity={name: merged_pk[name]["column"] for name in merged_pk},
                entity_rows=entity_rows,
            )
            if not targets:
                conflicts.append(
                    {
                        "id": f"conflict_fk_{entity_name}_{column.lower()}",
                        "entity": entity_name,
                        "column": column,
                        "kind": "foreign_key",
                        "profile_value": None,
                        "documentation_value": "foreign_key",
                        "text": (
                            f"Documentation marks {entity_name}.{column} as a foreign key, "
                            "but profiling could not confirm cardinality against any primary key."
                        ),
                    }
                )
                continue
            best = targets[0]
            merged_fk[entity_name].append(
                {
                    "column": column,
                    "to_entity": best["to_entity"],
                    "to_column": best["to_column"],
                    "overlap_ratio": best["overlap_ratio"],
                    "confidence": best["confidence"],
                    "status": "proposed",
                    "citation": f"connector_knowledge/{settings.source.strip().lower()}/hints.yaml",
                }
            )

        for column in sorted(profile_fk_columns.get(entity_name, set())):
            if _documentation_fk_for_entity(entity_name, column, hints):
                continue

    proposals = {
        "primary_keys": merged_pk,
        "foreign_keys": merged_fk,
        "conflicts": conflicts,
        "profile_pk": profile_pk,
        "profile_fk_ranked": fk_ranked,
    }
    from meshflow.dna.semantic_source_reference import (
        apply_reference_consensus_to_key_proposals,
        load_source_semantic_consensus,
    )

    consensus = load_source_semantic_consensus(settings, settings.source.strip().lower())
    return apply_reference_consensus_to_key_proposals(
        proposals,
        consensus,
        source=settings.source.strip().lower(),
    )


def propose_relationships_from_approved_keys(
    settings: DnaSettings,
    *,
    entities: list[dict[str, Any]],
    attributes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build relationship proposals from approved PK/FK fields (profile-confirmed overlap)."""
    pk_by_entity: dict[str, tuple[str, str]] = {}
    for entity in entities:
        if not isinstance(entity, dict):
            continue
        silver = str(entity.get("silver_entity") or "").strip().lower()
        pk_status = str(entity.get("primary_key_status") or entity.get("status") or "").strip().lower()
        if pk_status != "approved":
            continue
        pk_column = str(entity.get("primary_key") or "id").strip()
        if silver and pk_column:
            pk_by_entity[silver] = (pk_column, str(entity.get("id") or silver))

    relationships: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()

    for attribute in attributes:
        if not isinstance(attribute, dict):
            continue
        if str(attribute.get("role") or "").strip().lower() != "foreign_key":
            continue
        if str(attribute.get("status") or "").strip().lower() != "approved":
            continue
        from_entity = str(attribute.get("entity") or "").strip().lower()
        from_column = str(attribute.get("column") or "").strip()
        if not from_entity or not from_column:
            continue

        target_entity = str(attribute.get("fk_target_entity") or "").strip().lower()
        target_column = str(attribute.get("fk_target_column") or "").strip()
        if not target_entity or not target_column:
            best_overlap = 0.0
            best_target = ("", "")
            for silver, (pk_col, _ent_id) in pk_by_entity.items():
                if silver == from_entity:
                    continue
                overlap = value_overlap_ratio(
                    settings,
                    from_entity=from_entity,
                    from_column=from_column,
                    to_entity=silver,
                    to_column=pk_col,
                )
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_target = (silver, pk_col)
            target_entity, target_column = best_target

        if not target_entity or not target_column:
            continue
        if target_entity not in pk_by_entity:
            continue

        key = (from_entity, from_column, target_entity, target_column)
        if key in seen:
            continue
        seen.add(key)

        overlap = value_overlap_ratio(
            settings,
            from_entity=from_entity,
            from_column=from_column,
            to_entity=target_entity,
            to_column=target_column,
        )
        rel_id = f"rel_{from_entity}_{from_column.lower()}_{target_entity}"
        relationships.append(
            {
                "id": rel_id,
                "from_entity": from_entity,
                "from_column": from_column,
                "to_entity": target_entity,
                "to_column": target_column,
                "cardinality": "many_to_one",
                "status": "proposed",
                "confidence": round(min(overlap, 1.0), 4) if overlap else 0.7,
                "description": f"{from_entity}.{from_column} → {target_entity}.{target_column}",
                "citation": "profile:approved_keys",
            }
        )

    return relationships
