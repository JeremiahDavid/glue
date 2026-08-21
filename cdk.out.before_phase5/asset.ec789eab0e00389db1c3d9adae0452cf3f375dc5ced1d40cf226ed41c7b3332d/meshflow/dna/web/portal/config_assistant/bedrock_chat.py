"""Bedrock-backed config assistant with client-bucket-only tools."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any, Callable

import yaml

from meshflow.dna.settings import DnaSettings
from meshflow.dna.store import read_json_artifact
from meshflow.dna.web.portal.config_assistant.gold_bindings import build_reporting_binding_catalog
from meshflow.dna.web.portal.config_assistant.field_semantics_context import (
    build_field_semantics_assistant_context,
)
from meshflow.dna.web.portal.config_assistant.reporting_context import build_reporting_assistant_context
from meshflow.dna.reporting import load_production_reporting
from meshflow.dna.workflow import load_production_pack
from meshflow.storage.paths import governance_prefix, gold_dna_prefix

# Cost-effective active model (Haiku 4.5). Sonnet 4 base IDs are legacy.
DEFAULT_BEDROCK_MODEL_ID = "us.anthropic.claude-haiku-4-5-20251001-v1:0"

TOOL_SPECS = [
    {
        "toolSpec": {
            "name": "get_pinned_dna",
            "description": "Load the pinned production DNA config YAML for this client only.",
            "inputSchema": {"json": {"type": "object", "properties": {}, "additionalProperties": False}},
        }
    },
    {
        "toolSpec": {
            "name": "get_pinned_reporting",
            "description": "Load the pinned production reporting config YAML for this client only.",
            "inputSchema": {"json": {"type": "object", "properties": {}, "additionalProperties": False}},
        }
    },
    {
        "toolSpec": {
            "name": "list_governance_keys",
            "description": (
                "List object keys under this client's governance/ prefix only. "
                "Do not request other buckets or prefixes outside governance/."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "prefix": {
                            "type": "string",
                            "description": "Optional sub-prefix under governance/ (no bucket name).",
                        }
                    },
                    "additionalProperties": False,
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "get_gold_manifest",
            "description": "Read gold/dna/manifest.json from this client's bucket only.",
            "inputSchema": {"json": {"type": "object", "properties": {}, "additionalProperties": False}},
        }
    },
    {
        "toolSpec": {
            "name": "get_gold_binding_catalog",
            "description": (
                "List certified gold outputs with suggested reporting table/chart/section bindings "
                "derived from the pinned DNA pack schema."
            ),
            "inputSchema": {"json": {"type": "object", "properties": {}, "additionalProperties": False}},
        }
    },
    {
        "toolSpec": {
            "name": "get_reporting_layout_cookbook",
            "description": (
                "Reporting pack layout reference: section layouts, dim_join for ranked tables, "
                "columns for detail tables, and KPI binding hints from the pinned DNA pack."
            ),
            "inputSchema": {"json": {"type": "object", "properties": {}, "additionalProperties": False}},
        }
    },
    {
        "toolSpec": {
            "name": "get_field_semantics",
            "description": (
                "Published silver column to operational concept mappings for this client. "
                "Use when the user refers to business concepts (customer, cost, revenue, freight, etc.)."
            ),
            "inputSchema": {"json": {"type": "object", "properties": {}, "additionalProperties": False}},
        }
    },
]


def _assert_client_relative_key(key: str) -> str:
    cleaned = key.strip().lstrip("/")
    if not cleaned or ".." in cleaned.split("/"):
        raise ValueError(f"Invalid key: {key!r}")
    if cleaned.startswith("s3://") or "://" in cleaned:
        raise ValueError("Cross-bucket or absolute S3 URIs are not allowed")
    if cleaned.startswith("governance/") or cleaned == "governance":
        return cleaned
    if cleaned.startswith("gold/dna/") or cleaned == "gold/dna/manifest.json":
        return cleaned
    raise ValueError("Only governance/ and gold/dna/ keys in the client bucket are allowed")


def system_prompt(
    settings: DnaSettings,
    *,
    base_version: str,
    next_version: str,
    dna_version: str | None = None,
    reporting_version: str | None = None,
    next_dna_version: str | None = None,
    next_reporting_version: str | None = None,
) -> str:
    dna_base = dna_version or base_version
    reporting_base = reporting_version or base_version
    dna_next = next_dna_version or next_version
    reporting_next = next_reporting_version or next_version
    try:
        catalog = build_reporting_binding_catalog(settings)
        catalog_json = json.dumps(catalog, indent=2)[:12000]
    except Exception:  # noqa: BLE001 — catalog is advisory; do not block the assistant
        catalog_json = "(catalog unavailable — call get_gold_binding_catalog if needed)"
    try:
        reporting_ctx = build_reporting_assistant_context(settings)
        cookbook = str(reporting_ctx.get("layout_cookbook") or "")
        kpi_hints_json = json.dumps(reporting_ctx.get("kpi_binding_hints") or [], indent=2)[:6000]
    except Exception:  # noqa: BLE001
        cookbook = "(call get_reporting_layout_cookbook if needed)"
        kpi_hints_json = "[]"
    try:
        semantics_ctx = build_field_semantics_assistant_context(settings)
        semantics_json = json.dumps(semantics_ctx, indent=2)[:12000]
    except Exception:  # noqa: BLE001
        semantics_json = "(call get_field_semantics if needed)"
    return f"""You are the HiveFlowAI Config Assistant for a single client portal.

