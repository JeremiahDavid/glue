"""Knowledge context for semantic assistant (source packs + tenant model)."""

from __future__ import annotations

import json
from typing import Any

import yaml

from meshflow.dna.semantic_doc_retrieval import format_retrieved_chunks, retrieve_semantic_docs
from meshflow.dna.semantic_knowledge_base import (
    load_merged_semantic_hints,
    load_semantic_knowledge_corpus,
)
from meshflow.dna.semantic_model import (
    build_assistant_semantic_model_context,
    load_semantic_model_draft,
)
from meshflow.dna.settings import DnaSettings


def build_semantic_knowledge_context(
    settings: DnaSettings,
    *,
    query: str = "",
    top_k: int = 4,
) -> dict[str, Any]:
    """RAG context bundle for the semantic builder assistant."""
    source = settings.source.strip().lower()
    merged_hints = load_merged_semantic_hints(settings)
    model = load_semantic_model_draft(settings)
    assistant = build_assistant_semantic_model_context(settings)

    tagged_attributes = [
        {
            "entity": item.get("entity"),
            "column": item.get("column"),
            "concepts": item.get("concepts") or [],
            "status": item.get("status"),
            "role": item.get("role"),
        }
        for item in model.get("attributes") or []
        if isinstance(item, dict) and item.get("concepts")
    ][:200]

    retrieval_query = query.strip() or (
        f"{source} semantic model entities joins column tags "
        f"{assistant.get('coverage', {}).get('tagged_column_count', 0)}"
    )
    retrieved = retrieve_semantic_docs(settings, retrieval_query, top_k=top_k)
    retrieved_docs = [
        {
            "title": item.chunk.title,
            "source": item.chunk.source,
            "score": round(item.score, 4),
            "text": item.chunk.text[:2000],
        }
        for item in retrieved
    ]

    return {
        "source": source,
        "knowledge_base": {
            "description": merged_hints.get("description"),
            "hint_entity_count": len(merged_hints.get("entities") or []),
            "hint_relationship_count": len(merged_hints.get("relationships") or []),
            "tenant_doc_chunks": sum(
                1 for chunk in load_semantic_knowledge_corpus(settings) if chunk.source.startswith("tenant:")
            ),
        },
        "semantic_hints_yaml": yaml.safe_dump(merged_hints, sort_keys=False, allow_unicode=True)[:16000],
        "semantic_model_summary": assistant,
        "tagged_attributes_sample": tagged_attributes,
        "retrieval_query": retrieval_query,
        "retrieved_docs": retrieved_docs,
        "retrieved_docs_text": format_retrieved_chunks(retrieved),
    }


def semantic_assistant_system_prompt(settings: DnaSettings, *, query: str = "") -> str:
    ctx = build_semantic_knowledge_context(settings, query=query)
    docs_block = ctx.get("retrieved_docs_text") or "(no documentation chunks retrieved)"
    return f"""You are the Meshflow Semantic Builder assistant for connector {ctx["source"]!r}.

You help business users understand and refine their source semantic model: entities, joins, column tags, and open questions.
You do NOT invent financial amounts. You do NOT modify DNA KPI logic or reporting layouts.

Source semantic knowledge (connector standard + client overrides):
```yaml
{ctx["semantic_hints_yaml"]}
```

Current tenant semantic model summary:
```json
{json.dumps(ctx["semantic_model_summary"], indent=2)}
```

Retrieved documentation (embedding-ranked for the user's question):
```
{docs_block}
```

Rules:
- Answer in plain language for business users.
- When suggesting column tags, use operational concept ids from the catalog (e.g. revenue_amount, customer_id).
- When explaining joins, cite APV2 / document-chain conventions from retrieved docs when relevant.
- If unsure, recommend adding an open question to the semantic model rather than guessing.
- Keep replies concise (2–5 sentences) unless the user asks for detail.
- Do not output full YAML files; describe changes clearly.
"""
