"""Semantic Builder assistant — Bedrock Q&A over source packs and tenant model."""

from __future__ import annotations

import os
from typing import Any

from meshflow.dna.semantic_knowledge import semantic_assistant_system_prompt
from meshflow.dna.settings import DnaSettings
from meshflow.dna.web.portal.config_assistant.bedrock_chat import DEFAULT_BEDROCK_MODEL_ID
from meshflow.dna.web.portal.config_assistant.bedrock_usage import (
    assert_within_budget,
    record_usage,
)


from meshflow.dna.web.portal.config_assistant.service import _resolve_client_id


def _converse(
    *,
    system: str,
    messages: list[dict[str, Any]],
    model_id: str,
) -> tuple[str, int, int]:
    import boto3
    from botocore.config import Config

    client = boto3.client(
        "bedrock-runtime",
        config=Config(read_timeout=60, connect_timeout=10, retries={"max_attempts": 2}),
    )
    response = client.converse(
        modelId=model_id,
        system=[{"text": system}],
        messages=messages,
        inferenceConfig={"maxTokens": 2048, "temperature": 0.2},
    )
    usage = response.get("usage") or {}
    input_tokens = int(usage.get("inputTokens") or 0)
    output_tokens = int(usage.get("outputTokens") or 0)
    output = response.get("output") or {}
    message = output.get("message") or {}
    content = message.get("content") or []
    texts = [
        str(block.get("text") or "")
        for block in content
        if isinstance(block, dict) and block.get("text")
    ]
    return "\n".join(texts).strip(), input_tokens, output_tokens


def chat_semantic_assistant(
    settings: DnaSettings,
    *,
    user_message: str,
    history: list[dict[str, str]] | None = None,
    username: str = "",
) -> dict[str, Any]:
    """Answer a user question about the semantic model (no automatic YAML edits)."""
    message = str(user_message or "").strip()
    if not message:
        raise ValueError("message is required")

    model_id = os.getenv("MESHFLOW_BEDROCK_MODEL_ID", DEFAULT_BEDROCK_MODEL_ID).strip()
    client_id = _resolve_client_id()
    if client_id:
        assert_within_budget(settings, client_id=client_id)

    system = semantic_assistant_system_prompt(settings, query=message)
    messages: list[dict[str, Any]] = []
    for item in history or []:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip().lower()
        text = str(item.get("content") or item.get("text") or "").strip()
        if role in {"user", "assistant"} and text:
            messages.append({"role": role, "content": [{"text": text}]})
    messages.append({"role": "user", "content": [{"text": message}]})

    reply, input_tokens, output_tokens = _converse(system=system, messages=messages, model_id=model_id)
    if client_id and (input_tokens > 0 or output_tokens > 0):
        record_usage(
            settings,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            client_id=client_id,
        )
    return {
        "reply": reply,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }
