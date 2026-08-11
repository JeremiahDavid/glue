"""LLM-assisted column concept tagging for semantic model init."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any, Callable

from meshflow.dna.field_semantics import (
    coerce_entity_column_concepts,
    entity_column_concept_id,
    entity_column_concept_label,
    entity_singular_label,
    load_operational_concept_catalog,
)
from meshflow.dna.semantic_doc_retrieval import format_retrieved_chunks, retrieve_semantic_docs
from meshflow.dna.semantic_profiling import profile_summary_text
from meshflow.dna.settings import DnaSettings

DEFAULT_BEDROCK_MODEL_ID = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
_MIN_CONFIDENCE = 0.55
_JSON_BLOCK_RE = re.compile(r"\{[\s\S]*\}")

InvokeFn = Callable[[str, str], str]


@dataclass(frozen=True)
class ColumnTagSuggestion:
    concepts: list[str]
    confidence: float
    notes: str
    citation: str
    role: str


def _catalog_concept_ids() -> list[str]:
    catalog = load_operational_concept_catalog()
    return sorted(
        {
            str(item.get("id") or "").strip().lower()
            for item in catalog.get("concepts") or []
            if isinstance(item, dict) and str(item.get("id") or "").strip()
        }
    )


def _concept_catalog_excerpt(*, limit: int = 80) -> str:
    catalog = load_operational_concept_catalog()
    lines: list[str] = []
    for item in catalog.get("concepts") or []:
        if not isinstance(item, dict):
            continue
        concept_id = str(item.get("id") or "").strip()
        if not concept_id:
            continue
        label = str(item.get("label") or concept_id)
        category = str(item.get("category") or "")
        lines.append(f"- {concept_id}: {label} ({category})")
        if len(lines) >= limit:
            break
    return "\n".join(lines)


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


def _normalize_suggestion(
    payload: dict[str, Any],
    *,
    allowed: set[str],
    entity_scoped_id: str = "",
) -> ColumnTagSuggestion:
    allowed_ids = set(allowed)
    if entity_scoped_id:
        allowed_ids.add(entity_scoped_id)
    concepts = [
        str(concept).strip().lower()
        for concept in payload.get("concepts") or []
        if str(concept).strip()
    ]
    concepts = [concept for concept in concepts if concept in allowed_ids][:3]
    confidence = float(payload.get("confidence") or 0.0)
    notes = str(payload.get("notes") or "").strip()
    citation = str(payload.get("citation") or "").strip()
    role = str(payload.get("role") or "").strip().lower()
    return ColumnTagSuggestion(
        concepts=concepts,
        confidence=max(0.0, min(confidence, 1.0)),
        notes=notes,
        citation=citation,
        role=role,
    )


def _default_invoke(system: str, user_message: str) -> str:
    import boto3
    from botocore.config import Config

    model_id = os.getenv("MESHFLOW_BEDROCK_MODEL_ID", DEFAULT_BEDROCK_MODEL_ID).strip()
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


def suggest_column_tags(
    settings: DnaSettings,
    *,
    entity: str,
    profile: dict[str, Any],
    invoke_fn: InvokeFn | None = None,
    rag_query: str | None = None,
    entity_context: str = "",
) -> ColumnTagSuggestion:
    """Suggest operational concept tags for one silver column."""
    allowed = set(_catalog_concept_ids())
    entity_name = entity.strip().lower()
    column_name = str(profile.get("column") or "").strip()
    entity_scoped_id = entity_column_concept_id(entity_name, column_name) if entity_name and column_name else ""
    query = rag_query or (
        f"{entity_name} {column_name} {profile.get('inferred_dtype')} "
        f"{' '.join(profile.get('sample_values') or [])} {entity_context}"
    )
    retrieved = retrieve_semantic_docs(settings, query, top_k=3)
    docs = format_retrieved_chunks(retrieved, max_chars=6000)
    entity_label = entity_singular_label(entity_name) if entity_name else entity_name
    default_label = entity_column_concept_label(entity_name, column_name) if entity_name and column_name else ""
    system = f"""You tag silver warehouse columns with operational concept ids for a semantic model.

Return JSON only:
{{"concepts": ["concept_id"], "confidence": 0.0, "notes": "short reason", "citation": "doc section", "role": "dimension|measure|foreign_key|date|identifier|status"}}

Rules:
- Every column is tagged in the context of its silver table. purchase_invoices.orderNumber is NOT the same as sales_orders.number.
- Always use the entity-scoped concept id for this table+column: {entity_scoped_id or "(n/a)"} (human meaning: {default_label or "n/a"}).
- Do not reuse shared catalog ids (posting_date, document_number, customer_number, document_status, revenue_amount, etc.).
- Use exactly one concept id when confident; otherwise return an empty concepts list.
- confidence must be between 0 and 1.
"""
    user_message = f"""Tag this column:

