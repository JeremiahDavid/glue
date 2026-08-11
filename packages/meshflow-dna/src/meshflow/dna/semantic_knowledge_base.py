"""Connector knowledge bases and tenant semantic overrides for RAG-backed init."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from meshflow.dna.semantic_doc_retrieval import DocumentChunk, chunk_markdown_by_heading
from meshflow.dna.settings import DnaSettings
from meshflow.dna.store import read_text_artifact, read_yaml_artifact
from meshflow.repo_paths import find_project_root
from meshflow.storage.paths import (
    governance_semantic_docs_prefix,
    governance_semantic_overrides_key,
    prefix_path,
)

CONNECTOR_KNOWLEDGE_DIR = "connector_knowledge"
_LEGACY_SOURCE_SEMANTIC_DIR = "source_semantic"
_HINT_LIST_KEYS = ("entities", "relationships", "questions")


def connector_knowledge_root() -> Path:
    return Path(__file__).resolve().parent / "packs" / CONNECTOR_KNOWLEDGE_DIR


def connector_manifest_path(source: str) -> Path:
    connector = source.strip().lower()
    return connector_knowledge_root() / connector / "manifest.yaml"


def connector_hints_path(source: str) -> Path:
    connector = source.strip().lower()
    return connector_knowledge_root() / connector / "hints.yaml"


def connector_profiling_rules_path(source: str) -> Path:
    connector = source.strip().lower()
    return connector_knowledge_root() / connector / "profiling_rules.yaml"


def _legacy_source_semantic_path(source: str) -> Path:
    connector = source.strip().lower()
    return Path(__file__).resolve().parent / "packs" / _LEGACY_SOURCE_SEMANTIC_DIR / f"{connector}.yaml"


def _resolve_repo_doc_path(relative: str) -> Path | None:
    text = str(relative or "").strip().replace("\\", "/")
    if not text:
        return None
    root = find_project_root()
    path = (root / text).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError:
        return None
    return path if path.is_file() else None


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise ValueError(f"Knowledge YAML must be a mapping: {path}")
    return payload


@lru_cache(maxsize=16)
def load_connector_manifest(source: str) -> dict[str, Any]:
    """Connector-standard knowledge manifest (docs, label, description)."""
    path = connector_manifest_path(source)
    if not path.is_file():
        return {"source": source.strip().lower()}
    payload = _load_yaml_mapping(path)
    payload.setdefault("source", source.strip().lower())
    return payload


def load_connector_profiling_rules(source: str) -> dict[str, Any]:
    """Scraped baseline profiling rules (Microsoft APV2 docs)."""
    path = connector_profiling_rules_path(source)
    if not path.is_file():
        return {}
    payload = _load_yaml_mapping(path)
    if payload:
        from meshflow.dna.connector_knowledge_schema import validate_connector_knowledge

        validate_connector_knowledge(payload)
    return payload


def load_connector_documentation_hints(source: str) -> dict[str, Any]:
    """Hand-tuned hints merged with scraped profiling rules (documentation only)."""
    from meshflow.dna.bc_profiling_rules import merge_profiling_rules_into_hints

    path = connector_hints_path(source)
    if path.is_file():
        hints = _load_yaml_mapping(path)
    else:
        legacy = _legacy_source_semantic_path(source)
        hints = _load_yaml_mapping(legacy) if legacy.is_file() else {}
    profiling_rules = load_connector_profiling_rules(source)
    if profiling_rules:
        hints = merge_profiling_rules_into_hints(hints, profiling_rules)
    return hints


def load_connector_standard_hints(source: str) -> dict[str, Any]:
    """Connector-standard structured hints (roles, joins, column tags, questions)."""
    return load_connector_documentation_hints(source)


def load_tenant_semantic_overrides(settings: DnaSettings) -> dict[str, Any]:
    """Client-specific YAML overrides stored in governance."""
    key = governance_semantic_overrides_key(settings.dna_config_id)
    payload = read_yaml_artifact(settings, key)
    return payload if isinstance(payload, dict) else {}


def _index_hint_entities(items: list[Any]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        silver_entity = str(item.get("silver_entity") or "").strip().lower()
        if silver_entity:
            indexed[silver_entity] = dict(item)
    return indexed


def _index_hint_relationships(items: list[Any]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        rel_id = str(item.get("id") or "").strip().lower()
        if rel_id:
            indexed[rel_id] = dict(item)
    return indexed


def _index_hint_questions(items: list[Any]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        question_id = str(item.get("id") or "").strip().lower()
        if question_id:
            indexed[question_id] = dict(item)
    return indexed


def merge_semantic_hints(
    connector_hints: dict[str, Any],
    tenant_overrides: dict[str, Any],
) -> dict[str, Any]:
    """Merge connector-standard hints with tenant overrides (tenant wins on conflicts)."""
    merged: dict[str, Any] = {
        "source": str(tenant_overrides.get("source") or connector_hints.get("source") or "").strip().lower(),
        "description": str(
            tenant_overrides.get("description") or connector_hints.get("description") or ""
        ).strip(),
    }

    connector_entities = _index_hint_entities(list(connector_hints.get("entities") or []))
    tenant_entities = _index_hint_entities(list(tenant_overrides.get("entities") or []))
    entity_keys = sorted(set(connector_entities) | set(tenant_entities))
    merged["entities"] = [
        {**connector_entities.get(key, {}), **tenant_entities.get(key, {})}
        for key in entity_keys
        if connector_entities.get(key) or tenant_entities.get(key)
    ]

    connector_relationships = _index_hint_relationships(list(connector_hints.get("relationships") or []))
    tenant_relationships = _index_hint_relationships(list(tenant_overrides.get("relationships") or []))
    rel_keys = sorted(set(connector_relationships) | set(tenant_relationships))
    merged["relationships"] = [
        {**connector_relationships.get(key, {}), **tenant_relationships.get(key, {})}
        for key in rel_keys
        if connector_relationships.get(key) or tenant_relationships.get(key)
    ]

    connector_questions = _index_hint_questions(list(connector_hints.get("questions") or []))
    tenant_questions = _index_hint_questions(list(tenant_overrides.get("questions") or []))
    question_keys = sorted(set(connector_questions) | set(tenant_questions))
    merged["questions"] = [
        {**connector_questions.get(key, {}), **tenant_questions.get(key, {})}
        for key in question_keys
        if connector_questions.get(key) or tenant_questions.get(key)
    ]

    entity_column_hints: dict[str, dict[str, Any]] = {}
    for source in (connector_hints, tenant_overrides):
        hints = source.get("entity_column_hints")
        if isinstance(hints, dict):
            for entity, per_entity in hints.items():
                if not isinstance(per_entity, dict):
                    continue
                entity_key = str(entity).strip().lower()
                entity_column_hints.setdefault(entity_key, {}).update(per_entity)
    if entity_column_hints:
        merged["entity_column_hints"] = entity_column_hints
    profiling_rules = connector_hints.get("profiling_rules")
    if isinstance(profiling_rules, dict):
        merged["profiling_rules"] = dict(profiling_rules)
    if connector_hints.get("baseline"):
        merged["baseline"] = connector_hints.get("baseline")
        baseline_meta = connector_hints.get("baseline_meta")
        if isinstance(baseline_meta, dict):
            merged["baseline_meta"] = dict(baseline_meta)
    column_tags = connector_hints.get("column_tags")
    if isinstance(column_tags, dict):
        merged["column_tags"] = dict(column_tags)
    return merged


def load_merged_semantic_hints(settings: DnaSettings) -> dict[str, Any]:
    """Connector-standard hints merged with tenant governance overrides."""
    source = settings.source.strip().lower()
    return merge_semantic_hints(
        load_connector_standard_hints(source),
        load_tenant_semantic_overrides(settings),
    )


def _list_connector_knowledge_markdown(source: str) -> list[tuple[str, str]]:
    connector = source.strip().lower()
    base = connector_knowledge_root() / connector
    if not base.is_dir():
        return []
    docs: list[tuple[str, str]] = []
    for path in sorted(base.rglob("*")):
        if path.is_file() and path.suffix.lower() in {".md", ".txt"}:
            if path.name in {"manifest.yaml", "hints.yaml"}:
                continue
            docs.append((path.name, path.read_text(encoding="utf-8")))
    return docs


def _list_manifest_documentation(source: str) -> list[tuple[str, str]]:
    manifest = load_connector_manifest(source)
    docs: list[tuple[str, str]] = []
    for entry in manifest.get("documentation") or []:
        path = _resolve_repo_doc_path(str(entry))
        if path is not None:
            docs.append((path.name, path.read_text(encoding="utf-8")))
    return docs


def _list_tenant_doc_texts(settings: DnaSettings) -> list[tuple[str, str]]:
    prefix = governance_semantic_docs_prefix(settings.dna_config_id)
    docs: list[tuple[str, str]] = []
    if settings.s3_bucket:
        import boto3

        client = boto3.client("s3")
        paginator = client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=settings.s3_bucket, Prefix=f"{prefix}/"):
            for item in page.get("Contents") or []:
                key = str(item.get("Key") or "")
                if not key.lower().endswith((".md", ".txt")):
                    continue
                text = read_text_artifact(settings, key)
                if text:
                    docs.append((key.rsplit("/", 1)[-1], text))
        return docs

    base = prefix_path(settings.data_dir, prefix)
    if not base.is_dir():
        return docs
    for path in sorted(base.rglob("*")):
        if path.is_file() and path.suffix.lower() in {".md", ".txt"}:
            docs.append((path.name, path.read_text(encoding="utf-8")))
    return docs


def load_semantic_knowledge_corpus(settings: DnaSettings) -> list[DocumentChunk]:
    """Load RAG corpus: connector standard docs, then tenant-specific references."""
    source = settings.source.strip().lower()
    chunks: list[DocumentChunk] = []

    for filename, text in _list_manifest_documentation(source):
        chunks.extend(
            chunk_markdown_by_heading(
                text,
                source=f"connector:{source}/{filename}",
                title_prefix=filename,
            )
        )

    for filename, text in _list_connector_knowledge_markdown(source):
        chunks.extend(
            chunk_markdown_by_heading(
                text,
                source=f"connector:{source}/{filename}",
                title_prefix=filename,
            )
        )

    # Backward-compatible fallback when manifest has no documentation entries.
    if not chunks:
        root = find_project_root()
        builtin = root / "docs" / f"{source}-data-model.md"
        if not builtin.is_file() and source == "dbc":
            builtin = root / "docs" / "dbc-data-model.md"
        if builtin.is_file():
            text = builtin.read_text(encoding="utf-8")
            chunks.extend(
                chunk_markdown_by_heading(text, source=str(builtin.name), title_prefix=builtin.stem)
            )

    for filename, text in _list_tenant_doc_texts(settings):
        chunks.extend(
            chunk_markdown_by_heading(
                text,
                source=f"tenant:{filename}",
                title_prefix=f"Client: {filename}",
            )
        )

    return chunks


def knowledge_base_summary(settings: DnaSettings) -> dict[str, Any]:
    """Summary payload for assistant / API consumers."""
    source = settings.source.strip().lower()
    manifest = load_connector_manifest(source)
    hints = load_merged_semantic_hints(settings)
    profiling_meta = hints.get("profiling_rules") if isinstance(hints.get("profiling_rules"), dict) else {}
    from meshflow.dna.semantic_source_profile import load_latest_source_profile

    latest_profile = load_latest_source_profile(settings, source)
    corpus = load_semantic_knowledge_corpus(settings)
    return {
        "source": source,
        "connector": {
            "label": manifest.get("label"),
            "description": manifest.get("description"),
            "documentation_paths": list(manifest.get("documentation") or []),
            "profiling_rules_path": str(manifest.get("profiling_rules") or ""),
            "profiling_rules_generated_at": profiling_meta.get("generated_at"),
            "profiling_rules_entity_count": profiling_meta.get("entity_count"),
            "latest_profile_generated_at": (latest_profile or {}).get("generated_at"),
            "latest_profile_approved_build_count": (latest_profile or {}).get("approved_build_count"),
            "hint_entity_count": len(hints.get("entities") or []),
            "hint_relationship_count": len(hints.get("relationships") or []),
        },
        "tenant": {
            "override_entity_count": len(load_tenant_semantic_overrides(settings).get("entities") or []),
            "doc_chunk_count": sum(1 for chunk in corpus if chunk.source.startswith("tenant:")),
        },
        "corpus_chunk_count": len(corpus),
    }
