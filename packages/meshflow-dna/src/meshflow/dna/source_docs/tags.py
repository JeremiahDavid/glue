"""Generate conceptual property tags from BC entity_properties.yaml via Bedrock.

Reads s3://hiveflowai-source-documentation/{source}/entity_properties.yaml and
publishes entity_property_tags.yaml with the same entity/property shape, replacing
type/description with one or more short concept tags.

Every property always gets a field-specific tag derived from its camelCase name
(e.g. sellToCountry → "sell to country"). Identified foreign-key properties also
get a "foreign key" tag.
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
    source_docs_tags_object_key,
    source_docs_uri,
)
from meshflow.bc.source_docs_relationships import extract_table_keys

_DEFAULT_BEDROCK_MODEL_ID = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
_JSON_BLOCK_RE = re.compile(r"\{[\s\S]*\}|\[[\s\S]*\]")
_CAMEL_SPLIT_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
_MAX_TAG_WORDS = 5
_FOREIGN_KEY_TAG = "foreign key"

# Multi-token expansions applied left-to-right on camelCase parts (lowercased).
_TOKEN_PHRASE_EXPANSIONS: dict[tuple[str, ...], tuple[str, ...]] = {
    ("post", "code"): ("postal", "code"),
    ("postal", "code"): ("postal", "code"),
}
# Single-token expansions (lowercased source → lowercase phrase parts).
_TOKEN_EXPANSIONS: dict[str, tuple[str, ...]] = {
    "id": ("id",),
    "qty": ("quantity",),
    "amt": ("amount",),
    "no": ("number",),
    "num": ("number",),
    "addr": ("address",),
    "desc": ("description",),
}

InvokeFn = Callable[[str, str], str]

_TAG_SYSTEM_PROMPT = (
    "Generate tags for each property that describe the field within the context of "
    "its parent entity. All tags should be phrases with 5 words or less.\n\n"
    "Rules:\n"
    "- Always include one field-specific tag that names the property itself "
    "(e.g. sellToCountry → \"sell to country\", sellToPostCode → \"sell to postal code\"). "
    "Do not collapse distinct fields into one shared abstract tag only.\n"
    "- You may also add broader conceptual tags (e.g. \"sell to address\", "
    "\"company location\") in addition to the field-specific tag.\n"
    "- If a property is a foreign key (description refers to an ID of another entity), "
    "include the tag \"foreign key\".\n\n"
    "Return JSON only:\n"
    '{"properties": [{"name": "sellToCountry", "tags": ["sell to country", "sell to address"]}]}\n'
    "Include every property from the provided entity_properties YAML. "
    "Each property may have one or many tags."
)


def _parse_json_payload(raw: str) -> dict[str, Any] | list[Any]:
    text = str(raw or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
        if isinstance(parsed, (dict, list)):
            return parsed
    except json.JSONDecodeError:
        pass
    match = _JSON_BLOCK_RE.search(text)
    if not match:
        return {}
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, (dict, list)) else {}


def _default_invoke(system: str, user_message: str) -> str:
    import boto3
    from botocore.config import Config

    model_id = os.getenv("MESHFLOW_BEDROCK_MODEL_ID", _DEFAULT_BEDROCK_MODEL_ID).strip()
    client = boto3.client(
        "bedrock-runtime",
        config=Config(read_timeout=120, connect_timeout=10, retries={"max_attempts": 2}),
    )
    response = client.converse(
        modelId=model_id,
        system=[{"text": system}],
        messages=[{"role": "user", "content": [{"text": user_message}]}],
        inferenceConfig={"maxTokens": 4096, "temperature": 0.1},
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


def _normalize_tag(value: str) -> str:
    text = " ".join(str(value or "").strip().split())
    if not text:
        return ""
    words = text.split(" ")
    if len(words) > _MAX_TAG_WORDS:
        text = " ".join(words[:_MAX_TAG_WORDS])
    return text


def _normalize_tags(values: Any) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        raw = [values]
    elif isinstance(values, list):
        raw = values
    else:
        return []
    seen: set[str] = set()
    tags: list[str] = []
    for item in raw:
        tag = _normalize_tag(str(item or ""))
        key = tag.casefold()
        if not tag or key in seen:
            continue
        seen.add(key)
        tags.append(tag)
    return tags


def split_camel_case(name: str) -> list[str]:
    """Split camelCase / PascalCase identifiers into word tokens."""
    text = str(name or "").strip()
    if not text:
        return []
    spaced = _CAMEL_SPLIT_RE.sub(" ", text)
    return [part for part in re.split(r"[\s_]+", spaced) if part]


def _expand_field_tokens(tokens: list[str]) -> list[str]:
    """Expand common BC abbreviations into readable phrase parts."""
    lowered = [token.casefold() for token in tokens if token]
    expanded: list[str] = []
    index = 0
    while index < len(lowered):
        matched = False
        for length in (2, 1):
            if index + length > len(lowered):
                continue
            chunk = tuple(lowered[index : index + length])
            if length == 2 and chunk in _TOKEN_PHRASE_EXPANSIONS:
                expanded.extend(_TOKEN_PHRASE_EXPANSIONS[chunk])
                index += length
                matched = True
                break
            if length == 1 and chunk[0] in _TOKEN_EXPANSIONS:
                expanded.extend(_TOKEN_EXPANSIONS[chunk[0]])
                index += 1
                matched = True
                break
        if not matched:
            expanded.append(lowered[index])
            index += 1
    return expanded


def field_specific_tag(property_name: str) -> str:
    """Deterministic field-specific tag from a property name.

    Examples:
    - sellToCountry → sell to country
    - sellToPostCode → sell to postal code
    - billToCustomerNumber → bill to customer number
    """
    tokens = _expand_field_tokens(split_camel_case(property_name))
    return _normalize_tag(" ".join(tokens))


def enrich_property_tags(
    property_name: str,
    tags: Any,
    *,
    is_foreign_key: bool = False,
) -> list[str]:
    """Ensure field-specific (+ optional FK) tags are present alongside model tags."""
    ordered: list[str] = []
    specific = field_specific_tag(property_name)
    if specific:
        ordered.append(specific)
    if is_foreign_key:
        ordered.append(_FOREIGN_KEY_TAG)
    ordered.extend(_normalize_tags(tags))
    return _normalize_tags(ordered)


def entity_properties_prompt_yaml(entity: dict[str, Any]) -> str:
    """Slim entity_properties YAML fragment included in the Bedrock prompt."""
    properties = []
    for prop in entity.get("properties") or []:
        if not isinstance(prop, dict):
            continue
        name = str(prop.get("name") or "").strip()
        if not name:
            continue
        properties.append(
            {
                "name": name,
                "type": str(prop.get("type") or "").strip(),
                "description": str(prop.get("description") or "").strip(),
            }
        )
    payload = {
        "silver_entity": str(entity.get("silver_entity") or "").strip(),
        "description": str(entity.get("description") or "").strip(),
        "properties": properties,
    }
    return yaml.safe_dump(payload, sort_keys=False, allow_unicode=True, width=120)


def _extract_property_tags(payload: dict[str, Any] | list[Any]) -> dict[str, list[str]]:
    rows: list[Any]
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        maybe = payload.get("properties")
        if isinstance(maybe, list):
            rows = maybe
        else:
            rows = []
    else:
        rows = []

    by_name: dict[str, list[str]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        by_name[name] = _normalize_tags(row.get("tags"))
    return by_name


def tag_entity_properties(
    entity: dict[str, Any],
    *,
    invoke_fn: InvokeFn | None = None,
) -> dict[str, list[str]]:
    """Ask Bedrock for concept tags for one entity's properties."""
    properties = [
        prop
        for prop in (entity.get("properties") or [])
        if isinstance(prop, dict) and str(prop.get("name") or "").strip()
    ]
    if not properties:
        return {}

    prompt_yaml = entity_properties_prompt_yaml(entity)
    user_message = (
        "entity_properties:\n"
        f"{prompt_yaml}\n"
        "Generate tags for each property that describe the field within the context of "
        "its parent entity. Always include a field-specific tag derived from the property "
        "name (e.g. sellToCountry → \"sell to country\"), plus any broader conceptual tags. "
        "Tag foreign-key ID fields with \"foreign key\". All tags should be phrases with "
        "5 words or less."
    )
    invoke = invoke_fn or _default_invoke
    parsed = _parse_json_payload(invoke(_TAG_SYSTEM_PROMPT, user_message))
    return _extract_property_tags(parsed)


