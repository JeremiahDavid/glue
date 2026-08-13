from __future__ import annotations

from typing import Any


def handler(event: dict[str, Any] | None, _context: Any) -> dict[str, Any]:
    """Lambda entry: derive PK/FK relationships from entity_properties.yaml."""
    import json

    from meshflow.dna.source_docs.relationships import run_source_docs_relationships_job

    payload = event or {}
    source = str(payload.get("source") or "dbc").strip().lower() or "dbc"
    dry_run = bool(payload.get("dry_run"))
    bucket = str(payload.get("bucket") or "").strip() or None
    properties_object_key = (
        str(payload.get("properties_object_key") or payload.get("object_key") or "").strip() or None
    )
    relationships_object_key = str(payload.get("relationships_object_key") or "").strip() or None

    print(
        json.dumps(
            {
                "msg": "source_docs_relationships_start",
                "source": source,
                "dry_run": dry_run,
                "properties_object_key": properties_object_key,
            }
        )
    )
    result = run_source_docs_relationships_job(
        source=source,
        bucket=bucket,
        properties_object_key=properties_object_key,
        relationships_object_key=relationships_object_key,
        dry_run=dry_run,
    )
    print(json.dumps({"msg": "source_docs_relationships_done", "result": result}, default=str))
    return result


def lambda_handler(event: dict[str, Any] | None, context: Any) -> dict[str, Any]:
    return handler(event, context)
