"""Load client gold source-documentation catalogs from the lake bucket.

Reads governance/source_semantic_reference/{source}/gold/*.yaml produced by the
bc-source-docs-gold Lambda (global MS Learn catalogs + client overlays).
"""

from __future__ import annotations

from typing import Any

from meshflow.dna.settings import DnaSettings
from meshflow.dna.store import read_yaml_artifact
from meshflow.storage.paths import governance_source_docs_gold_key

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


def source_docs_gold_key(settings: DnaSettings, artifact: str) -> str:
    name = _FILENAMES.get(artifact)
    if not name:
        raise ValueError(f"Unknown gold artifact {artifact!r}")
    return governance_source_docs_gold_key(settings.source, name)


def load_source_docs_gold_artifact(settings: DnaSettings, artifact: str) -> dict[str, Any] | None:
    return read_yaml_artifact(settings, source_docs_gold_key(settings, artifact))


def load_source_docs_gold(settings: DnaSettings) -> dict[str, Any]:
    """Return all gold catalogs plus presence flags for the inspector UI."""
    artifacts: dict[str, dict[str, Any] | None] = {}
    present: dict[str, bool] = {}
    for name in GOLD_ARTIFACTS:
        payload = load_source_docs_gold_artifact(settings, name)
        artifacts[name] = payload
        present[name] = payload is not None

    any_present = any(present.values())
    all_present = all(present.values())
    properties = artifacts.get("entity_properties") or {}
    relationships = artifacts.get("entity_relationships") or {}
    tags = artifacts.get("entity_property_tags") or {}

    return {
        "source": settings.source.strip().lower(),
        "available": any_present,
        "complete": all_present,
        "present": present,
        "entity_properties": properties if present["entity_properties"] else None,
        "entity_relationships": relationships if present["entity_relationships"] else None,
        "entity_property_tags": tags if present["entity_property_tags"] else None,
        "summary": {
            "entity_count": int(properties.get("entity_count") or len(properties.get("entities") or [])),
            "property_count": int(properties.get("property_count") or 0),
            "table_count": int(relationships.get("table_count") or len(relationships.get("tables") or {})),
            "relationship_count": int(relationships.get("relationship_count") or 0),
            "tagged_property_count": int(tags.get("tagged_property_count") or 0),
            "generated_at": str(
                properties.get("generated_at")
                or relationships.get("generated_at")
                or tags.get("generated_at")
                or ""
            ),
        },
    }