def build_entity_property_tags(
    catalog: dict[str, Any],
    *,
    invoke_fn: InvokeFn | None = None,
    sourced_from: str | None = None,
) -> dict[str, Any]:
    """Build entity_property_tags.yaml from an entity_properties catalog."""
    tables_out: list[dict[str, Any]] = []
    tagged_property_count = 0
    for entity in catalog.get("tables") or catalog.get("entities") or []:
        if not isinstance(entity, dict):
            continue
        silver = str(entity.get("silver_entity") or "").strip()
        if not silver:
            continue
        fk_fields = {
            str(item.get("field") or "").strip()
            for item in (extract_table_keys(entity).get("foreign_keys") or [])
            if str(item.get("field") or "").strip()
        }
        tags_by_name = tag_entity_properties(entity, invoke_fn=invoke_fn)
        property_rows: list[dict[str, Any]] = []
        for prop in entity.get("properties") or []:
            if not isinstance(prop, dict):
                continue
            name = str(prop.get("name") or "").strip()
            if not name:
                continue
            tags = enrich_property_tags(
                name,
                tags_by_name.get(name) or [],
                is_foreign_key=name in fk_fields,
            )
            if tags:
                tagged_property_count += 1
            property_rows.append({"name": name, "tags": tags})
        tables_out.append(
            {
                "silver_entity": silver,
                "bc_resource_slug": str(entity.get("bc_resource_slug") or "").strip(),
                "description": str(entity.get("description") or "").strip(),
                "ms_learn_url": str(entity.get("ms_learn_url") or "").strip(),
                "property_count": len(property_rows),
                "properties": property_rows,
            }
        )

    tables_out.sort(key=lambda item: str(item.get("silver_entity") or ""))
    source = str(catalog.get("source") or DEFAULT_SOURCE).strip().lower() or DEFAULT_SOURCE
    return {
        "source": source,
        "kind": "ms_learn_entity_property_tags",
        "description": (
            "Conceptual column tags generated from Microsoft Learn property descriptions "
            "in entity_properties.yaml. Each property includes a field-specific tag from "
            "its name; identified foreign keys also include a foreign key tag."
        ),
        "generated_at": datetime.now(UTC).isoformat(),
        "sourced_from": sourced_from
        or source_docs_uri(source, object_key=source_docs_object_key(source)),
        "table_count": len(tables_out),
        "property_count": sum(int(item.get("property_count") or 0) for item in tables_out),
        "tagged_property_count": tagged_property_count,
        "tables": tables_out,
    }


