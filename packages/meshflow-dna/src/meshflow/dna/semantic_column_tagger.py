"""LLM-assisted column concept tagging for semantic model init."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any, Callable

from meshflow.dna.field_semantics import (
    entity_column_concept_id,
    entity_column_concept_label,
    entity_singular_label,
    resolve_entity_column_concepts,
)
from meshflow.dna.semantic_doc_retrieval import format_retrieved_chunks, retrieve_semantic_docs
from meshflow.dna.semantic_profiling import profile_summary_text
from meshflow.dna.settings import DnaSettings

_DEFAULT_BEDROCK_MODEL_ID = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
_JSON_BLOCK_RE = re.compile(r"\{[\s\S]*\}")
_STALE_GENERIC_CONCEPTS = frozenset(
    {
        "document_id",
        "document_status",
        "document_number",
        "posting_date",
        "order_date",
        "due_date",
        "customer_number",
        "revenue_amount",
        "display_name",
        "quantity",
    }
)

InvokeFn = Callable[[str, str], str]


@dataclass(frozen=True)
class ColumnTagSuggestion:
    concepts: list[str]
    confidence: float
    label: str
    notes: str
    citation: str
    role: str


def _parse_suggestion_payload(raw: str) -> dict[str, Any]:
    text = str(raw or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        match = _JSON_BLOCK_RE.search(text)
        if not match:
            return {}
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}


def _normalize_humanization(
    payload: dict[str, Any],
    *,
    concept_id: str,
    fallback_label: str,
) -> ColumnTagSuggestion:
    label = str(payload.get("label") or "").strip() or fallback_label
    notes = str(payload.get("notes") or "").strip()
    citation = str(payload.get("citation") or "").strip()
    role = str(payload.get("role") or "").strip().lower()
    return ColumnTagSuggestion(
        concepts=[concept_id],
        confidence=1.0,
        label=label,
        notes=notes,
        citation=citation,
        role=role,
    )


def _default_invoke(system: str, user_message: str) -> str:
    import boto3
    from botocore.config import Config

    model_id = os.getenv("MESHFLOW_BEDROCK_MODEL_ID", _DEFAULT_BEDROCK_MODEL_ID).strip()
    client = boto3.client(
        "bedrock-runtime",
        config=Config(read_timeout=60, connect_timeout=10, retries={"max_attempts": 2}),
    )
    response = client.converse(
        modelId=model_id,
        system=[{"text": system}],
        messages=[{"role": "user", "content": [{"text": user_message}]}],
        inferenceConfig={"maxTokens": 512, "temperature": 0.1},
    )
    output = response.get("output") or {}
    message = output.get("message") or {}
    content = message.get("content") or []
    texts = [
        str(block.get("text") or "")
        for block in content
        if isinstance(block, dict) and block.get("text")
    ]
    return "\n".join(texts).strip()


def humanize_column_tag(
    settings: DnaSettings,
    *,
    entity: str,
    column: str,
    concept_id: str,
    profile: dict[str, Any],
    invoke_fn: InvokeFn | None = None,
    rag_query: str | None = None,
    entity_context: str = "",
) -> ColumnTagSuggestion:
    """Write a business-readable label for an already-assigned entity-scoped concept id."""
    entity_name = entity.strip().lower()
    column_name = str(column or profile.get("column") or "").strip()
    normalized_concept_id = str(concept_id).strip().lower()
    fallback_label = (
        entity_column_concept_label(entity_name, column_name)
        if entity_name and column_name
        else normalized_concept_id.replace("_", " ").title()
    )
    query = rag_query or (
        f"{entity_name} {column_name} {profile.get('inferred_dtype')} "
        f"{' '.join(profile.get('sample_values') or [])} {entity_context}"
    )
    retrieved = retrieve_semantic_docs(settings, query, top_k=3)
    docs = format_retrieved_chunks(retrieved, max_chars=6000)
    entity_label = entity_singular_label(entity_name) if entity_name else entity_name
    system = """You write human-readable business labels for tagged silver warehouse columns.

Return JSON only:
{"label": "Purchase Order Number", "notes": "Reference to the related purchase order on this purchase invoice", "role": "identifier|measure|dimension|date|status"}

Rules:
- label is a short Title Case phrase (2-5 words) a business user recognizes
- interpret the column in its table context — do NOT mechanically join table and field names
- purchase_invoices.orderNumber → "Purchase Order Number" (the PO referenced on the invoice), NOT "Purchase Invoice Order Number"
- notes is one sentence explaining the business meaning
- role is optional analytics role
- the stable concept id is already assigned; do not invent a different id
"""
    user_message = f"""Humanize this column tag:

Silver table: {entity_name} ({entity_label})
Table context: {entity_context or "(no table description available)"}
Column: {column_name}
Stable concept id (already assigned): {normalized_concept_id}
Heuristic fallback label: {fallback_label}

{profile_summary_text(profile)}

