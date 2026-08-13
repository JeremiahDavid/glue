"""Load client gold source-documentation catalogs from the lake bucket.

Reads governance/source_semantic_reference/{source}/gold/*.yaml produced by the
source-docs-gold Lambda (global catalogs + client overlays). Each connector
source has its own gold prefix and Semantic Reference.
"""

from __future__ import annotations

from typing import Any

from meshflow.dna.settings import DnaSettings
from meshflow.dna.store import read_yaml_artifact
from meshflow.storage.paths import (
    governance_source_docs_gold_key,
    governance_source_semantic_reference_prefix,
)

GOLD_ARTIFACTS: tuple[str, ...] = (
    "entity_properties",
    "entity_relationships",
    "entity_property_tags",
)

_FILENAMES: dict[str, str] = {
    "entity_properties": "entity_properties.yaml",
    "entity_relationships": "entity_relationships.yaml",
    "entity_property_tags": "entity_property_tags.yaml",
}

# Sources with a global docs → client gold merge pipeline today.
GOLD_BUILD_SOURCES: frozenset[str] = frozenset({"dbc"})


def normalize_reference_source(source: str) -> str:
    key = source.strip().lower()
    if key == "bc":
        return "dbc"
    return key


def source_docs_gold_key(settings: DnaSettings, artifact: str, *, source: str | None = None) -> str:
    name = _FILENAMES.get(artifact)
    if not name:
        raise ValueError(f"Unknown gold artifact {artifact!r}")
    connector = normalize_reference_source(source or settings.source)
    return governance_source_docs_gold_key(connector, name)


def load_source_docs_gold_artifact(
    settings: DnaSettings,
    artifact: str,
    *,
    source: str | None = None,
) -> dict[str, Any] | None:
    return read_yaml_artifact(
        settings,
        source_docs_gold_key(settings, artifact, source=source),
    )


def source_supports_gold_build(source: str) -> bool:
    return normalize_reference_source(source) in GOLD_BUILD_SOURCES


def list_reference_sources(
    settings: DnaSettings,
    *,
    configured: list[str] | None = None,
) -> list[str]:
    """Ordered connector sources that can appear in the Semantic Reference UI."""
    ordered: list[str] = []
    seen: set[str] = set()

    def _add(raw: str) -> None:
        key = normalize_reference_source(raw)
        if not key or key in seen:
            return
        seen.add(key)
        ordered.append(key)

    primary = normalize_reference_source(settings.source)
    if primary:
        _add(primary)
    for item in configured or []:
        _add(item)
    # Prefer known connector order after the primary DNA source.
    for item in ("dbc", "qbo", "qbd"):
        if item in seen:
            continue
        # Only append known connectors when they were configured.
        if configured is None:
            continue
        if item in {normalize_reference_source(c) for c in configured}:
            _add(item)
    return ordered


def load_source_docs_gold(settings: DnaSettings, *, source: str | None = None) -> dict[str, Any]:
    """Return all gold catalogs plus presence flags for one connector source."""
    connector = normalize_reference_source(source or settings.source)
    artifacts: dict[str, dict[str, Any] | None] = {}
    present: dict[str, bool] = {}
    for name in GOLD_ARTIFACTS:
        payload = load_source_docs_gold_artifact(settings, name, source=connector)
        artifacts[name] = payload
        present[name] = payload is not None

    any_present = any(present.values())
    all_present = all(present.values())
    properties = artifacts.get("entity_properties") or {}
    relationships = artifacts.get("entity_relationships") or {}
    tags = artifacts.get("entity_property_tags") or {}
    artifact_generated_at = {
        name: str((artifacts.get(name) or {}).get("generated_at") or "")
        for name in GOLD_ARTIFACTS
        if present.get(name)
    }

    return {
        "source": connector,
        "prefix": governance_source_semantic_reference_prefix(connector),
        "gold_prefix": f"{governance_source_semantic_reference_prefix(connector)}/gold",
        "available": any_present,
        "complete": all_present,
        "build_supported": source_supports_gold_build(connector),
        "present": present,
        "entity_properties": properties if present["entity_properties"] else None,
        "entity_relationships": relationships if present["entity_relationships"] else None,
        "entity_property_tags": tags if present["entity_property_tags"] else None,
        "summary": {
            "table_count": int(
                properties.get("table_count")
                or properties.get("entity_count")
                or len(properties.get("tables") or properties.get("entities") or [])
            ),
            "property_count": int(properties.get("property_count") or 0),
            "relationship_count": int(relationships.get("relationship_count") or 0),
            "tagged_property_count": int(tags.get("tagged_property_count") or 0),
            "generated_at": str(
                properties.get("generated_at")
                or relationships.get("generated_at")
                or tags.get("generated_at")
                or ""
            ),
            # Per-artifact stamps so rebuild/submit polling waits for tags too
            # (properties are written first and would otherwise look "fresh" early).
            "artifact_generated_at": artifact_generated_at,
        },
    }