def tags_to_yaml(payload: dict[str, Any]) -> str:
    return yaml.safe_dump(payload, sort_keys=False, allow_unicode=True, width=120)


def write_entity_property_tags(
    payload: dict[str, Any],
    *,
    bucket: str | None = None,
    object_key: str | None = None,
) -> dict[str, Any]:
    """Write property tags YAML to the global source-documentation bucket."""
    import boto3

    source = str(payload.get("source") or DEFAULT_SOURCE)
    bucket_name = (bucket or source_docs_bucket_name()).strip()
    key = (object_key or source_docs_tags_object_key(source)).lstrip("/")
    body = tags_to_yaml(payload).encode("utf-8")
    client = boto3.client("s3")
    client.put_object(
        Bucket=bucket_name,
        Key=key,
        Body=body,
        ContentType="application/yaml; charset=utf-8",
        Metadata={
            "source": source,
            "kind": "ms_learn_entity_property_tags",
            "table_count": str(payload.get("table_count") or payload.get("entity_count") or 0),
            "property_count": str(payload.get("property_count") or 0),
            "tagged_property_count": str(payload.get("tagged_property_count") or 0),
        },
    )
    return {
        "bucket": bucket_name,
        "key": key,
        "uri": f"s3://{bucket_name}/{key}",
        "bytes": len(body),
    }


def run_source_docs_tags_job(
    *,
    source: str = DEFAULT_SOURCE,
    bucket: str | None = None,
    properties_object_key: str | None = None,
    tags_object_key: str | None = None,
    catalog: dict[str, Any] | None = None,
    invoke_fn: InvokeFn | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Load entity_properties.yaml from S3 (or use provided catalog) and publish tags."""
    source_key = source.strip().lower() or DEFAULT_SOURCE
    props_key = properties_object_key or source_docs_object_key(source_key)
    if catalog is None:
        catalog = load_source_properties_catalog(
            bucket=bucket,
            object_key=props_key,
            source=source_key,
        )
    sourced_from = source_docs_uri(source_key, object_key=props_key)
    payload = build_entity_property_tags(
        catalog,
        invoke_fn=invoke_fn,
        sourced_from=sourced_from,
    )
    result: dict[str, Any] = {
        "status": "built",
        "source": payload["source"],
        "table_count": payload.get("table_count"),
        "property_count": payload.get("property_count"),
        "tagged_property_count": payload.get("tagged_property_count"),
        "sourced_from": sourced_from,
        "generated_at": payload.get("generated_at"),
    }
    if dry_run:
        result["status"] = "dry_run"
        result["preview_tables"] = [e.get("silver_entity") for e in (payload.get("tables") or [])[:5]]
        return result

    written = write_entity_property_tags(
        payload,
        bucket=bucket,
        object_key=tags_object_key,
    )
    result["status"] = "published"
    result["artifact"] = written
    print(json.dumps({"msg": "source_docs_tags_published", **result}, default=str))
    return result
