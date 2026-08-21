"""Knowledge context for semantic assistant (source packs + tenant model)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from meshflow.dna.semantic_model import (
    build_assistant_semantic_model_context,
    load_semantic_model_draft,
    load_source_semantic_pack,
)
from meshflow.dna.settings import DnaSettings
from meshflow.repo_paths import find_project_root


def _dbc_data_model_excerpt(*, max_chars: int = 12000) -> str:
    root = find_project_root()
    path = root / "docs" / "dbc-data-model.md"
    if not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8")
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n\n[truncated]"


def build_semantic_knowledge_context(settings: DnaSettings) -> dict[str, Any]:
    """RAG-style context bundle for the semantic builder assistant."""
    source = settings.source.strip().lower()
    source_pack = load_source_semantic_pack(source) or {}
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

    return {
        "source": source,
        "source_pack_summary": {
            "description": source_pack.get("description"),
            "entity_count": len(source_pack.get("entities") or []),
            "relationship_count": len(source_pack.get("relationships") or []),
        },
        "source_pack_yaml": yaml.safe_dump(source_pack, sort_keys=False, allow_unicode=True)[:16000],
        "semantic_model_summary": assistant,
        "tagged_attributes_sample": tagged_attributes,
        "dbc_data_model_excerpt": _dbc_data_model_excerpt(),
    }


def semantic_assistant_system_prompt(settings: DnaSettings) -> str:
    ctx = build_semantic_knowledge_context(settings)
    return f"""You are the Meshflow Semantic Builder assistant for connector {ctx["source"]!r}.

You help business users understand and refine their source semantic model: entities, joins, column tags, and open questions.
You do NOT invent financial amounts. You do NOT modify DNA KPI logic or reporting layouts.

Source semantic starter pack (documentation-derived):
```yaml
{ctx["source_pack_yaml"]}
```

Current tenant semantic model summary:
```json
{json.dumps(ctx["semantic_model_summary"], indent=2)}
```

Business Central data model reference excerpt:
```
{ctx["dbc_data_model_excerpt"]}
```

Rules:
- Answer in plain language for business users.
- When suggesting column tags, use operational concept ids from the starter pack (e.g. revenue_amount, customer_id).
- When explaining joins, cite APV2 / document-chain conventions when relevant.
- If unsure, recommend adding an open question to the semantic model rather than guessing.
- Keep replies concise (2–5 sentences) unless the user asks for detail.
- Do not output full YAML files; describe changes clearly.
"""
