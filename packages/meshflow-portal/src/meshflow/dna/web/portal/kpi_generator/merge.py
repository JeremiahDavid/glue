"""Merge per-KPI silver contribution SQL into one canonical enhancement."""

from __future__ import annotations

import json
import re
from typing import Any, Callable

from meshflow.dna.settings import DnaSettings
from meshflow.dna.silver_enhancement import (
    assert_preserves_silver_grain,
    extract_new_column_aliases,
    try_deterministic_merge,
)
from meshflow.dna.web.portal.kpi_generator.sql_format import format_kpi_sql

_JSON_FENCE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)
DEFAULT_BEDROCK_MODEL_ID = "us.anthropic.claude-haiku-4-5-20251001-v1:0"


def merge_silver_enhancement(
    settings: DnaSettings,
    *,
    target_entity: str,
    contributions: dict[str, str],
    primary_key: str = "id",
    validate_sql: Callable[[str], None] | None = None,
) -> str:
    """Produce one canonical silver enhancement SELECT from KPI contributions."""
    if not contributions:
        raise ValueError(f"No contributions to merge for {target_entity!r}")

    for kpi_id, body in contributions.items():
        if not body.strip():
            raise ValueError(f"Contribution {kpi_id!r} has no SQL")
        assert_preserves_silver_grain(body, primary_key=primary_key)

    merged = try_deterministic_merge(
        target_entity=target_entity,
        source=settings.source,
        contributions=contributions,
    )
    if merged is None:
        merged = _merge_with_bedrock(
            settings,
            target_entity=target_entity,
            contributions=contributions,
            primary_key=primary_key,
        )

    merged = format_kpi_sql(merged)
    assert_preserves_silver_grain(merged, primary_key=primary_key)
    if validate_sql is not None:
        validate_sql(merged)

    expected_aliases: set[str] = set()
    for body in contributions.values():
        expected_aliases.update(extract_new_column_aliases(body))
    if expected_aliases:
        merged_lower = merged.lower()
        missing = [alias for alias in sorted(expected_aliases) if alias.lower() not in merged_lower]
        if missing:
            raise ValueError(
                "Merged silver enhancement is missing contribution columns: "
                + ", ".join(missing)
            )
    return merged


def _merge_with_bedrock(
    settings: DnaSettings,
    *,
    target_entity: str,
    contributions: dict[str, str],
    primary_key: str,
) -> str:
    from meshflow.dna.source_docs.reference import normalize_reference_source

    source = normalize_reference_source(settings.source)
    base_table = f"silver_{source}_{target_entity.strip().lower()}"
    contrib_lines = []
    for kpi_id, body in sorted(contributions.items()):
        contrib_lines.append(f"### {kpi_id}\n{body.strip()}")

    system = (
        "You merge multiple Athena SQL contribution queries into ONE silver enhancement SELECT. "
        "Rules (strict):\n"
        f"- Base table: {base_table}\n"
        f"- Preserve row grain: exactly one row per {primary_key}\n"
        "- Include all base entity columns and every new column from each contribution\n"
        "- Do NOT use GROUP BY or SELECT DISTINCT\n"
        "- Use correlated subqueries for lookups when needed\n"
        "- Return ONLY JSON: {\"sql\": \"...\"}\n"
    )
    user = (
        f"Merge these contributions for silver entity {target_entity!r}:\n\n"
        + "\n\n".join(contrib_lines)
    )

    import boto3

    model_id = __import__("os").environ.get("MESHFLOW_BEDROCK_MODEL_ID", DEFAULT_BEDROCK_MODEL_ID)
    client = boto3.client("bedrock-runtime")
    response = client.converse(
        modelId=model_id,
        system=[{"text": system}],
        messages=[{"role": "user", "content": [{"text": user}]}],
        inferenceConfig={"maxTokens": 4096, "temperature": 0.1},
    )
    raw_text = _extract_converse_text(response)
    payload = _parse_json_object(raw_text)
    sql = str(payload.get("sql") or "").strip()
    if not sql:
        raise ValueError("Bedrock merge did not return SQL")
    return sql


def _extract_converse_text(response: dict[str, Any]) -> str:
    parts: list[str] = []
    for block in ((response.get("output") or {}).get("message") or {}).get("content") or []:
        if isinstance(block, dict) and block.get("text"):
            parts.append(str(block["text"]))
    return "\n".join(parts).strip()


def _parse_json_object(text: str) -> dict[str, Any]:
    raw = text.strip()
    match = _JSON_FENCE.search(raw)
    if match:
        raw = match.group(1).strip()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("Model did not return JSON") from None
        payload = json.loads(raw[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError("Model JSON must be an object")
    return payload
