"""Build client gold source-docs by merging global catalogs with lake overlays."""

from __future__ import annotations

import os
from typing import Any

import yaml

from hiveflow.dna.source_docs.scrape import (
    DEFAULT_SOURCE,
    source_docs_bucket_name,
    source_docs_object_key,
    source_docs_relationships_object_key,
    source_docs_tags_object_key,
    source_docs_uri,
)
from hiveflow.dna.source_docs.merge import merge_source_docs_artifact
from hiveflow.dna.source_docs.reconcile import reconcile_gold_artifacts
from hiveflow.dna.source_docs.schema import (
    SCHEMA_ARTIFACT_NAMES,
    ArtifactName,
    publish_source_docs_schemas,
    validate_source_docs_payload,
)

_ARTIFACT_FILENAMES: dict[ArtifactName, str] = {
    "entity_properties": "entity_properties.yaml",
    "entity_relationships": "entity_relationships.yaml",
    "entity_property_tags": "entity_property_tags.yaml",
}

_GLOBAL_KEY_FN = {
    "entity_properties": source_docs_object_key,
    "entity_relationships": source_docs_relationships_object_key,
    "entity_property_tags": source_docs_tags_object_key,
}


def client_data_bucket_name() -> str:
    return os.getenv("HIVEFLOW_S3_BUCKET", "").strip()


def _s3_get_yaml(bucket: str, key: str) -> dict[str, Any] | None:
    import boto3
    from botocore.exceptions import ClientError

    client = boto3.client("s3")
    try:
        response = client.get_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        code = str((exc.response or {}).get("Error", {}).get("Code") or "")
        if code in {"404", "NoSuchKey", "NotFound"}:
            return None
        raise
    payload = yaml.safe_load(response["Body"].read().decode("utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"Expected mapping in s3://{bucket}/{key}")
    return payload


def _s3_put_yaml(bucket: str, key: str, payload: dict[str, Any]) -> None:
    import boto3

    body = yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)
    boto3.client("s3").put_object(
        Bucket=bucket,
        Key=key,
        Body=body.encode("utf-8"),
        ContentType="application/yaml",
    )


def empty_overlay(source: str, artifact: ArtifactName) -> dict[str, Any]:
    kinds = {
        "entity_properties": "ms_learn_entity_properties_overlay",
        "entity_relationships": "ms_learn_entity_relationships_overlay",
        "entity_property_tags": "ms_learn_entity_property_tags_overlay",
    }
    return {
        "source": source,
        "kind": kinds[artifact],
        "description": (
            f"Client overlay for {artifact}. Use exclude: and addition: to customize "
            "the global catalog before gold merge."
        ),
        "exclude": {},
        "addition": {},
    }


def run_source_docs_gold_job(
    *,
    source: str = DEFAULT_SOURCE,
    client_bucket: str | None = None,
    global_bucket: str | None = None,
    artifacts: list[ArtifactName] | None = None,
    publish_schemas: bool = False,
    dry_run: bool = False,
    seed_missing_overlays: bool = False,
) -> dict[str, Any]:
    """Merge global source docs with client overlays into governance .../gold/."""
    from hiveflow.storage.paths import (
        governance_source_docs_gold_key,
        governance_source_docs_overlay_key,
        governance_source_semantic_latest_profile_key,
    )

    connector = source.strip().lower() or DEFAULT_SOURCE
    lake_bucket = (client_bucket or client_data_bucket_name()).strip()
    if not lake_bucket:
        raise ValueError("client_bucket or HIVEFLOW_S3_BUCKET is required")
    docs_bucket = (global_bucket or source_docs_bucket_name()).strip()
    selected = list(artifacts or SCHEMA_ARTIFACT_NAMES)

    schema_publish: dict[str, Any] | None = None
    if publish_schemas and not dry_run:
        schema_publish = publish_source_docs_schemas(bucket=docs_bucket, source=connector)

    results: list[dict[str, Any]] = []
    merged_artifacts: dict[str, dict[str, Any]] = {}
    overlay_seeded_by_artifact: dict[str, bool] = {}
    artifact_meta: dict[str, dict[str, str]] = {}
    for artifact in selected:
        filename = _ARTIFACT_FILENAMES[artifact]
        global_key = _GLOBAL_KEY_FN[artifact](connector)
        overlay_key = governance_source_docs_overlay_key(connector, filename)
        gold_key = governance_source_docs_gold_key(connector, filename)
        artifact_meta[artifact] = {
            "global_key": global_key,
            "overlay_key": overlay_key,
            "gold_key": gold_key,
        }

        global_catalog = _s3_get_yaml(docs_bucket, global_key)
        if global_catalog is None:
            raise FileNotFoundError(f"Missing global catalog s3://{docs_bucket}/{global_key}")

        overlay = _s3_get_yaml(lake_bucket, overlay_key)
        overlay_seeded = False
        if overlay is None:
            overlay = empty_overlay(connector, artifact)
            if seed_missing_overlays and not dry_run:
                _s3_put_yaml(lake_bucket, overlay_key, overlay)
                overlay_seeded = True
        overlay_seeded_by_artifact[artifact] = overlay_seeded

        gold = merge_source_docs_artifact(
            artifact=artifact,
            global_catalog=global_catalog,
            overlay=overlay,
            validate=True,
        )
        gold["merged_from"] = {
            "global": source_docs_uri(connector, object_key=global_key),
            "overlay": f"s3://{lake_bucket}/{overlay_key}",
        }
        merged_artifacts[artifact] = gold

    profile_key = governance_source_semantic_latest_profile_key(connector)
    profile = _s3_get_yaml(lake_bucket, profile_key)
    reconciled = False
    if profile and str(profile.get("kind") or "") == "silver_schema_profile":
        try:
            merged_artifacts = reconcile_gold_artifacts(merged_artifacts, profile)
            for gold_payload in merged_artifacts.values():
                merged_from = gold_payload.get("merged_from")
                if isinstance(merged_from, dict):
                    merged_from["silver_profile"] = {
                        **(merged_from.get("silver_profile") or {}),
                        "s3": f"s3://{lake_bucket}/{profile_key}",
                    }
            reconciled = True
        except ValueError:
            reconciled = False

    for artifact_name, payload in merged_artifacts.items():
        if reconciled:
            validate_source_docs_payload(payload, artifact=artifact_name, variant="catalog")

    for artifact in selected:
        gold = merged_artifacts[artifact]
        meta = artifact_meta[artifact]
        if not dry_run:
            _s3_put_yaml(lake_bucket, meta["gold_key"], gold)

        results.append(
            {
                "artifact": artifact,
                "overlay_seeded": overlay_seeded_by_artifact.get(artifact, False),
                "global": {"bucket": docs_bucket, "key": meta["global_key"]},
                "overlay": {"bucket": lake_bucket, "key": meta["overlay_key"]},
                "gold": {"bucket": lake_bucket, "key": meta["gold_key"]},
                "status": "dry_run" if dry_run else "published",
                "reconciled_with_silver_profile": reconciled,
            }
        )

    return {
        "status": "dry_run" if dry_run else "published",
        "source": connector,
        "client_bucket": lake_bucket,
        "global_bucket": docs_bucket,
        "artifacts": results,
        "schema_publish": schema_publish,
    }
