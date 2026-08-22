"""Client source-docs overlay mutate, pending diff, and version snapshots.

Portal edits write exclude entries onto live overlay YAMLs. Submit runs gold
merge, then commits overlays+gold into versions/vN. Restore rewrites both.
"""

from __future__ import annotations

import copy
from datetime import datetime
from meshflow.compat import UTC
from typing import Any, Literal

from meshflow.dna.settings import DnaSettings
from meshflow.dna.source_docs.reference import (
    GOLD_ARTIFACTS,
    normalize_reference_source,
    source_docs_gold_key,
)
from meshflow.dna.store import read_yaml_artifact, write_yaml_artifact
from meshflow.storage.paths import (
    governance_source_docs_overlay_key,
    governance_source_docs_version_gold_key,
    governance_source_docs_version_overlay_key,
    governance_source_docs_versions_manifest_key,
)

ExcludeKind = Literal["table", "relationship", "tag"]

_FILENAMES: dict[str, str] = {
    "entity_properties": "entity_properties.yaml",
    "entity_relationships": "entity_relationships.yaml",
    "entity_property_tags": "entity_property_tags.yaml",
}

_OVERLAY_KINDS: dict[str, str] = {
    "entity_properties": "ms_learn_entity_properties_overlay",
    "entity_relationships": "ms_learn_entity_relationships_overlay",
    "entity_property_tags": "ms_learn_entity_property_tags_overlay",
}


def _utcnow() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def empty_overlay(source: str, artifact: str) -> dict[str, Any]:
    kind = _OVERLAY_KINDS.get(artifact)
    if not kind:
        raise ValueError(f"Unknown overlay artifact {artifact!r}")
    return {
        "source": source,
        "kind": kind,
        "description": (
            f"Client overlay for {artifact}. Use exclude: and addition: to customize "
            "the global catalog before gold merge."
        ),
        "exclude": {},
        "addition": {},
    }


def source_docs_overlay_key(
    settings: DnaSettings, artifact: str, *, source: str | None = None
) -> str:
    name = _FILENAMES.get(artifact)
    if not name:
        raise ValueError(f"Unknown overlay artifact {artifact!r}")
    connector = normalize_reference_source(source or settings.source)
    return governance_source_docs_overlay_key(connector, name)


def load_overlay(
    settings: DnaSettings, artifact: str, *, source: str | None = None
) -> dict[str, Any] | None:
    return read_yaml_artifact(
        settings, source_docs_overlay_key(settings, artifact, source=source)
    )


def ensure_overlay(
    settings: DnaSettings, artifact: str, *, source: str | None = None
) -> dict[str, Any]:
    connector = normalize_reference_source(source or settings.source)
    existing = load_overlay(settings, artifact, source=connector)
    if isinstance(existing, dict) and existing:
        if not isinstance(existing.get("exclude"), dict):
            existing["exclude"] = {}
        if not isinstance(existing.get("addition"), dict):
            existing["addition"] = {}
        return existing
    payload = empty_overlay(connector, artifact)
    write_yaml_artifact(
        settings, source_docs_overlay_key(settings, artifact, source=connector), payload
    )
    return payload


def save_overlay(
    settings: DnaSettings,
    artifact: str,
    payload: dict[str, Any],
    *,
    source: str | None = None,
) -> str:
    connector = normalize_reference_source(source or settings.source)
    key = source_docs_overlay_key(settings, artifact, source=connector)
    write_yaml_artifact(settings, key, payload)
    return key


def _ensure_list(container: dict[str, Any], key: str) -> list[Any]:
    value = container.get(key)
    if not isinstance(value, list):
        value = []
        container[key] = value
    return value


def _add_table_exclude(overlay: dict[str, Any], table: str) -> bool:
    exclude = overlay.setdefault("exclude", {})
    if not isinstance(exclude, dict):
        exclude = {}
        overlay["exclude"] = exclude
    tables = _ensure_list(exclude, "tables")
    if table in {str(t).strip() for t in tables}:
        return False
    tables.append(table)
    return True


def _remove_table_exclude(overlay: dict[str, Any], table: str) -> bool:
    exclude = overlay.get("exclude")
    if not isinstance(exclude, dict):
        return False
    tables = exclude.get("tables")
    if not isinstance(tables, list):
        return False
    before = len(tables)
    exclude["tables"] = [t for t in tables if str(t).strip() != table]
    return len(exclude["tables"]) != before


