"""Merge global BC source-docs YAML with client exclude/addition overlays.

Produces gold catalogs with the same schema as the global source files.
"""

from __future__ import annotations

import copy
from datetime import UTC, datetime
from typing import Any

from meshflow.bc.source_docs_schema import ArtifactName, validate_source_docs_payload


def _utcnow() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _entity_index(entities: list[Any]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for item in entities:
        if not isinstance(item, dict):
            continue
        name = str(item.get("silver_entity") or "").strip()
        if name:
            index[name] = item
    return index


def _property_names(entity: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for prop in entity.get("properties") or []:
        if isinstance(prop, dict):
            name = str(prop.get("name") or "").strip()
            if name:
                names.add(name)
    return names


def merge_entity_list_catalog(
    global_catalog: dict[str, Any],
    overlay: dict[str, Any] | None,
    *,
    kind: str,
    property_key: str = "properties",
) -> dict[str, Any]:
    """Merge entity_properties / entity_property_tags style catalogs."""
    base = copy.deepcopy(global_catalog) if isinstance(global_catalog, dict) else {}
    raw_tables = base.get("tables")
    if raw_tables is None:
        raw_tables = base.get("entities")
    tables = [copy.deepcopy(e) for e in (raw_tables or []) if isinstance(e, dict)]
    by_name = _entity_index(tables)

    overlay = overlay if isinstance(overlay, dict) else {}
    exclude = overlay.get("exclude") if isinstance(overlay.get("exclude"), dict) else {}
    addition = overlay.get("addition") if isinstance(overlay.get("addition"), dict) else {}

    drop_tables = {
        str(name).strip()
        for name in (exclude.get("tables") or exclude.get("silver_entities") or [])
        if str(name).strip()
    }
    if drop_tables:
        tables = [e for e in tables if str(e.get("silver_entity") or "").strip() not in drop_tables]
        by_name = _entity_index(tables)

    for entry in exclude.get("properties") or []:
        if not isinstance(entry, dict):
            continue
        silver = str(entry.get("silver_entity") or "").strip()
        names = {str(n).strip() for n in (entry.get("names") or []) if str(n).strip()}
        entity = by_name.get(silver)
        if not entity or not names:
            continue
        entity[property_key] = [
            p
            for p in (entity.get(property_key) or [])
            if isinstance(p, dict) and str(p.get("name") or "").strip() not in names
        ]
        entity["property_count"] = len(entity.get(property_key) or [])

    # Per-tag excludes apply to tags catalogs (and are schema-validated only there).
    for entry in exclude.get("tags") or []:
        if not isinstance(entry, dict):
            continue
        silver = str(entry.get("silver_entity") or "").strip()
        prop_name = str(entry.get("name") or "").strip()
        drop_tags = {str(t).strip() for t in (entry.get("tags") or []) if str(t).strip()}
        entity = by_name.get(silver)
        if not entity or not prop_name or not drop_tags:
            continue
        kept_props: list[dict[str, Any]] = []
        for prop in entity.get(property_key) or []:
            if not isinstance(prop, dict):
                continue
            if str(prop.get("name") or "").strip() != prop_name:
                kept_props.append(prop)
                continue
            remaining = [
                str(t).strip()
                for t in (prop.get("tags") or [])
                if str(t).strip() and str(t).strip() not in drop_tags
            ]
            if not remaining:
                continue
            cloned = copy.deepcopy(prop)
            cloned["tags"] = remaining
            kept_props.append(cloned)
        entity[property_key] = kept_props
        entity["property_count"] = len(kept_props)

    for entity in addition.get("tables") or addition.get("entities") or []:
        if not isinstance(entity, dict):
            continue
        silver = str(entity.get("silver_entity") or "").strip()
        if not silver:
            continue
        cloned = copy.deepcopy(entity)
        props = [p for p in (cloned.get(property_key) or []) if isinstance(p, dict)]
        cloned[property_key] = props
        cloned["property_count"] = len(props)
        if silver in by_name:
            idx = next(
                i
                for i, item in enumerate(tables)
                if str(item.get("silver_entity") or "").strip() == silver
            )
            tables[idx] = cloned
            by_name[silver] = cloned
        else:
            tables.append(cloned)
            by_name[silver] = cloned

    for entry in addition.get("properties") or []:
        if not isinstance(entry, dict):
            continue
        silver = str(entry.get("silver_entity") or "").strip()
        entity = by_name.get(silver)
        if not entity:
            continue
        existing = {
            str(p.get("name") or "").strip()
            for p in (entity.get(property_key) or [])
            if isinstance(p, dict)
        }
        props = list(entity.get(property_key) or [])
        for prop in entry.get("properties") or []:
            if not isinstance(prop, dict):
                continue
            name = str(prop.get("name") or "").strip()
            if not name:
                continue
            if name in existing:
                props = [
                    copy.deepcopy(prop) if str(p.get("name") or "").strip() == name else p
                    for p in props
                    if isinstance(p, dict)
                ]
            else:
                props.append(copy.deepcopy(prop))
                existing.add(name)
        entity[property_key] = props
        entity["property_count"] = len(props)

    property_count = sum(len(e.get(property_key) or []) for e in tables)
    result = {
        **{
            k: v
            for k, v in base.items()
            if k
            not in {
                "entities",
                "tables",
                "entity_count",
                "table_count",
                "property_count",
                "tagged_property_count",
                "kind",
                "generated_at",
                "merged_from",
            }
        },
        "source": str(overlay.get("source") or base.get("source") or "dbc"),
        "kind": kind,
        "generated_at": _utcnow(),
        "table_count": len(tables),
        "property_count": property_count,
        "tables": tables,
    }
    if kind == "ms_learn_entity_property_tags":
        tagged = sum(
            1
            for e in tables
            for p in (e.get(property_key) or [])
            if isinstance(p, dict) and (p.get("tags") or [])
        )
        result["tagged_property_count"] = tagged
    return result


def merge_entity_relationships(
    global_catalog: dict[str, Any],
    overlay: dict[str, Any] | None,
) -> dict[str, Any]:
    """Merge entity_relationships style catalogs."""
    base = copy.deepcopy(global_catalog) if isinstance(global_catalog, dict) else {}
    tables: dict[str, Any] = {}
    for name, table in (base.get("tables") or {}).items():
        if isinstance(table, dict):
            tables[str(name)] = copy.deepcopy(table)

    overlay = overlay if isinstance(overlay, dict) else {}
    exclude = overlay.get("exclude") if isinstance(overlay.get("exclude"), dict) else {}
    addition = overlay.get("addition") if isinstance(overlay.get("addition"), dict) else {}

    for name in exclude.get("tables") or []:
        tables.pop(str(name).strip(), None)

    for entry in exclude.get("relationships") or []:
        if not isinstance(entry, dict):
            continue
        table_name = str(entry.get("table") or "").strip()
        table = tables.get(table_name)
        if not table:
            continue
        fk = str(entry.get("FK") or "").strip()
        target = str(entry.get("target") or "").strip()
        if not fk and not target:
            table["relationships"] = []
            continue
        kept: list[dict[str, Any]] = []
        for rel in table.get("relationships") or []:
            if not isinstance(rel, dict):
                continue
            rel_fk = str(rel.get("FK") or "").strip()
            rel_target = str(rel.get("target") or "").strip()
            matches = True
            if fk:
                matches = matches and rel_fk == fk
            if target:
                matches = matches and rel_target == target
            if not matches:
                kept.append(rel)
        table["relationships"] = kept

    for name, table in (addition.get("tables") or {}).items():
        if not isinstance(table, dict):
            continue
        tables[str(name)] = copy.deepcopy(table)

    for entry in addition.get("relationships") or []:
        if not isinstance(entry, dict):
            continue
        table_name = str(entry.get("table") or "").strip()
        if not table_name:
            continue
        table = tables.setdefault(table_name, {"PK": "", "relationships": []})
        rels = [r for r in (table.get("relationships") or []) if isinstance(r, dict)]
        new_rel = {
            "target": str(entry.get("target") or "").strip(),
            "PK": str(entry.get("PK") or "").strip(),
            "FK": str(entry.get("FK") or "").strip(),
        }
        if not new_rel["target"] or not new_rel["FK"]:
            continue
        replaced = False
        for idx, rel in enumerate(rels):
            if str(rel.get("FK") or "").strip() == new_rel["FK"]:
                rels[idx] = new_rel
                replaced = True
                break
        if not replaced:
            rels.append(new_rel)
        table["relationships"] = rels
        if not str(table.get("PK") or "").strip() and new_rel["PK"]:
            # Leave PK alone unless empty; additions should set PK via tables when needed.
            pass

    relationship_count = sum(
        len(t.get("relationships") or []) for t in tables.values() if isinstance(t, dict)
    )
    return {
        **{
            k: v
            for k, v in base.items()
            if k
            not in {
                "tables",
                "table_count",
                "relationship_count",
                "kind",
                "generated_at",
                "merged_from",
            }
        },
        "source": str(overlay.get("source") or base.get("source") or "dbc"),
        "kind": "ms_learn_entity_relationships",
        "generated_at": _utcnow(),
        "table_count": len(tables),
        "relationship_count": relationship_count,
        "tables": tables,
    }


def merge_source_docs_artifact(
    *,
    artifact: ArtifactName,
    global_catalog: dict[str, Any],
    overlay: dict[str, Any] | None,
    validate: bool = True,
) -> dict[str, Any]:
    """Validate inputs, merge, and validate gold output."""
    if validate:
        validate_source_docs_payload(global_catalog, artifact=artifact, variant="catalog")
        if overlay:
            validate_source_docs_payload(overlay, artifact=artifact, variant="overlay")

    if artifact == "entity_properties":
        gold = merge_entity_list_catalog(
            global_catalog,
            overlay,
            kind="ms_learn_entity_properties",
        )
    elif artifact == "entity_property_tags":
        gold = merge_entity_list_catalog(
            global_catalog,
            overlay,
            kind="ms_learn_entity_property_tags",
        )
    elif artifact == "entity_relationships":
        gold = merge_entity_relationships(global_catalog, overlay)
    else:
        raise ValueError(f"Unsupported artifact {artifact!r}")

    if validate:
        validate_source_docs_payload(gold, artifact=artifact, variant="catalog")
    return gold
