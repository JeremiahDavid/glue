"""Reconcile MS Learn gold source-docs with ETL silver schema profiles."""

from __future__ import annotations

import copy
from typing import Any

PROFILE_KIND = "silver_schema_profile"

ORIGIN_VALUES = frozenset(
    {"api", "unpack", "sql_pack", "key_derivation", "documentation_only"}
)


def _profile_provenance(profile: dict[str, Any]) -> dict[str, Any]:
    provenance: dict[str, Any] = {
        "generated_at": profile.get("generated_at"),
        "consolidated_at": profile.get("consolidated_at"),
    }
    version = str(profile.get("silver_sql_pack_version") or "").strip()
    if version:
        provenance["silver_sql_pack_version"] = version
    return provenance


def build_silver_column_index(profile: dict[str, Any]) -> dict[str, Any]:
    """Index profile tables by silver_entity with column sets and name lookups."""
    tables_index: dict[str, dict[str, Any]] = {}
    for table in profile.get("tables") or []:
        if not isinstance(table, dict):
            continue
        entity = str(table.get("silver_entity") or "").strip().lower()
        if not entity:
            continue
        column_meta: dict[str, dict[str, str]] = {}
        column_set: set[str] = set()
        for col in table.get("columns") or []:
            if not isinstance(col, dict):
                continue
            name = str(col.get("name") or "").strip()
            if not name:
                continue
            column_set.add(name)
            column_meta[name] = {
                "name": name,
                "type": str(col.get("type") or "string"),
                "origin": str(col.get("origin") or "api"),
            }
        tables_index[entity] = {
            "glue_table": str(table.get("glue_table") or ""),
            "column_set": column_set,
            "column_meta": column_meta,
        }
    return tables_index


def _resolve_silver_column(
    entity: str,
    doc_name: str,
    tables_index: dict[str, dict[str, Any]],
) -> tuple[str, bool, str]:
    """Return (silver_column, in_silver, origin)."""
    name = str(doc_name or "").strip()
    if not name:
        return "", False, "documentation_only"
    table = tables_index.get(entity.strip().lower())
    if not table:
        return name, False, "documentation_only"
    column_set = table["column_set"]
    if name in column_set:
        meta = table["column_meta"].get(name) or {}
        return name, True, str(meta.get("origin") or "api")
    lowered = {col.lower(): col for col in column_set}
    match = lowered.get(name.lower())
    if match:
        meta = table["column_meta"].get(match) or {}
        return match, True, str(meta.get("origin") or "api")
    return name, False, "documentation_only"


def _attach_profile_provenance(gold: dict[str, Any], profile: dict[str, Any]) -> None:
    merged_from = gold.get("merged_from")
    if not isinstance(merged_from, dict):
        merged_from = {}
        gold["merged_from"] = merged_from
    merged_from["silver_profile"] = _profile_provenance(profile)


def reconcile_entity_properties(
    gold: dict[str, Any],
    profile: dict[str, Any],
) -> dict[str, Any]:
    out = copy.deepcopy(gold)
    tables_index = build_silver_column_index(profile)
    tables = out.get("tables") or []
    if not isinstance(tables, list):
        return out

    for table in tables:
        if not isinstance(table, dict):
            continue
        entity = str(table.get("silver_entity") or "").strip().lower()
        if not entity:
            continue
        table["in_silver"] = entity in tables_index
        seen_doc_names: set[str] = set()
        properties = table.get("properties") or []
        enriched: list[dict[str, Any]] = []
        for prop in properties:
            if not isinstance(prop, dict):
                continue
            doc_name = str(prop.get("name") or "").strip()
            if not doc_name:
                continue
            seen_doc_names.add(doc_name)
            silver_column, in_silver, origin = _resolve_silver_column(entity, doc_name, tables_index)
            item = dict(prop)
            item["silver_column"] = silver_column
            item["in_silver"] = in_silver
            item["origin"] = origin
            enriched.append(item)

        profile_table = tables_index.get(entity)
        if profile_table:
            for col_name, meta in profile_table["column_meta"].items():
                if col_name in seen_doc_names:
                    continue
                enriched.append(
                    {
                        "name": col_name,
                        "silver_column": col_name,
                        "in_silver": True,
                        "origin": str(meta.get("origin") or "api"),
                        "description": "Silver ETL column not in MS Learn catalog.",
                    }
                )
        table["properties"] = enriched
        table["property_count"] = len(enriched)

    out["table_count"] = len([t for t in tables if isinstance(t, dict)])
    _attach_profile_provenance(out, profile)
    return out


