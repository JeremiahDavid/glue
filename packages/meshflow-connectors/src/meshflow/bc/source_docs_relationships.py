"""Derive PK/FK relationships from BC entity_properties.yaml descriptions.

Reads s3://hiveflowai-source-documentation/{source}/entity_properties.yaml,
classifies keys from property descriptions, and asks Bedrock (one batched call)
to map each FK description to a target silver table.
"""

from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from typing import Any, Callable

import yaml

from meshflow.bc.source_docs import (
    DEFAULT_SOURCE,
    load_source_properties_catalog,
    source_docs_bucket_name,
    source_docs_object_key,
    source_docs_relationships_object_key,
    source_docs_uri,
)

_DEFAULT_BEDROCK_MODEL_ID = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
_UNIQUE_ID_RE = re.compile(r"\bunique\s+ID\b", re.IGNORECASE)
_ID_TOKEN_RE = re.compile(r"\bID\b", re.IGNORECASE)
_JSON_BLOCK_RE = re.compile(r"\{[\s\S]*\}")

InvokeFn = Callable[[str, str], str]


def _field_name_ends_with_id(field_name: str) -> bool:
    return str(field_name or "").strip().lower().endswith("id")


def classify_property_key_role(description: str, *, field_name: str = "") -> str | None:
    """Return 'pk', 'fk', or None from a property name + Microsoft Learn description.

    - Field ``id`` with description containing "unique ID" → primary key
    - Other fields ending in ``id`` with description containing "ID" → foreign key
    """
    text = str(description or "").strip()
    if not text:
        return None
    name = str(field_name or "").strip().lower()
    has_unique_id = bool(_UNIQUE_ID_RE.search(text))
    has_id_token = bool(_ID_TOKEN_RE.search(text))
    if not has_unique_id and not has_id_token:
        return None
    if name == "id":
        return "pk" if has_unique_id else None
    if _field_name_ends_with_id(name):
        return "fk"
    return None


def extract_table_keys(entity: dict[str, Any]) -> dict[str, Any]:
    """Identify PK field and FK candidates for one entity from property descriptions."""
    properties = entity.get("properties") or []
    pk = ""
    foreign_keys: list[dict[str, str]] = []
    for prop in properties:
        if not isinstance(prop, dict):
            continue
        name = str(prop.get("name") or "").strip()
        description = str(prop.get("description") or "").strip()
        if not name or not description:
            continue
        role = classify_property_key_role(description, field_name=name)
        if role == "pk":
            pk = name
        elif role == "fk":
            foreign_keys.append({"field": name, "description": description})
    return {"PK": pk, "foreign_keys": foreign_keys}


def _parse_json_object(raw: str) -> dict[str, Any]:
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
        inferenceConfig={"maxTokens": 2048, "temperature": 0.0},
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


def _normalize_table_name(value: str, allowed: set[str]) -> str:
    candidate = str(value or "").strip().lower().replace(" ", "_").replace("-", "_")
    if candidate in allowed:
        return candidate
    # Soft match: drop trailing pluralization mismatches already covered by silver names.
    if candidate.endswith("s") and candidate[:-1] in allowed:
        return candidate[:-1]
    if f"{candidate}s" in allowed:
        return f"{candidate}s"
    return ""


def line_table_header_base(table: str) -> str:
    """Strip a trailing line/lines suffix from a line table name.

    Examples:
    - sales_order_lines → sales_order
    - sales_order_line → sales_order
    - journal_lines → journal
    """
    name = str(table or "").strip().lower()
    for suffix in ("_lines", "_line", "lines", "line"):
        if name.endswith(suffix) and len(name) > len(suffix):
            return name[: -len(suffix)].rstrip("_")
    return ""


def resolve_document_id_target(table: str, *, allowed_tables: list[str] | set[str]) -> str:
    """Map documentId on a *line(s) table to its header table (header PK, usually id)."""
    base = line_table_header_base(table)
    if not base:
        return ""
    allowed = {str(name).strip().lower() for name in allowed_tables if str(name).strip()}
    return _normalize_table_name(base, allowed)