Retrieved documentation:
{docs or "(no matching documentation chunks)"}
"""
    invoke = invoke_fn or _default_invoke
    raw = invoke(system, user_message)
    return _normalize_humanization(
        _parse_suggestion_payload(raw),
        concept_id=normalized_concept_id,
        fallback_label=fallback_label,
    )


def suggest_column_tags(
    settings: DnaSettings,
    *,
    entity: str,
    profile: dict[str, Any],
    invoke_fn: InvokeFn | None = None,
    rag_query: str | None = None,
    entity_context: str = "",
) -> ColumnTagSuggestion:
    """Suggest a humanized label for one silver column (concept id is assigned deterministically)."""
    entity_name = entity.strip().lower()
    column_name = str(profile.get("column") or "").strip()
    concepts = resolve_entity_column_concepts(entity_name, column_name)
    if not concepts:
        return ColumnTagSuggestion(
            concepts=[],
            confidence=0.0,
            label="",
            notes="No concept id could be resolved for this column",
            citation="",
            role="",
        )
    concept_id = concepts[0]
    return humanize_column_tag(
        settings,
        entity=entity_name,
        column=column_name,
        concept_id=concept_id,
        profile=profile,
        invoke_fn=invoke_fn,
        rag_query=rag_query,
        entity_context=entity_context,
    )


def llm_tagging_enabled() -> bool:
    raw = os.getenv("MESHFLOW_SEMANTIC_LLM_TAGGING", "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def llm_tagging_limit() -> int:
    raw = os.getenv("MESHFLOW_SEMANTIC_LLM_TAG_LIMIT", "500").strip()
    try:
        return max(0, int(raw))
    except ValueError:
        return 500


def _entity_context_by_name(draft_entities: list[dict[str, Any]] | None) -> dict[str, str]:
    contexts: dict[str, str] = {}
    for entity in draft_entities or []:
        if not isinstance(entity, dict):
            continue
        silver = str(entity.get("silver_entity") or "").strip().lower()
        if not silver:
            continue
        description = str(entity.get("description") or "").strip()
        role = str(entity.get("role") or "").strip().lower()
        grain = str(entity.get("grain") or "").strip().lower()
        parts = [part for part in (description, f"role={role}" if role else "", f"grain={grain}" if grain else "") if part]
        if parts:
            contexts[silver] = "; ".join(parts)
    return contexts


def _attribute_needs_tagging(attribute: dict[str, Any]) -> bool:
    if str(attribute.get("status") or "") not in {"proposed", ""}:
        return False
    if str(attribute.get("role") or "") == "foreign_key":
        return False
    concepts = [str(c).strip().lower() for c in attribute.get("concepts") or [] if str(c).strip()]
    if not concepts:
        return True
    if len(concepts) == 1 and concepts[0] in _STALE_GENERIC_CONCEPTS:
        return True
    return False


def _attribute_needs_humanization(
    attribute: dict[str, Any],
    concept_labels: dict[str, str],
) -> bool:
    if str(attribute.get("status") or "") not in {"proposed", ""}:
        return False
    if str(attribute.get("role") or "") == "foreign_key":
        return False
    concepts = [str(c).strip().lower() for c in attribute.get("concepts") or [] if str(c).strip()]
    if not concepts:
        return False
    concept_id = concepts[0]
    if concept_id in concept_labels and str(attribute.get("citation") or "") == "llm:humanized":
        return False
    if str(attribute.get("tagged_by") or "") == "llm" and concept_id in concept_labels:
        return False
    return True


def apply_entity_scoped_tags_to_attributes(
    attributes: list[dict[str, Any]],
    *,
    entity_names: set[str],
) -> int:
    """Tag columns using deterministic table+field entity-scoped concepts."""
    tagged_count = 0
    for attribute in attributes:
        if not isinstance(attribute, dict):
            continue
        entity = str(attribute.get("entity") or "").strip().lower()
        column = str(attribute.get("column") or "").strip()
        if not entity or not column or entity not in entity_names:
            continue
        if not _attribute_needs_tagging(attribute):
            continue
        concepts = resolve_entity_column_concepts(entity, column)
        if not concepts:
            continue
        attribute["concepts"] = concepts
        attribute["status"] = "proposed"
        attribute["citation"] = "derived:entity_column"
        attribute.pop("confidence", None)
        attribute.pop("tagged_by", None)
        attribute.pop("notes", None)
        tagged_count += 1
    return tagged_count


def _apply_fallback_labels(
    attributes: list[dict[str, Any]],
    *,
    entity_names: set[str],
    concept_labels: dict[str, str],
) -> int:
    """Use heuristic labels when LLM humanization is disabled."""
    labeled_count = 0
    for attribute in attributes:
        if not isinstance(attribute, dict):
            continue
        entity = str(attribute.get("entity") or "").strip().lower()
        column = str(attribute.get("column") or "").strip()
        if not entity or not column or entity not in entity_names:
            continue
        concepts = [str(c).strip().lower() for c in attribute.get("concepts") or [] if str(c).strip()]
        if not concepts:
            continue
        concept_id = concepts[0]
        if concept_id in concept_labels:
            continue
        label = entity_column_concept_label(entity, column)
        concept_labels[concept_id] = label
        attribute["notes"] = label
        attribute["citation"] = "derived:entity_column"
        labeled_count += 1
    return labeled_count


def apply_llm_tags_to_attributes(
    settings: DnaSettings,
    attributes: list[dict[str, Any]],
    *,
    entity_names: set[str],
    invoke_fn: InvokeFn | None = None,
    entity_context_by_name: dict[str, str] | None = None,
    concept_labels: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Assign stable entity-scoped concept ids, then humanize labels via LLM for every tagged column."""
    labels: dict[str, str] = {
        str(concept_id).strip().lower(): str(label).strip()
        for concept_id, label in (concept_labels or {}).items()
        if str(concept_id).strip() and str(label).strip()
    }
    deterministic_tagged = apply_entity_scoped_tags_to_attributes(
        attributes,
        entity_names=entity_names,
    )

    from meshflow.dna.semantic_source_profile import apply_latest_profile_tags_to_attributes, load_latest_source_profile

    profile = load_latest_source_profile(settings)
    reference_tagged = apply_latest_profile_tags_to_attributes(attributes, profile)
    if reference_tagged == 0:
        from meshflow.dna.semantic_source_reference import (
            apply_reference_tags_to_attributes,
            load_source_semantic_consensus,
        )

        consensus = load_source_semantic_consensus(settings)
        reference_tagged = apply_reference_tags_to_attributes(attributes, consensus)

    if not llm_tagging_enabled():
        fallback_labeled = _apply_fallback_labels(
            attributes,
            entity_names=entity_names,
            concept_labels=labels,
        )
        return {
            "tagged_count": deterministic_tagged,
            "humanized_count": fallback_labeled,
            "skipped_count": 0,
            "attempts": 0,
            "limit": 0,
            "reference_tagged": reference_tagged,
            "deterministic_tagged": deterministic_tagged,
            "concept_labels": labels,
            "reason": "llm_disabled",
        }

    limit = llm_tagging_limit()
    if limit <= 0:
        fallback_labeled = _apply_fallback_labels(
            attributes,
            entity_names=entity_names,
            concept_labels=labels,
        )
        return {
            "tagged_count": deterministic_tagged,
            "humanized_count": fallback_labeled,
            "skipped_count": 0,
            "attempts": 0,
            "limit": limit,
            "reference_tagged": reference_tagged,
            "deterministic_tagged": deterministic_tagged,
            "concept_labels": labels,
            "reason": "limit_zero",
        }

    from meshflow.dna.semantic_profiling import profile_entity_columns

    humanized_count = 0
    skipped_count = 0
    attempts = 0
    profiles_by_entity: dict[str, dict[str, dict[str, Any]]] = {}
    entity_contexts = entity_context_by_name or {}

    for attribute in attributes:
        if attempts >= limit:
            break
        if not isinstance(attribute, dict):
            continue
        if not _attribute_needs_humanization(attribute, labels):
            continue
        entity = str(attribute.get("entity") or "").strip().lower()
        column = str(attribute.get("column") or "").strip()
        if not entity or not column or entity not in entity_names:
            continue
        concepts = [str(c).strip().lower() for c in attribute.get("concepts") or [] if str(c).strip()]
        if not concepts:
            continue
        concept_id = concepts[0]

        if entity not in profiles_by_entity:
            profiles_by_entity[entity] = profile_entity_columns(settings, entity)
        column_profile = profiles_by_entity[entity].get(column)
        if not column_profile:
            fallback_label = entity_column_concept_label(entity, column)
            labels[concept_id] = fallback_label
            attribute["notes"] = fallback_label
            attribute["citation"] = "derived:entity_column"
            skipped_count += 1
            continue

        attempts += 1
        try:
            suggestion = humanize_column_tag(
                settings,
                entity=entity,
                column=column,
                concept_id=concept_id,
                profile=column_profile,
                invoke_fn=invoke_fn,
                entity_context=entity_contexts.get(entity, ""),
            )
        except Exception as exc:  # noqa: BLE001 — continue tagging remaining columns
            skipped_count += 1
            fallback_label = entity_column_concept_label(entity, column)
            labels[concept_id] = fallback_label
            attribute["notes"] = f"{fallback_label} (LLM humanization failed: {exc})"
            attribute["citation"] = "derived:entity_column"
            continue

        labels[concept_id] = suggestion.label
        attribute["tagged_by"] = "llm"
        attribute["citation"] = "llm:humanized"
        attribute["notes"] = suggestion.notes or suggestion.label
        if suggestion.role:
            attribute["role"] = suggestion.role
        humanized_count += 1

    return {
        "tagged_count": deterministic_tagged,
        "humanized_count": humanized_count,
        "skipped_count": skipped_count,
        "attempts": attempts,
        "limit": limit,
        "reference_tagged": reference_tagged,
        "deterministic_tagged": deterministic_tagged,
        "concept_labels": labels,
    }