def reconcile_entity_relationships(
    gold: dict[str, Any],
    profile: dict[str, Any],
    properties_index: dict[str, dict[str, str]] | None = None,
) -> dict[str, Any]:
    out = copy.deepcopy(gold)
    tables_index = build_silver_column_index(profile)
    props_index = properties_index or {}

    tables = out.get("tables") or {}
    if not isinstance(tables, dict):
        return out

    for entity_key, table in tables.items():
        if not isinstance(table, dict):
            continue
        entity = str(entity_key or "").strip().lower()
        table["in_silver"] = entity in tables_index

        pk_name = str(table.get("PK") or "id").strip()
        silver_pk, pk_in_silver, _ = _resolve_silver_column(entity, pk_name, tables_index)
        if props_index.get(entity, {}).get(pk_name):
            silver_pk = props_index[entity][pk_name]
            pk_in_silver = silver_pk in (tables_index.get(entity, {}).get("column_set") or set())
        table["silver_PK"] = silver_pk
        table["pk_in_silver"] = pk_in_silver

        relationships = table.get("relationships") or []
        for rel in relationships:
            if not isinstance(rel, dict):
                continue
            target = str(rel.get("target") or "").strip().lower()
            fk_name = str(rel.get("FK") or "").strip()
            target_pk_name = str(rel.get("PK") or pk_name).strip()

            silver_fk, fk_in_silver, _ = _resolve_silver_column(entity, fk_name, tables_index)
            if props_index.get(entity, {}).get(fk_name):
                silver_fk = props_index[entity][fk_name]
                fk_in_silver = silver_fk in (tables_index.get(entity, {}).get("column_set") or set())

            silver_target_pk, target_pk_in_silver, _ = _resolve_silver_column(
                target, target_pk_name, tables_index
            )
            if props_index.get(target, {}).get(target_pk_name):
                silver_target_pk = props_index[target][target_pk_name]
                target_pk_in_silver = silver_target_pk in (
                    tables_index.get(target, {}).get("column_set") or set()
                )

            rel["silver_FK"] = silver_fk
            rel["fk_in_silver"] = fk_in_silver
            rel["silver_PK"] = silver_target_pk
            rel["pk_in_silver"] = target_pk_in_silver
            rel["target_in_silver"] = target in tables_index

    _attach_profile_provenance(out, profile)
    return out


def reconcile_entity_property_tags(
    gold: dict[str, Any],
    profile: dict[str, Any],
    properties_index: dict[str, dict[str, str]] | None = None,
) -> dict[str, Any]:
    out = copy.deepcopy(gold)
    tables_index = build_silver_column_index(profile)
    props_index = properties_index or {}
    tables = out.get("tables") or []
    if not isinstance(tables, list):
        return out

    tagged_count = 0
    for table in tables:
        if not isinstance(table, dict):
            continue
        entity = str(table.get("silver_entity") or "").strip().lower()
        if not entity:
            continue
        table["in_silver"] = entity in tables_index
        seen_doc_names: set[str] = set()
        properties = table.get("properties") or []
        enriched: list[dict[str, Any]] = []
        table_tagged = 0
        for prop in properties:
            if not isinstance(prop, dict):
                continue
            doc_name = str(prop.get("name") or "").strip()
            if not doc_name:
                continue
            seen_doc_names.add(doc_name)
            silver_column, in_silver, origin = _resolve_silver_column(entity, doc_name, tables_index)
            if props_index.get(entity, {}).get(doc_name):
                silver_column = props_index[entity][doc_name]
                in_silver = silver_column in (tables_index.get(entity, {}).get("column_set") or set())
            item = dict(prop)
            item["silver_column"] = silver_column
            item["in_silver"] = in_silver
            item["origin"] = origin if in_silver else "documentation_only"
            if item.get("tags"):
                table_tagged += 1
            enriched.append(item)

        profile_table = tables_index.get(entity)
        if profile_table:
            for col_name, meta in profile_table["column_meta"].items():
                if col_name in seen_doc_names:
                    continue
                enriched.append(
                    {
                        "name": col_name,
                        "silver_column": col_name,
                        "in_silver": True,
                        "origin": str(meta.get("origin") or "api"),
                        "tags": ["etl_column"],
                    }
                )
                table_tagged += 1

        table["properties"] = enriched
        table["property_count"] = len(enriched)
        table["tagged_property_count"] = table_tagged
        tagged_count += table_tagged

    out["table_count"] = len([t for t in tables if isinstance(t, dict)])
    out["tagged_property_count"] = tagged_count
    _attach_profile_provenance(out, profile)
    return out


def build_properties_silver_index(properties_gold: dict[str, Any]) -> dict[str, dict[str, str]]:
    """doc property name -> silver_column from reconciled entity_properties."""
    index: dict[str, dict[str, str]] = {}
    for table in properties_gold.get("tables") or []:
        if not isinstance(table, dict):
            continue
        entity = str(table.get("silver_entity") or "").strip().lower()
        if not entity:
            continue
        entity_map: dict[str, str] = {}
        for prop in table.get("properties") or []:
            if not isinstance(prop, dict):
                continue
            doc_name = str(prop.get("name") or "").strip()
            if not doc_name:
                continue
            silver_column = str(prop.get("silver_column") or doc_name).strip() or doc_name
            entity_map[doc_name] = silver_column
        if entity_map:
            index[entity] = entity_map
    return index


def reconcile_gold_artifacts(
    artifacts: dict[str, dict[str, Any]],
    profile: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    if str(profile.get("kind") or "") != PROFILE_KIND:
        raise ValueError(f"Expected profile kind {PROFILE_KIND}")

    properties = artifacts.get("entity_properties")
    if not isinstance(properties, dict):
        raise ValueError("entity_properties artifact is required for reconcile")

    reconciled_properties = reconcile_entity_properties(properties, profile)
    props_index = build_properties_silver_index(reconciled_properties)

    reconciled: dict[str, dict[str, Any]] = {
        "entity_properties": reconciled_properties,
    }
    relationships = artifacts.get("entity_relationships")
    if isinstance(relationships, dict):
        reconciled["entity_relationships"] = reconcile_entity_relationships(
            relationships,
            profile,
            properties_index=props_index,
        )
    tags = artifacts.get("entity_property_tags")
    if isinstance(tags, dict):
        reconciled["entity_property_tags"] = reconcile_entity_property_tags(
            tags,
            profile,
            properties_index=props_index,
        )
    return reconciled