def _rel_signature(entry: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(entry.get("table") or "").strip(),
        str(entry.get("FK") or "").strip(),
        str(entry.get("target") or "").strip(),
    )


def _add_relationship_exclude(
    overlay: dict[str, Any], *, table: str, fk: str = "", target: str = ""
) -> bool:
    exclude = overlay.setdefault("exclude", {})
    if not isinstance(exclude, dict):
        exclude = {}
        overlay["exclude"] = exclude
    rels = _ensure_list(exclude, "relationships")
    entry = {"table": table}
    if fk:
        entry["FK"] = fk
    if target:
        entry["target"] = target
    sig = _rel_signature(entry)
    for existing in rels:
        if isinstance(existing, dict) and _rel_signature(existing) == sig:
            return False
    rels.append(entry)
    return True


def _remove_relationship_exclude(
    overlay: dict[str, Any], *, table: str, fk: str = "", target: str = ""
) -> bool:
    exclude = overlay.get("exclude")
    if not isinstance(exclude, dict):
        return False
    rels = exclude.get("relationships")
    if not isinstance(rels, list):
        return False
    sig = (table, fk, target)
    kept: list[Any] = []
    removed = False
    for existing in rels:
        if isinstance(existing, dict) and _rel_signature(existing) == sig:
            removed = True
            continue
        kept.append(existing)
    exclude["relationships"] = kept
    return removed


def _tag_signature(entry: dict[str, Any]) -> tuple[str, str, frozenset[str]]:
    tags = {
        str(t).strip()
        for t in (entry.get("tags") or [])
        if str(t).strip()
    }
    return (
        str(entry.get("silver_entity") or "").strip(),
        str(entry.get("name") or "").strip(),
        frozenset(tags),
    )


def _add_tag_exclude(
    overlay: dict[str, Any],
    *,
    silver_entity: str,
    name: str,
    tags: list[str],
) -> bool:
    exclude = overlay.setdefault("exclude", {})
    if not isinstance(exclude, dict):
        exclude = {}
        overlay["exclude"] = exclude
    entries = _ensure_list(exclude, "tags")
    clean_tags = [str(t).strip() for t in tags if str(t).strip()]
    if not clean_tags:
        return False

    # Merge into existing entry for same entity+property when present.
    for existing in entries:
        if not isinstance(existing, dict):
            continue
        if (
            str(existing.get("silver_entity") or "").strip() == silver_entity
            and str(existing.get("name") or "").strip() == name
        ):
            current = _ensure_list(existing, "tags")
            before = {str(t).strip() for t in current}
            changed = False
            for tag in clean_tags:
                if tag not in before:
                    current.append(tag)
                    before.add(tag)
                    changed = True
            return changed

    entries.append(
        {"silver_entity": silver_entity, "name": name, "tags": clean_tags}
    )
    return True


def _remove_tag_exclude(
    overlay: dict[str, Any],
    *,
    silver_entity: str,
    name: str,
    tags: list[str],
) -> bool:
    exclude = overlay.get("exclude")
    if not isinstance(exclude, dict):
        return False
    entries = exclude.get("tags")
    if not isinstance(entries, list):
        return False
    drop = {str(t).strip() for t in tags if str(t).strip()}
    if not drop:
        return False
    kept: list[Any] = []
    changed = False
    for existing in entries:
        if not isinstance(existing, dict):
            kept.append(existing)
            continue
        if (
            str(existing.get("silver_entity") or "").strip() != silver_entity
            or str(existing.get("name") or "").strip() != name
        ):
            kept.append(existing)
            continue
        remaining = [
            str(t).strip()
            for t in (existing.get("tags") or [])
            if str(t).strip() and str(t).strip() not in drop
        ]
        if len(remaining) != len(list(existing.get("tags") or [])):
            changed = True
        if remaining:
            cloned = copy.deepcopy(existing)
            cloned["tags"] = remaining
            kept.append(cloned)
        else:
            changed = True
    exclude["tags"] = kept
    return changed


