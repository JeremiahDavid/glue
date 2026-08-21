"""Compile approved semantic model sections into DNA pack entities, joins, and dimensions."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from meshflow.dna.field_semantics import load_operational_concept_catalog
from meshflow.dna.governance import load_governance_reporting_payload, save_governance_version
from meshflow.dna.reporting import load_production_reporting
from meshflow.dna.schema import load_definition_pack
from meshflow.dna.settings import DnaSettings
from meshflow.dna.workflow import load_production_pack, load_workflow_state, save_workflow_state


def _dna_join_id(relationship_id: str) -> str:
    rel_id = relationship_id.strip().lower()
    if rel_id.startswith("rel_"):
        return f"join_{rel_id[4:]}"
    if rel_id.startswith("join_"):
        return rel_id
    return f"join_{rel_id}"


def _concept_labels() -> dict[str, str]:
    catalog = load_operational_concept_catalog()
    labels: dict[str, str] = {}
    for item in catalog.get("concepts") or []:
        if isinstance(item, dict) and item.get("id"):
            labels[str(item["id"])] = str(item.get("label") or item["id"])
    return labels


def codegen_dna_sections(model: dict[str, Any]) -> dict[str, Any]:
    """Build DNA ``entities``, ``joins``, and ``dimensions`` from an approved semantic model."""
    entities_in = [
        item
        for item in model.get("entities") or []
        if isinstance(item, dict) and str(item.get("status") or "") == "approved"
    ]
    relationships_in = [
        item
        for item in model.get("relationships") or []
        if isinstance(item, dict) and str(item.get("status") or "") == "approved"
    ]
    attributes_in = [
        item
        for item in model.get("attributes") or []
        if isinstance(item, dict) and str(item.get("status") or "") in {"approved", "proposed"}
    ]

    silver_to_entity_id: dict[str, str] = {}
    entities: list[dict[str, Any]] = []
    for item in entities_in:
        entity_id = str(item.get("id") or "").strip()
        silver_entity = str(item.get("silver_entity") or "").strip().lower()
        if not entity_id or not silver_entity:
            continue
        silver_to_entity_id[silver_entity] = entity_id
        entry: dict[str, Any] = {
            "id": entity_id,
            "grain": str(item.get("grain") or "row"),
            "silver_entity": silver_entity,
            "primary_key": str(item.get("primary_key") or "id"),
        }
        description = str(item.get("description") or "").strip()
        if description:
            entry["description"] = description
        entities.append(entry)

    joins: list[dict[str, Any]] = []
    for rel in relationships_in:
        from_silver = str(rel.get("from_entity") or "").strip().lower()
        to_silver = str(rel.get("to_entity") or "").strip().lower()
        left_entity = silver_to_entity_id.get(from_silver)
        right_entity = silver_to_entity_id.get(to_silver)
        if not left_entity or not right_entity:
            continue
        rel_id = str(rel.get("id") or "").strip()
        entry: dict[str, Any] = {
            "id": _dna_join_id(rel_id),
            "left_entity": left_entity,
            "right_entity": right_entity,
            "left_key": str(rel.get("from_column") or "").strip(),
            "right_key": str(rel.get("to_column") or "").strip(),
            "cardinality": str(rel.get("cardinality") or "many_to_one"),
        }
        description = str(rel.get("description") or "").strip()
        if description:
            entry["description"] = description
        joins.append(entry)

    entity_roles = {
        str(item.get("silver_entity") or "").strip().lower(): str(item.get("role") or "")
        for item in entities_in
    }
    entity_ids = {
        str(item.get("silver_entity") or "").strip().lower(): str(item.get("id") or "")
        for item in entities_in
    }
    labels = _concept_labels()
    dimensions: list[dict[str, Any]] = []
    seen_dim: set[str] = set()
    for attr in attributes_in:
        silver_entity = str(attr.get("entity") or "").strip().lower()
        column = str(attr.get("column") or "").strip()
        concepts = [str(c) for c in attr.get("concepts") or [] if str(c).strip()]
        if not silver_entity or not column or not concepts:
            continue
        role = entity_roles.get(silver_entity, "")
        if role not in {"dimension", "reference"}:
            continue
        entity_id = entity_ids.get(silver_entity)
        if not entity_id:
            continue
        concept_id = concepts[0]
        dim_id = f"dim_{concept_id}"
        if dim_id in seen_dim:
            dim_id = f"dim_{silver_entity}_{column}"
        if dim_id in seen_dim:
            continue
        seen_dim.add(dim_id)
        dimensions.append(
            {
                "id": dim_id,
                "entity_id": entity_id,
                "column": column,
                "display_name": labels.get(concept_id, concept_id.replace("_", " ").title()),
            }
        )

    return {
        "entities": entities,
        "joins": joins,
        "dimensions": dimensions,
    }


def _bump_patch_version(version: str) -> str:
    parts = str(version or "1.0.0").strip().split(".")
    if len(parts) != 3:
        return "1.0.1"
    try:
        major, minor, patch = (int(parts[0]), int(parts[1]), int(parts[2]))
    except ValueError:
        return "1.0.1"
    return f"{major}.{minor}.{patch + 1}"


def apply_semantic_model_to_dna_pack(
    settings: DnaSettings,
    model: dict[str, Any],
    *,
    username: str,
    notes: str = "",
) -> dict[str, Any]:
    """Merge semantic model entities/joins/dimensions into the pinned DNA pack (new patch version)."""
    sections = codegen_dna_sections(model)
    if not sections["entities"]:
        raise ValueError("Semantic model has no approved entities to sync into DNA")

    pack = load_production_pack(settings)
    payload = pack.to_dict()
    payload["entities"] = sections["entities"]
    payload["joins"] = sections["joins"]
    payload["dimensions"] = sections["dimensions"]

    new_version = _bump_patch_version(pack.version)
    payload["version"] = new_version
    changelog = list(payload.get("changelog") or [])
    changelog.append(
        {
            "version": new_version,
            "date": datetime.now(UTC).date().isoformat(),
            "summary": notes or "Synced entities, joins, and dimensions from published semantic model",
            "author": username,
        }
    )
    payload["changelog"] = changelog

    updated_pack = load_definition_pack(payload)
    pack_id = settings.dna_config_id
    state = load_workflow_state(settings, pack_id)
    version = str(state.get("active_version") or pack.version)
    reporting = load_governance_reporting_payload(settings, pack_id, version)
    if reporting is None:
        reporting = load_production_reporting(settings)

    saved = save_governance_version(settings, pack=updated_pack, reporting=reporting)
    state["active_version"] = new_version
    history = state.get("history")
    if not isinstance(history, list):
        history = []
    history.append(
        {
            "version": new_version,
            "status": updated_pack.status,
            "approver": username,
            "at": datetime.now(UTC).isoformat(),
            "notes": notes or "Semantic model → DNA sync",
        }
    )
    state["history"] = history
    workflow_path = save_workflow_state(settings, state)

    return {
        "status": "synced",
        "dna_version": new_version,
        "entity_count": len(sections["entities"]),
        "join_count": len(sections["joins"]),
        "dimension_count": len(sections["dimensions"]),
        "dna_path": saved["dna_path"],
        "workflow_path": workflow_path,
    }