def is_line_document_id_fk(*, table: str, field: str) -> bool:
    return str(field or "").strip() == "documentId" and bool(line_table_header_base(table))


def resolve_fk_targets(
    fk_items: list[dict[str, str]],
    *,
    allowed_tables: list[str],
    invoke_fn: InvokeFn | None = None,
) -> dict[int, str]:
    """Map FK description indexes → target silver table via one minimal Bedrock call.

    Prompt payload is intentionally tiny: allowed table names + numbered FK descriptions.
    """
    if not fk_items:
        return {}
    allowed = sorted({str(name).strip().lower() for name in allowed_tables if str(name).strip()})
    if not allowed:
        return {}

    lines = [f"{index}. {item['description']}" for index, item in enumerate(fk_items, start=1)]
    system = (
        "Map each Business Central foreign-key field description to the best matching "
        "silver table name from the allowed list. Return JSON only:\n"
        '{"targets": {"1": "table_name", "2": "table_name"}}\n'
        "Use only names from the allowed list. If unsure, use an empty string."
    )
    user_message = (
        "Allowed tables:\n"
        + ", ".join(allowed)
        + "\n\nFK descriptions:\n"
        + "\n".join(lines)
    )
    invoke = invoke_fn or _default_invoke
    payload = _parse_json_object(invoke(system, user_message))
    targets_raw = payload.get("targets")
    if not isinstance(targets_raw, dict):
        return {}

    allowed_set = set(allowed)
    resolved: dict[int, str] = {}
    for key, value in targets_raw.items():
        try:
            index = int(key)
        except (TypeError, ValueError):
            continue
        if index < 1 or index > len(fk_items):
            continue
        table = _normalize_table_name(str(value or ""), allowed_set)
        if table:
            resolved[index] = table
    return resolved


def build_entity_relationships(
    catalog: dict[str, Any],
    *,
    invoke_fn: InvokeFn | None = None,
    sourced_from: str | None = None,
) -> dict[str, Any]:
    """Build relationships YAML structure from an entity_properties catalog."""
    entities = [
        item
        for item in (catalog.get("tables") or catalog.get("entities") or [])
        if isinstance(item, dict)
    ]
    table_names = [
        str(item.get("silver_entity") or "").strip().lower()
        for item in entities
        if str(item.get("silver_entity") or "").strip()
    ]
    pk_by_table: dict[str, str] = {}
    pending_fks: list[dict[str, str]] = []
    tables: dict[str, Any] = {}

    for entity in entities:
        table = str(entity.get("silver_entity") or "").strip().lower()
        if not table:
            continue
        keys = extract_table_keys(entity)
        pk = str(keys.get("PK") or "").strip()
        pk_by_table[table] = pk
        tables[table] = {"PK": pk, "relationships": []}
        for fk in keys.get("foreign_keys") or []:
            pending_fks.append(
                {
                    "table": table,
                    "field": str(fk.get("field") or "").strip(),
                    "description": str(fk.get("description") or "").strip(),
                }
            )

    # Deterministic: documentId on *line(s) tables → header table (strip trailing line/lines).
    resolved: dict[int, str] = {}
    ai_items: list[dict[str, str]] = []
    ai_index_by_pending: dict[int, int] = {}
    for index, item in enumerate(pending_fks, start=1):
        if is_line_document_id_fk(table=item["table"], field=item["field"]):
            target = resolve_document_id_target(item["table"], allowed_tables=table_names)
            if target:
                resolved[index] = target
                continue
        ai_index_by_pending[index] = len(ai_items) + 1
        ai_items.append({"description": item["description"]})

    ai_resolved = resolve_fk_targets(
        ai_items,
        allowed_tables=table_names,
        invoke_fn=invoke_fn,
    )
    for pending_index, ai_index in ai_index_by_pending.items():
        target = ai_resolved.get(ai_index, "")
        if target:
            resolved[pending_index] = target

    unresolved: list[dict[str, str]] = []
    for index, item in enumerate(pending_fks, start=1):
        target = resolved.get(index, "")
        if not target:
            unresolved.append(
                {
                    "table": item["table"],
                    "FK": item["field"],
                    "description": item["description"],
                }
            )
            continue
        tables[item["table"]]["relationships"].append(
            {
                "target": target,
                "PK": pk_by_table.get(target) or "id",
                "FK": item["field"],
            }
        )

    for table in tables.values():
        table["relationships"].sort(key=lambda row: (str(row.get("FK") or ""), str(row.get("target") or "")))

    ordered_tables = {name: tables[name] for name in sorted(tables)}
    source = str(catalog.get("source") or DEFAULT_SOURCE).strip().lower() or DEFAULT_SOURCE
    return {
        "source": source,
        "kind": "ms_learn_entity_relationships",
        "description": (
            "Primary keys and foreign-key relationships derived from Microsoft Learn "
            "property descriptions in entity_properties.yaml."
        ),
        "generated_at": datetime.now(UTC).isoformat(),
        "sourced_from": sourced_from
        or source_docs_uri(source, object_key=source_docs_object_key(source)),
        "table_count": len(ordered_tables),
        "relationship_count": sum(len(item["relationships"]) for item in ordered_tables.values()),
        "unresolved_fk_count": len(unresolved),
        "unresolved_fks": unresolved,
        "tables": ordered_tables,
    }


