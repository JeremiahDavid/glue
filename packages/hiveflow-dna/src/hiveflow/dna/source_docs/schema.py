"""JSON Schema validation for BC source documentation YAML artifacts.

Schemas ship in-package under ``hiveflow.dna.source_docs.schemas`` and are also
published to ``s3://hiveflowai-source-documentation/{source}/schemas/`` so
global catalogs and client overlays share one contract.
"""

from __future__ import annotations

import json
from functools import lru_cache
from importlib.resources import files
from typing import Any, Literal

import jsonschema

ArtifactName = Literal[
    "entity_properties",
    "entity_relationships",
    "entity_property_tags",
]

_SCHEMA_FILES: dict[tuple[ArtifactName, str], str] = {
    ("entity_properties", "catalog"): "entity_properties.schema.json",
    ("entity_properties", "overlay"): "entity_properties.overlay.schema.json",
    ("entity_relationships", "catalog"): "entity_relationships.schema.json",
    ("entity_relationships", "overlay"): "entity_relationships.overlay.schema.json",
    ("entity_property_tags", "catalog"): "entity_property_tags.schema.json",
    ("entity_property_tags", "overlay"): "entity_property_tags.overlay.schema.json",
}

SCHEMA_ARTIFACT_NAMES: tuple[ArtifactName, ...] = (
    "entity_properties",
    "entity_relationships",
    "entity_property_tags",
)


def source_docs_schemas_prefix(source: str = "dbc") -> str:
    connector = source.strip().lower() or "dbc"
    return f"{connector}/schemas"


def source_docs_schema_object_key(source: str, filename: str) -> str:
    name = filename.strip().lstrip("/")
    return f"{source_docs_schemas_prefix(source)}/{name}"


@lru_cache(maxsize=16)
def load_schema(artifact: ArtifactName, *, variant: str = "catalog") -> dict[str, Any]:
    key = (artifact, variant)
    filename = _SCHEMA_FILES.get(key)
    if not filename:
        raise ValueError(f"Unknown schema {artifact!r} variant {variant!r}")
    text = files("hiveflow.dna.source_docs").joinpath(f"schemas/{filename}").read_text(encoding="utf-8")
    return json.loads(text)


def list_schema_filenames() -> list[str]:
    return sorted({name for name in _SCHEMA_FILES.values()})


def validate_source_docs_payload(
    payload: dict[str, Any],
    *,
    artifact: ArtifactName,
    variant: Literal["catalog", "overlay"] = "catalog",
) -> None:
    """Raise jsonschema.ValidationError when payload does not match the schema."""
    if not isinstance(payload, dict):
        raise ValueError("payload must be a mapping")
    jsonschema.validate(payload, load_schema(artifact, variant=variant))


def publish_source_docs_schemas(
    *,
    bucket: str | None = None,
    source: str = "dbc",
) -> dict[str, Any]:
    """Upload in-package schemas to the global source-documentation bucket."""
    import boto3

    from hiveflow.dna.source_docs.scrape import source_docs_bucket_name

    bucket_name = (bucket or source_docs_bucket_name()).strip()
    client = boto3.client("s3")
    uploaded: list[dict[str, str]] = []
    for filename in list_schema_filenames():
        text = files("hiveflow.dna.source_docs").joinpath(f"schemas/{filename}").read_text(encoding="utf-8")
        key = source_docs_schema_object_key(source, filename)
        client.put_object(
            Bucket=bucket_name,
            Key=key,
            Body=text.encode("utf-8"),
            ContentType="application/schema+json",
        )
        uploaded.append({"bucket": bucket_name, "key": key})
    return {
        "status": "published",
        "source": source.strip().lower() or "dbc",
        "schema_count": len(uploaded),
        "artifacts": uploaded,
    }