Silver table: {entity_name} ({entity_label})
Table context: {entity_context or "(no table description available)"}
Default entity-scoped concept id: {entity_scoped_id or "(n/a)"}
Default human label: {default_label or "(n/a)"}

{profile_summary_text(profile)}

Retrieved documentation:
{docs or "(no matching documentation chunks)"}
"""
    invoke = invoke_fn or _default_invoke
    raw = invoke(system, user_message)
    suggestion = _normalize_suggestion(
        _parse_suggestion_payload(raw),
        allowed=allowed,
        entity_scoped_id=entity_scoped_id,
    )
    coerced = coerce_entity_column_concepts(
        entity_name,
        column_name,
        suggestion.concepts,
        hint_role=suggestion.role,
    )
    if coerced:
        suggestion = ColumnTagSuggestion(
            concepts=coerced,
            confidence=suggestion.confidence,
            notes=suggestion.notes or f"{default_label} ({entity_scoped_id})",
            citation=suggestion.citation,
            role=suggestion.role,
        )
    elif entity_scoped_id and suggestion.confidence >= _MIN_CONFIDENCE:
        suggestion = ColumnTagSuggestion(
            concepts=[entity_scoped_id],
            confidence=max(suggestion.confidence, _MIN_CONFIDENCE),
            notes=suggestion.notes or f"{default_label} ({entity_scoped_id})",
            citation=suggestion.citation,
            role=suggestion.role,
        )
    if suggestion.confidence < _MIN_CONFIDENCE:
        return ColumnTagSuggestion(
            concepts=[],
            confidence=suggestion.confidence,
            notes=suggestion.notes or "Low confidence — left untagged for human review",
            citation=suggestion.citation,
            role="",
        )
    return suggestion


def llm_tagging_enabled() -> bool:
    raw = os.getenv("MESHFLOW_SEMANTIC_LLM_TAGGING", "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def llm_tagging_limit() -> int:
    raw = os.getenv("MESHFLOW_SEMANTIC_LLM_TAG_LIMIT", "40").strip()
    try:
        return max(0, int(raw))
    except ValueError:
        return 40


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


def apply_llm_tags_to_attributes(
    settings: DnaSettings,
    attributes: list[dict[str, Any]],
    *,
    entity_names: set[str],
    invoke_fn: InvokeFn | None = None,
    entity_context_by_name: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Fill proposed concepts for untagged columns using LLM + retrieved docs."""
    if not llm_tagging_enabled():
        return {"tagged_count": 0, "skipped_count": 0, "reason": "disabled"}

    limit = llm_tagging_limit()
    if limit <= 0:
        return {"tagged_count": 0, "skipped_count": 0, "reason": "limit_zero"}

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

    from meshflow.dna.semantic_profiling import profile_entity_columns

    tagged_count = 0
    skipped_count = 0
    attempts = 0
    profiles_by_entity: dict[str, dict[str, dict[str, Any]]] = {}
    entity_contexts = entity_context_by_name or {}

    for attribute in attributes:
        if attempts >= limit:
            break
        if not isinstance(attribute, dict):
            continue
        if attribute.get("concepts"):
            continue
        if str(attribute.get("status") or "") not in {"proposed", ""}:
            continue
        entity = str(attribute.get("entity") or "").strip().lower()
        column = str(attribute.get("column") or "").strip()
        if not entity or not column or entity not in entity_names:
            continue

        if entity not in profiles_by_entity:
            profiles_by_entity[entity] = profile_entity_columns(settings, entity)
        profile = profiles_by_entity[entity].get(column)
        if not profile:
            skipped_count += 1
            continue

        attempts += 1
        try:
            suggestion = suggest_column_tags(
                settings,
                entity=entity,
                profile=profile,
                invoke_fn=invoke_fn,
                entity_context=entity_contexts.get(entity, ""),
            )
        except Exception as exc:  # noqa: BLE001 — continue tagging remaining columns
            skipped_count += 1
            attribute["notes"] = f"LLM tagging failed: {exc}"
            continue
        if not suggestion.concepts:
            skipped_count += 1
            if suggestion.notes:
                attribute["notes"] = suggestion.notes
            continue

        attribute["concepts"] = suggestion.concepts
        attribute["status"] = "proposed"
        attribute["confidence"] = suggestion.confidence
        attribute["tagged_by"] = "llm"
        if suggestion.notes:
            attribute["notes"] = suggestion.notes
        if suggestion.citation:
            attribute["citation"] = suggestion.citation
        if suggestion.role:
            attribute["role"] = suggestion.role
        tagged_count += 1

    return {
        "tagged_count": tagged_count,
        "skipped_count": skipped_count,
        "attempts": attempts,
        "limit": limit,
        "reference_tagged": reference_tagged,
    }
