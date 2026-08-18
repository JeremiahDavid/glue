"""Bedrock semantic interpretation of profiled spreadsheet tables."""

from __future__ import annotations

import json
import os
import re
from typing import Any, Callable

from botocore.config import Config

INTERPRET_KIND = "spreadsheet_engine_report"
DEFAULT_BEDROCK_MODEL_ID = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
_JSON_FENCE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)

_SYSTEM_PROMPT = """You analyze spreadsheet table profiles for a data platform.
Return strict JSON only (no markdown) with this shape:
{
  "tables": [
    {
      "table_id": "t0",
      "entity_name": "snake_case_entity",
      "purpose": "one sentence business purpose",
      "grain": "one row per ...",
      "confidence": 0.0-1.0,
      "schema": [
        {
          "name": "column_name",
          "type": "string|number|date|datetime|boolean|currency|email|unknown",
          "description": "business meaning",
          "nullable": true,
          "is_key": false,
          "is_foreign_key": false,
          "references": null
        }
      ],
      "relationships": [
        {"to_entity": "other_entity", "via_column": "col", "confidence": 0.0-1.0}
      ],
      "notes": ["optional caveats"]
    }
  ]
}
Use profiling stats and samples. Prefer snake_case entity and column names."""


def _default_invoke(system: str, user_message: str) -> str:
    import boto3

    model_id = os.getenv("MESHFLOW_BEDROCK_MODEL_ID", DEFAULT_BEDROCK_MODEL_ID).strip()
    region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "us-east-2"
    client = boto3.client(
        "bedrock-runtime",
        region_name=region,
        config=Config(connect_timeout=30, read_timeout=120, retries={"max_attempts": 2}),
    )
    response = client.converse(
        modelId=model_id,
        system=[{"text": system}],
        messages=[{"role": "user", "content": [{"text": user_message}]}],
        inferenceConfig={"maxTokens": 4096, "temperature": 0.0},
    )
    content = response.get("output", {}).get("message", {}).get("content") or []
    parts = [block.get("text", "") for block in content if isinstance(block, dict)]
    return "\n".join(parts).strip()


def _extract_json(text: str) -> dict[str, Any]:
    stripped = text.strip()
    match = _JSON_FENCE.search(stripped)
    if match:
        stripped = match.group(1).strip()
    payload = json.loads(stripped)
    if not isinstance(payload, dict):
        raise ValueError("Bedrock response must be a JSON object")
    return payload


def _heuristic_table(
    *,
    table_id: str,
    profile: dict[str, Any],
    parse_table: dict[str, Any] | None,
) -> dict[str, Any]:
    sheet = str(profile.get("sheet") or parse_table.get("sheet") if parse_table else "")
    headers = [str(col.get("name") or "") for col in profile.get("columns") or []]
    entity_name = re.sub(r"[^a-z0-9]+", "_", sheet.strip().lower()).strip("_") or table_id
    schema = []
    for col in profile.get("columns") or []:
        if not isinstance(col, dict):
            continue
        schema.append(
            {
                "name": col.get("name"),
                "type": col.get("inferred_type") or "unknown",
                "description": f"Column {col.get('name')}",
                "nullable": float(col.get("null_rate") or 0) > 0,
                "is_key": bool(col.get("likely_key")),
                "is_foreign_key": False,
                "references": None,
            }
        )
    grain = "one row per record"
    if profile.get("key_candidates"):
        grain = f"one row per {profile['key_candidates'][0]}"
    return {
        "table_id": table_id,
        "entity_name": entity_name,
        "purpose": f"Data extracted from sheet {sheet or 'unknown'}",
        "grain": grain,
        "confidence": 0.35,
        "schema": schema,
        "relationships": [],
        "notes": ["Heuristic fallback — Bedrock unavailable or returned invalid JSON."],
    }


def interpret_tables(
    parse_payload: dict[str, Any],
    profile_payload: dict[str, Any],
    *,
    invoke: Callable[[str, str], str] | None = None,
) -> dict[str, Any]:
    """Produce semantic proposals for each profiled table."""
    parse_tables = {
        str(t.get("table_id")): t
        for t in (parse_payload.get("tables") or [])
        if isinstance(t, dict) and t.get("table_id")
    }
    profile_tables_list = [
        t for t in (profile_payload.get("tables") or []) if isinstance(t, dict)
    ]
    user_payload = {
        "filename": parse_payload.get("filename"),
        "tables": [
            {
                "table_id": table.get("table_id"),
                "sheet": table.get("sheet"),
                "profiling": table,
                "headers": (parse_tables.get(str(table.get("table_id"))) or {}).get("headers"),
                "sample_rows": (parse_tables.get(str(table.get("table_id"))) or {}).get(
                    "sample_rows"
                ),
            }
            for table in profile_tables_list
        ],
    }
    interpreted: list[dict[str, Any]] = []
    llm_tables: dict[str, dict[str, Any]] = {}
    if invoke is not False:
        try:
            invoke_fn = invoke or _default_invoke
            raw = invoke_fn(_SYSTEM_PROMPT, json.dumps(user_payload, default=str))
            parsed = _extract_json(raw)
            for item in parsed.get("tables") or []:
                if isinstance(item, dict) and item.get("table_id"):
                    llm_tables[str(item["table_id"])] = item
        except Exception:  # noqa: BLE001
            llm_tables = {}

    for profile in profile_tables_list:
        table_id = str(profile.get("table_id") or "")
        parse_table = parse_tables.get(table_id)
        proposal = llm_tables.get(table_id)
        if not proposal:
            proposal = _heuristic_table(
                table_id=table_id,
                profile=profile,
                parse_table=parse_table,
            )
        interpreted.append(
            {
                **proposal,
                "status": "pending_review",
                "source": {
                    "sheet": profile.get("sheet") or (parse_table or {}).get("sheet"),
                    "header_row": (parse_table or {}).get("header_row"),
                    "data_start_row": (parse_table or {}).get("data_start_row"),
                    "data_end_row": (parse_table or {}).get("data_end_row"),
                    "row_count": profile.get("row_count"),
                    "column_count": profile.get("column_count"),
                },
                "profiling": profile,
            }
        )

    return {
        "kind": INTERPRET_KIND,
        "filename": parse_payload.get("filename"),
        "table_count": len(interpreted),
        "tables": interpreted,
    }