def apply_exclude(
    settings: DnaSettings,
    *,
    kind: ExcludeKind,
    source: str | None = None,
    table: str = "",
    fk: str = "",
    target: str = "",
    silver_entity: str = "",
    name: str = "",
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """Add exclude entries to live overlays. Returns pending summary."""
    connector = normalize_reference_source(source or settings.source)
    changed = False

    if kind == "table":
        table_name = (table or silver_entity).strip()
        if not table_name:
            raise ValueError("table is required")
        for artifact in GOLD_ARTIFACTS:
            overlay = ensure_overlay(settings, artifact, source=connector)
            if _add_table_exclude(overlay, table_name):
                changed = True
                save_overlay(settings, artifact, overlay, source=connector)
    elif kind == "relationship":
        table_name = table.strip()
        if not table_name:
            raise ValueError("table is required")
        overlay = ensure_overlay(settings, "entity_relationships", source=connector)
        if _add_relationship_exclude(
            overlay, table=table_name, fk=fk.strip(), target=target.strip()
        ):
            changed = True
            save_overlay(settings, "entity_relationships", overlay, source=connector)
    elif kind == "tag":
        entity = (silver_entity or table).strip()
        prop = name.strip()
        tag_list = list(tags or [])
        if not entity or not prop or not tag_list:
            raise ValueError("silver_entity, name, and tags are required")
        overlay = ensure_overlay(settings, "entity_property_tags", source=connector)
        if _add_tag_exclude(
            overlay, silver_entity=entity, name=prop, tags=tag_list
        ):
            changed = True
            save_overlay(settings, "entity_property_tags", overlay, source=connector)
    else:
        raise ValueError(f"Unsupported exclude kind {kind!r}")

    pending = list_pending_excludes(settings, source=connector)
    return {"changed": changed, "source": connector, "pending": pending, "pending_count": len(pending)}


def undo_exclude(
    settings: DnaSettings,
    *,
    kind: ExcludeKind,
    source: str | None = None,
    table: str = "",
    fk: str = "",
    target: str = "",
    silver_entity: str = "",
    name: str = "",
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """Remove matching exclude entries from live overlays."""
    connector = normalize_reference_source(source or settings.source)
    changed = False

    if kind == "table":
        table_name = (table or silver_entity).strip()
        if not table_name:
            raise ValueError("table is required")
        for artifact in GOLD_ARTIFACTS:
            overlay = ensure_overlay(settings, artifact, source=connector)
            if _remove_table_exclude(overlay, table_name):
                changed = True
                save_overlay(settings, artifact, overlay, source=connector)
    elif kind == "relationship":
        table_name = table.strip()
        if not table_name:
            raise ValueError("table is required")
        overlay = ensure_overlay(settings, "entity_relationships", source=connector)
        if _remove_relationship_exclude(
            overlay, table=table_name, fk=fk.strip(), target=target.strip()
        ):
            changed = True
            save_overlay(settings, "entity_relationships", overlay, source=connector)
    elif kind == "tag":
        entity = (silver_entity or table).strip()
        prop = name.strip()
        tag_list = list(tags or [])
        if not entity or not prop or not tag_list:
            raise ValueError("silver_entity, name, and tags are required")
        overlay = ensure_overlay(settings, "entity_property_tags", source=connector)
        if _remove_tag_exclude(
            overlay, silver_entity=entity, name=prop, tags=tag_list
        ):
            changed = True
            save_overlay(settings, "entity_property_tags", overlay, source=connector)
    else:
        raise ValueError(f"Unsupported exclude kind {kind!r}")

    pending = list_pending_excludes(settings, source=connector)
    return {"changed": changed, "source": connector, "pending": pending, "pending_count": len(pending)}


def _exclude_items_from_overlay(artifact: str, overlay: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(overlay, dict):
        return []
    exclude = overlay.get("exclude")
    if not isinstance(exclude, dict):
        return []
    items: list[dict[str, Any]] = []
    for table in exclude.get("tables") or []:
        name = str(table).strip()
        if name:
            items.append({"kind": "table", "artifact": artifact, "table": name})
    if artifact == "entity_relationships":
        for entry in exclude.get("relationships") or []:
            if not isinstance(entry, dict):
                continue
            table = str(entry.get("table") or "").strip()
            if not table:
                continue
            items.append(
                {
                    "kind": "relationship",
                    "artifact": artifact,
                    "table": table,
                    "FK": str(entry.get("FK") or "").strip(),
                    "target": str(entry.get("target") or "").strip(),
                }
            )
    if artifact == "entity_property_tags":
        for entry in exclude.get("tags") or []:
            if not isinstance(entry, dict):
                continue
            silver = str(entry.get("silver_entity") or "").strip()
            prop = str(entry.get("name") or "").strip()
            tags = [str(t).strip() for t in (entry.get("tags") or []) if str(t).strip()]
            if not silver or not prop or not tags:
                continue
            for tag in tags:
                items.append(
                    {
                        "kind": "tag",
                        "artifact": artifact,
                        "silver_entity": silver,
                        "name": prop,
                        "tag": tag,
                        "tags": [tag],
                    }
                )
        for entry in exclude.get("properties") or []:
            if not isinstance(entry, dict):
                continue
            silver = str(entry.get("silver_entity") or "").strip()
            for prop_name in entry.get("names") or []:
                pname = str(prop_name).strip()
                if silver and pname:
                    items.append(
                        {
                            "kind": "property",
                            "artifact": artifact,
                            "silver_entity": silver,
                            "name": pname,
                        }
                    )
    if artifact == "entity_properties":
        for entry in exclude.get("properties") or []:
            if not isinstance(entry, dict):
                continue
            silver = str(entry.get("silver_entity") or "").strip()
            for prop_name in entry.get("names") or []:
                pname = str(prop_name).strip()
                if silver and pname:
                    items.append(
                        {
                            "kind": "property",
                            "artifact": artifact,
                            "silver_entity": silver,
                            "name": pname,
                        }
                    )
    return items


def _item_key(item: dict[str, Any]) -> tuple[Any, ...]:
    kind = item.get("kind")
    if kind == "table":
        return ("table", item.get("artifact"), item.get("table"))
    if kind == "relationship":
        return (
            "relationship",
            item.get("table"),
            item.get("FK"),
            item.get("target"),
        )
    if kind == "tag":
        return (
            "tag",
            item.get("silver_entity"),
            item.get("name"),
            item.get("tag"),
        )
    if kind == "property":
        return (
            "property",
            item.get("artifact"),
            item.get("silver_entity"),
            item.get("name"),
        )
    return ("other", str(item))


def load_manifest(settings: DnaSettings, *, source: str | None = None) -> dict[str, Any]:
    connector = normalize_reference_source(source or settings.source)
    payload = read_yaml_artifact(
        settings, governance_source_docs_versions_manifest_key(connector)
    )
    if isinstance(payload, dict):
        versions = payload.get("versions")
        if not isinstance(versions, list):
            payload["versions"] = []
        return payload
    return {
        "source": connector,
        "kind": "source_docs_versions_manifest",
        "active_version": None,
        "versions": [],
    }


def save_manifest(
    settings: DnaSettings, manifest: dict[str, Any], *, source: str | None = None
) -> str:
    connector = normalize_reference_source(source or settings.source)
    key = governance_source_docs_versions_manifest_key(connector)
    write_yaml_artifact(settings, key, manifest)
    return key


def _committed_overlay(
    settings: DnaSettings, artifact: str, *, source: str, version: int | None
) -> dict[str, Any] | None:
    if version is None:
        return None
    filename = _FILENAMES[artifact]
    return read_yaml_artifact(
        settings,
        governance_source_docs_version_overlay_key(source, version, filename),
    )


def list_pending_excludes(
    settings: DnaSettings, *, source: str | None = None
) -> list[dict[str, Any]]:
    """Exclude entries in live overlays that are not in the active version snapshot."""
    connector = normalize_reference_source(source or settings.source)
    manifest = load_manifest(settings, source=connector)
    active = manifest.get("active_version")
    active_version = int(active) if active is not None else None

    live_items: list[dict[str, Any]] = []
    committed_keys: set[tuple[Any, ...]] = set()

    for artifact in GOLD_ARTIFACTS:
        live = load_overlay(settings, artifact, source=connector)
        live_items.extend(_exclude_items_from_overlay(artifact, live))
        committed = _committed_overlay(
            settings, artifact, source=connector, version=active_version
        )
        for item in _exclude_items_from_overlay(artifact, committed):
            committed_keys.add(_item_key(item))

    # Table excludes appear on all three overlays; collapse to one pending row.
    pending: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for item in live_items:
        key = _item_key(item)
        if key in committed_keys:
            continue
        # Deduplicate table excludes across artifacts for UI.
        if item.get("kind") == "table":
            ui_key = ("table", item.get("table"))
            if ui_key in seen:
                continue
            seen.add(ui_key)
            pending.append(
                {
                    "kind": "table",
                    "table": item.get("table"),
                    "artifacts": list(GOLD_ARTIFACTS),
                }
            )
            continue
        if key in seen:
            continue
        seen.add(key)
        pending.append(item)
    return pending


def _next_version_number(manifest: dict[str, Any]) -> int:
    versions = manifest.get("versions") or []
    max_v = 0
    for entry in versions:
        if not isinstance(entry, dict):
            continue
        try:
            max_v = max(max_v, int(entry.get("version") or 0))
        except (TypeError, ValueError):
            continue
    return max_v + 1


def commit_version(
    settings: DnaSettings,
    *,
    source: str | None = None,
    note: str = "",
    restored_from: int | None = None,
) -> dict[str, Any]:
    """Snapshot current live overlays + gold into versions/vN and update manifest."""
    connector = normalize_reference_source(source or settings.source)
    manifest = load_manifest(settings, source=connector)
    version = _next_version_number(manifest)

    for artifact in GOLD_ARTIFACTS:
        filename = _FILENAMES[artifact]
        overlay = load_overlay(settings, artifact, source=connector)
        if overlay is None:
            overlay = empty_overlay(connector, artifact)
            save_overlay(settings, artifact, overlay, source=connector)
        write_yaml_artifact(
            settings,
            governance_source_docs_version_overlay_key(connector, version, filename),
            overlay,
        )
        gold = read_yaml_artifact(
            settings, source_docs_gold_key(settings, artifact, source=connector)
        )
        if gold is None:
            raise ValueError(
                f"Cannot commit version: missing gold artifact {artifact!r} for {connector}"
            )
        write_yaml_artifact(
            settings,
            governance_source_docs_version_gold_key(connector, version, filename),
            gold,
        )

    entry: dict[str, Any] = {
        "version": version,
        "created_at": _utcnow(),
        "note": note or ("Restored from v{0}".format(restored_from) if restored_from else "Submitted"),
    }
    if restored_from is not None:
        entry["restored_from"] = int(restored_from)

    versions = list(manifest.get("versions") or [])
    versions.append(entry)
    manifest["source"] = connector
    manifest["kind"] = "source_docs_versions_manifest"
    manifest["active_version"] = version
    manifest["versions"] = versions
    save_manifest(settings, manifest, source=connector)

    return {
        "source": connector,
        "version": version,
        "manifest": manifest,
        "entry": entry,
    }


def restore_version(
    settings: DnaSettings,
    *,
    version: int,
    source: str | None = None,
) -> dict[str, Any]:
    """Rewrite live overlays + gold from a snapshot and record a new restored version."""
    connector = normalize_reference_source(source or settings.source)
    target = int(version)
    for artifact in GOLD_ARTIFACTS:
        filename = _FILENAMES[artifact]
        overlay = read_yaml_artifact(
            settings,
            governance_source_docs_version_overlay_key(connector, target, filename),
        )
        gold = read_yaml_artifact(
            settings,
            governance_source_docs_version_gold_key(connector, target, filename),
        )
        if overlay is None or gold is None:
            raise ValueError(
                f"Version v{target} is incomplete (missing {artifact} overlay or gold)"
            )
        save_overlay(settings, artifact, overlay, source=connector)
        write_yaml_artifact(
            settings,
            source_docs_gold_key(settings, artifact, source=connector),
            gold,
        )

    return commit_version(
        settings,
        source=connector,
        note=f"Restored from v{target}",
        restored_from=target,
    )


def list_versions(settings: DnaSettings, *, source: str | None = None) -> dict[str, Any]:
    connector = normalize_reference_source(source or settings.source)
    manifest = load_manifest(settings, source=connector)
    pending = list_pending_excludes(settings, source=connector)
    return {
        "source": connector,
        "active_version": manifest.get("active_version"),
        "versions": list(reversed(list(manifest.get("versions") or []))),
        "pending": pending,
        "pending_count": len(pending),
        "manifest": manifest,
    }