Company: {settings.company}
Client data bucket: {settings.s3_bucket or "(local data_dir only)"}
DNA pack id (must preserve): {settings.dna_config_id}
Reporting pack id (must preserve): {settings.reporting_config_id}
Pinned DNA version: {dna_base} → propose {dna_next} only if DNA changes
Pinned reporting version: {reporting_base} → propose {reporting_next} only if reporting changes

Gold output binding catalog (use suggested_table / suggested_chart / suggested_section when adding pages):
```json
{catalog_json}
```

Reporting layout cookbook (how to edit portal pages, sections, tables, and charts):
```
{cookbook}
```

KPI binding hints by gold output (for kpi_grid and compare_kpi_grid sections):
```json
{kpi_hints_json}
```

Published field semantics (silver column → operational business concepts):
```json
{semantics_json}
```

Rules:
- You may ONLY read this client's bucket via the provided tools. Never invent or request other bucket names.
- The current DNA and reporting YAML are already included in the user message — do NOT call get_pinned_dna or get_pinned_reporting unless those copies are missing.
- Edit only DNA definition pack YAML and reporting pack YAML.
- Preserve pack_id fields exactly as given above.
- Change ONLY the pack(s) the user asked about. Omit the other pack from the JSON entirely.
- When including a pack, set its version field to the matching next version above.
- Do not invent financial amounts or gold metric values.
- When adding reporting pages, tables, charts, or sections, prefer bindings from the gold catalog above.
- When the user refers to business concepts (customer, cost, revenue, freight, etc.), resolve columns using published field semantics before proposing YAML.
- Follow the reporting layout cookbook for structure — ranked_table uses dim_join (not columns) for name labels.
- Proposed reporting YAML must validate against the reporting pack schema before it can be proposed (valid layouts, required table/chart fields, dim_join shape). Invalid reporting YAML is rejected and will not appear in the proposal.
- Preserve source_output ids exactly as listed in the catalog.
- Set top-level include_chart_catalog to true only when the user explicitly wants the developer chart catalog page.
- Prefer minimal, correct YAML changes that match the user's request.
- Your visible chat reply must be 1–3 short sentences. Never paste YAML or JSON into the visible reply.
- Put machine-readable updates ONLY inside the fenced JSON block at the end.