def relationships_to_yaml(payload: dict[str, Any]) -> str:
    return yaml.safe_dump(payload, sort_keys=False, allow_unicode=True, width=120)


def write_entity_relationships(
    payload: dict[str, Any],
    *,
    bucket: str | None = None,
    object_key: str | None = None,
) -> dict[str, Any]:
    """Write relationships YAML to the global source-documentation bucket."""
    import boto3

    source = str(payload.get("source") or DEFAULT_SOURCE)
    bucket_name = (bucket or source_docs_bucket_name()).strip()
    key = (object_key or source_docs_relationships_object_key(source)).lstrip("/")
    body = relationships_to_yaml(payload).encode("utf-8")
    client = boto3.client("s3")
    client.put_object(
        Bucket=bucket_name,
        Key=key,
        Body=body,
        ContentType="application/yaml; charset=utf-8",
        Metadata={
            "source": source,
            "kind": "ms_learn_entity_relationships",
            "table_count": str(payload.get("table_count") or 0),
            "relationship_count": str(payload.get("relationship_count") or 0),
        },
    )
    return {
        "bucket": bucket_name,
        "key": key,
        "uri": f"s3://{bucket_name}/{key}",
        "bytes": len(body),
    }


def run_source_docs_relationships_job(
    *,
    source: str = DEFAULT_SOURCE,
    bucket: str | None = None,
    properties_object_key: str | None = None,
    relationships_object_key: str | None = None,
    catalog: dict[str, Any] | None = None,
    invoke_fn: InvokeFn | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Load entity_properties.yaml from S3 (or use provided catalog) and publish relationships."""
    source_key = source.strip().lower() or DEFAULT_SOURCE
    props_key = properties_object_key or source_docs_object_key(source_key)
    if catalog is None:
        catalog = load_source_properties_catalog(
            bucket=bucket,
            object_key=props_key,
            source=source_key,
        )
    sourced_from = source_docs_uri(source_key, object_key=props_key)
    payload = build_entity_relationships(
        catalog,
        invoke_fn=invoke_fn,
        sourced_from=sourced_from,
    )
    result: dict[str, Any] = {
        "status": "built",
        "source": payload["source"],
        "table_count": payload.get("table_count"),
        "relationship_count": payload.get("relationship_count"),
        "unresolved_fk_count": payload.get("unresolved_fk_count"),
        "sourced_from": sourced_from,
        "generated_at": payload.get("generated_at"),
    }
    if dry_run:
        result["status"] = "dry_run"
        result["preview_tables"] = list((payload.get("tables") or {}).keys())[:5]
        return result

    written = write_entity_relationships(
        payload,
        bucket=bucket,
        object_key=relationships_object_key,
    )
    result["status"] = "published"
    result["artifact"] = written
    print(json.dumps({"msg": "source_docs_relationships_published", **result}, default=str))
    return result
