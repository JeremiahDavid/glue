from __future__ import annotations

from typing import Any


def handler(event: dict[str, Any] | None, _context: Any) -> dict[str, Any]:
    """Lambda entry: merge global source docs + client overlays → gold YAML."""
    import json

    from hiveflow.dna.source_docs.gold import run_source_docs_gold_job
    from hiveflow.dna.source_docs.schema import SCHEMA_ARTIFACT_NAMES

    payload = event or {}
    source = str(payload.get("source") or "dbc").strip().lower() or "dbc"
    dry_run = bool(payload.get("dry_run"))
    publish_schemas = bool(payload.get("publish_schemas", True))
    seed_missing_overlays = bool(payload.get("seed_missing_overlays", True))
    client_bucket = str(payload.get("client_bucket") or payload.get("bucket") or "").strip() or None
    global_bucket = str(payload.get("global_bucket") or "").strip() or None

    raw_artifacts = payload.get("artifacts")
    artifacts = None
    if isinstance(raw_artifacts, list) and raw_artifacts:
        allowed = set(SCHEMA_ARTIFACT_NAMES)
        artifacts = []
        for item in raw_artifacts:
            name = str(item or "").strip()
            if name in allowed:
                artifacts.append(name)  # type: ignore[arg-type]

    print(
        json.dumps(
            {
                "msg": "source_docs_gold_start",
                "source": source,
                "dry_run": dry_run,
                "seed_missing_overlays": seed_missing_overlays,
                "publish_schemas": publish_schemas,
            }
        )
    )
    result = run_source_docs_gold_job(
        source=source,
        client_bucket=client_bucket,
        global_bucket=global_bucket,
        artifacts=artifacts,
        publish_schemas=publish_schemas,
        dry_run=dry_run,
        seed_missing_overlays=seed_missing_overlays,
    )
    print(json.dumps({"msg": "source_docs_gold_done", "result": result}, default=str))
    return result


def lambda_handler(event: dict[str, Any] | None, context: Any) -> dict[str, Any]:
    return handler(event, context)