When you are ready to propose file updates, write a short human summary, then end with a single fenced JSON block:
```json
{{
  "summary": "short description of changes",
  "dna_yaml": "full DNA YAML document as a string (omit key if DNA unchanged)",
  "reporting_yaml": "full reporting YAML document as a string (omit key if reporting unchanged)"
}}
```
Include at least one of dna_yaml or reporting_yaml. Omit any pack you did not change.
"""


def run_tool(settings: DnaSettings, name: str, tool_input: dict[str, Any] | None = None) -> str:
    tool_input = tool_input or {}
    if "bucket" in tool_input or "Bucket" in tool_input:
        raise ValueError("Tool arguments must not include a bucket name")

    if name == "get_pinned_dna":
        pack = load_production_pack(settings)
        return yaml.safe_dump(pack.to_dict(), sort_keys=False, allow_unicode=True)

    if name == "get_pinned_reporting":
        reporting = load_production_reporting(settings)
        return yaml.safe_dump(reporting, sort_keys=False, allow_unicode=True)

    if name == "get_gold_manifest":
        key = _assert_client_relative_key(f"{gold_dna_prefix()}/manifest.json")
        payload = read_json_artifact(settings, key)
        return json.dumps(payload or {}, indent=2)

    if name == "get_gold_binding_catalog":
        return json.dumps(build_reporting_binding_catalog(settings), indent=2)

    if name == "get_reporting_layout_cookbook":
        return json.dumps(build_reporting_assistant_context(settings), indent=2)

    if name == "get_field_semantics":
        return json.dumps(build_field_semantics_assistant_context(settings), indent=2)

    if name == "list_governance_keys":
        sub = str(tool_input.get("prefix") or "").strip().lstrip("/")
        if sub.startswith("governance/"):
            prefix = _assert_client_relative_key(sub)
        elif sub:
            prefix = _assert_client_relative_key(f"{governance_prefix()}/{sub}")
        else:
            prefix = governance_prefix() + "/"
        keys = _list_keys(settings, prefix)
        return json.dumps(keys[:200], indent=2)

    raise ValueError(f"Unknown tool {name!r}")


def _list_keys(settings: DnaSettings, prefix: str) -> list[str]:
    if settings.s3_bucket:
        import boto3

        client = boto3.client("s3")
        keys: list[str] = []
        paginator = client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=settings.s3_bucket, Prefix=prefix):
            for obj in page.get("Contents") or []:
                key = str(obj.get("Key") or "")
                if key:
                    keys.append(key)
        return keys

    from meshflow.storage.paths import prefix_path

    root = prefix_path(settings.data_dir, prefix.rstrip("/"))
    if not root.exists():
        return []
    keys = []
    if root.is_file():
        return [prefix.rstrip("/")]
    for path in root.rglob("*"):
        if path.is_file():
            rel = path.relative_to(settings.data_dir).as_posix()
            keys.append(rel)
    return sorted(keys)


_JSON_BLOCK_RE = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)


def extract_proposal_payload(assistant_text: str) -> dict[str, Any] | None:
    match = _JSON_BLOCK_RE.search(assistant_text or "")
    if not match:
        return None
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    dna_raw = payload.get("dna_yaml")
    reporting_raw = payload.get("reporting_yaml")
    dna_yaml = dna_raw.strip() if isinstance(dna_raw, str) and dna_raw.strip() else None
    reporting_yaml = (
        reporting_raw.strip()
        if isinstance(reporting_raw, str) and reporting_raw.strip()
        else None
    )
    if not dna_yaml and not reporting_yaml:
        return None
    return {
        "summary": str(payload.get("summary") or "Proposed config updates"),
        "dna_yaml": dna_yaml,
        "reporting_yaml": reporting_yaml,
    }


def display_assistant_message(assistant_text: str, *, summary: str = "") -> str:
    """Short chat-visible reply — strip the machine JSON proposal block."""
    text = assistant_text or ""
    without_json = _JSON_BLOCK_RE.sub("", text).strip()
    # Drop leftover fences / huge YAML dumps if the model misbehaved.
    if "```" in without_json:
        without_json = re.split(r"```", without_json, maxsplit=1)[0].strip()
    if without_json and len(without_json) <= 600:
        return without_json
    if summary.strip():
        return summary.strip()
    if without_json:
        return without_json[:280].rstrip() + ("…" if len(without_json) > 280 else "")
    return "Proposed config updates. Review the diffs below."


@dataclass(frozen=True)
class AssistantTurnResult:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0


def _usage_from_response(response: dict[str, Any]) -> tuple[int, int]:
    usage = response.get("usage") or {}
    return (
        int(usage.get("inputTokens") or 0),
        int(usage.get("outputTokens") or 0),
    )


def _normalize_invoke_result(raw: str | AssistantTurnResult) -> AssistantTurnResult:
    if isinstance(raw, AssistantTurnResult):
        return raw
    return AssistantTurnResult(text=str(raw))


def _converse_loop(
    *,
    settings: DnaSettings,
    system: str,
    messages: list[dict[str, Any]],
    model_id: str,
) -> AssistantTurnResult:
    import boto3
    from botocore.config import Config

    client = boto3.client(
        "bedrock-runtime",
        config=Config(read_timeout=90, connect_timeout=10, retries={"max_attempts": 2}),
    )
    working = list(messages)
    input_tokens = 0
    output_tokens = 0
    # Keep tool rounds low — API Gateway times out at ~29s for sync requests.
    for _ in range(3):
        response = client.converse(
            modelId=model_id,
            system=[{"text": system}],
            messages=working,
            toolConfig={"tools": TOOL_SPECS},
            inferenceConfig={"maxTokens": 8192, "temperature": 0.2},
        )
        round_input, round_output = _usage_from_response(response)
        input_tokens += round_input
        output_tokens += round_output
        output = response.get("output") or {}
        message = output.get("message") or {}
        content = message.get("content") or []
        working.append({"role": "assistant", "content": content})

        tool_uses = [block for block in content if isinstance(block, dict) and "toolUse" in block]
        if not tool_uses:
            texts = [
                str(block.get("text") or "")
                for block in content
                if isinstance(block, dict) and block.get("text")
            ]
            return AssistantTurnResult(
                text="\n".join(texts).strip(),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )

        tool_results = []
        for block in tool_uses:
            use = block["toolUse"]
            name = str(use.get("name") or "")
            tool_use_id = str(use.get("toolUseId") or "")
            tool_input = use.get("input") if isinstance(use.get("input"), dict) else {}
            try:
                result_text = run_tool(settings, name, tool_input)
                status = "success"
            except Exception as exc:  # noqa: BLE001 — return tool error to the model
                result_text = f"Error: {exc}"
                status = "error"
            tool_results.append(
                {
                    "toolResult": {
                        "toolUseId": tool_use_id,
                        "content": [{"text": result_text}],
                        "status": status,
                    }
                }
            )
        working.append({"role": "user", "content": tool_results})

    return AssistantTurnResult(
        text="I could not finish proposing config changes. Please try again with a smaller request.",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


InvokeFn = Callable[[DnaSettings, str, list[dict[str, Any]], str], str | AssistantTurnResult]


def invoke_assistant(
    settings: DnaSettings,
    *,
    system: str,
    history: list[dict[str, str]],
    user_message: str,
    invoke_fn: InvokeFn | None = None,
) -> AssistantTurnResult:
    """Run one assistant turn. ``history`` items are {role, content} strings."""
    messages: list[dict[str, Any]] = []
    for item in history:
        role = str(item.get("role") or "")
        content = str(item.get("content") or "")
        if role not in {"user", "assistant"} or not content.strip():
            continue
        messages.append({"role": role, "content": [{"text": content}]})
    messages.append({"role": "user", "content": [{"text": user_message}]})

    model_id = (
        os.getenv("MESHFLOW_BEDROCK_MODEL_ID", "").strip()
        or DEFAULT_BEDROCK_MODEL_ID
    )

    if invoke_fn is not None:
        return _normalize_invoke_result(invoke_fn(settings, system, messages, model_id))

    if os.getenv("MESHFLOW_CONFIG_ASSISTANT_MOCK", "").strip() in {"1", "true", "yes"}:
        return AssistantTurnResult(text=_mock_assistant(settings, user_message))

    return _converse_loop(settings=settings, system=system, messages=messages, model_id=model_id)


def _mock_assistant(settings: DnaSettings, user_message: str) -> str:
    """Deterministic local/test assistant — updates reporting only by default."""
    # invoke_assistant may prefix current YAML context before the real request.
    message = user_message.strip()
    if "User request:\n" in message:
        message = message.split("User request:\n", 1)[-1].strip()
    lower = message.lower()
    note = f" (assistant note: {message[:120]})"
    payload: dict[str, Any] = {
        "summary": f"Updated config from chat: {message[:80]}",
    }
    touch_dna = "dna" in lower or "both" in lower
    touch_reporting = "reporting" in lower or "both" in lower or not touch_dna
    if touch_dna:
        dna = load_production_pack(settings).to_dict()
        dna["description"] = str(dna.get("description") or "") + note
        payload["dna_yaml"] = yaml.safe_dump(dna, sort_keys=False, allow_unicode=True)
    if touch_reporting:
        reporting = load_production_reporting(settings)
        reporting["description"] = str(reporting.get("description") or "") + note
        payload["reporting_yaml"] = yaml.safe_dump(
            reporting, sort_keys=False, allow_unicode=True
        )
    return (
        "Got it — I drafted the config updates below for your review.\n\n"
        f"```json\n{json.dumps(payload)}\n```"
    )
