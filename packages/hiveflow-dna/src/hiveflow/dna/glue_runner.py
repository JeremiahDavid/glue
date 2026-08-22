"""Glue Python Shell runner: DNA-pack silver from silver_stg, then gold."""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Any

from hiveflow.dna.lambda_handler import run_dna_pipeline
from hiveflow.dna.runtime import resolve_dna_settings
from hiveflow.dna.sql_pack import load_sql_pack, load_transform_sql, silver_entities_for_sql_pack
from hiveflow.dna.sql_runtime import apply_silver_sql_pack
from hiveflow.project_config import (
    get_environment_config,
    iter_configured_connectors,
    resolve_selection,
)
from hiveflow.storage.paths import (
    prefix_path,
    silver_entity_parquet_key,
    silver_entity_prefix,
    silver_source_prefix,
    silver_stg_entity_parquet_key,
    silver_stg_entity_prefix,
)

logger = logging.getLogger(__name__)


def run_dna_refresh(
    *,
    source: str = "",
    bucket: str | None = None,
) -> dict[str, Any]:
    """Refresh DNA silver (from silver_stg) and gold for configured connectors."""
    company, environment = resolve_selection()
    env_config = get_environment_config(company, environment)
    resolved_bucket = (bucket or os.getenv("HIVEFLOW_S3_BUCKET", "")).strip() or None

    requested_source = source.strip().lower()
    connectors = list(iter_configured_connectors(env_config))
    if requested_source:
        connectors = [item for item in connectors if item[0] == requested_source]
        if not connectors:
            raise ValueError(
                f"Connector {requested_source!r} is not configured for {company}/{environment}"
            )

    copies: dict[str, Any] = {}
    silver_sql: dict[str, Any] = {"status": "skipped", "reason": "not_run"}
    last_pack_version = ""
    for connector, _connector_cfg in connectors:
        settings = resolve_dna_settings(
            event={
                "source": connector,
                "company": company,
                "action": "publish",
            }
        )
        if resolved_bucket:
            settings.s3_bucket = resolved_bucket
        entities = resolve_dna_silver_entities(settings, source=connector)
        copies[connector] = copy_silver_stg_to_silver(
            settings,
            source=connector,
            entities=entities,
            company=company,
            environment=environment,
        )
        copies[connector]["entities"] = entities
        copies[connector]["pruned"] = prune_dna_silver(
            settings,
            source=connector,
            keep_entities=entities,
            company=company,
            environment=environment,
        )
        silver_sql = apply_silver_sql_pack(
            settings,
            source=connector,
            company=company,
            environment=environment,
        )
        copies[connector]["silver_sql"] = silver_sql
        last_pack_version = str(silver_sql.get("pack_version") or last_pack_version)

    dna_settings = resolve_dna_settings(
        event={
            "source": requested_source or (connectors[0][0] if connectors else ""),
            "company": company,
            "action": "publish",
        }
    )
    if resolved_bucket:
        dna_settings.s3_bucket = resolved_bucket
    gold = run_dna_pipeline(
        dna_settings,
        silver_sql_pack_version=last_pack_version,
    )
    return {
        "status": "ok",
        "company": company,
        "environment": environment,
        "copies": copies,
        "silver_sql": silver_sql,
        "gold": gold,
    }


def copy_silver_stg_to_silver(
    settings: Any,
    *,
    source: str,
    entities: list[str],
    company: str = "",
    environment: str | None = None,
    region: str | None = None,
) -> dict[str, Any]:
    """Copy pack-referenced silver_stg entities into DNA silver."""
    copied: list[str] = []
    skipped: list[str] = []
    catalog_skipped: list[str] = []
    for entity in entities:
        name = entity.strip().lower()
        if not name:
            continue
        if settings.s3_bucket:
            if _copy_s3_entity(bucket=settings.s3_bucket, source=source, entity=name):
                copied.append(name)
                if not _sync_dna_silver_glue(
                    settings,
                    source=source,
                    entity=name,
                    company=company,
                    environment=environment,
                    region=region,
                ):
                    catalog_skipped.append(name)
            else:
                skipped.append(name)
            continue
        if _copy_local_entity(data_dir=settings.data_dir, source=source, entity=name):
            copied.append(name)
        else:
            skipped.append(name)
    return {"copied": copied, "skipped": skipped, "catalog_skipped": catalog_skipped}


def resolve_dna_silver_entities(settings: Any, *, source: str) -> list[str]:
    """Entities DNA silver should hold: silver SQL targets and gold SQL sources."""
    pack = load_sql_pack(settings)
    if pack is None:
        return _compile_pack_silver_entities(settings)
    gold_sql: dict[str, str] = {}
    for transform in pack.by_layer("gold"):
        gold_sql[transform.file] = load_transform_sql(
            settings,
            transform,
            pack_id=settings.dna_config_id,
            version=pack.version,
            verify_checksum=True,
        )
    return silver_entities_for_sql_pack(pack, source=source, gold_sql=gold_sql)


def _compile_pack_silver_entities(settings: Any) -> list[str]:
    try:
        from hiveflow.dna.workflow import load_production_pack

        pack = load_production_pack(settings)
    except Exception:  # noqa: BLE001
        logger.warning("No SQL pack or YAML pack entities for DNA silver copy")
        return []
    names = {
        str(entity.silver_entity or "").strip().lower()
        for entity in getattr(pack, "entities", [])
        if str(getattr(entity, "silver_entity", "") or "").strip()
    }
    return sorted(names)


def prune_dna_silver(
    settings: Any,
    *,
    source: str,
    keep_entities: list[str],
    company: str = "",
    environment: str | None = None,
    region: str | None = None,
) -> dict[str, Any]:
    """Remove silver prefixes/tables that are not in the DNA pack."""
    keep = {name.strip().lower() for name in keep_entities if name.strip()}
    if settings.s3_bucket:
        removed = _prune_s3_silver(bucket=settings.s3_bucket, source=source, keep=keep)
        dropped = _drop_unused_silver_glue(
            source=source,
            keep=keep,
            company=company,
            environment=environment,
            region=region,
        )
        return {"removed_prefixes": removed, "dropped_tables": dropped}
    return {"removed_prefixes": _prune_local_silver(settings.data_dir, source, keep), "dropped_tables": []}


def _prune_local_silver(data_dir: Path, source: str, keep: set[str]) -> list[str]:
    root = prefix_path(data_dir, silver_source_prefix(source))
    if not root.is_dir():
        return []
    removed: list[str] = []
    for child in root.iterdir():
        if not child.is_dir():
            continue
        name = child.name.strip().lower()
        if name in keep:
            continue
        shutil.rmtree(child)
        removed.append(name)
    return sorted(removed)


def _prune_s3_silver(*, bucket: str, source: str, keep: set[str]) -> list[str]:
    import boto3

    client = boto3.client("s3")
    prefix = silver_source_prefix(source).rstrip("/") + "/"
    removed: list[str] = []
    token: str | None = None
    while True:
        kwargs: dict[str, Any] = {"Bucket": bucket, "Prefix": prefix, "Delimiter": "/"}
        if token:
            kwargs["ContinuationToken"] = token
        listed = client.list_objects_v2(**kwargs)
        for entry in listed.get("CommonPrefixes") or []:
            raw = str(entry.get("Prefix") or "").strip("/")
            entity = raw.rsplit("/", 1)[-1].strip().lower()
            if not entity or entity in keep:
                continue
            _delete_s3_prefix(client, bucket=bucket, prefix=f"{prefix}{entity}/")
            removed.append(entity)
            logger.info("Pruned unused DNA silver prefix s3://%s/%s%s/", bucket, prefix, entity)
        if not listed.get("IsTruncated"):
            break
        token = listed.get("NextContinuationToken")
    return sorted(removed)


def _delete_s3_prefix(client: Any, *, bucket: str, prefix: str) -> None:
    token: str | None = None
    while True:
        kwargs: dict[str, Any] = {"Bucket": bucket, "Prefix": prefix}
        if token:
            kwargs["ContinuationToken"] = token
        listed = client.list_objects_v2(**kwargs)
        objects = [{"Key": obj["Key"]} for obj in listed.get("Contents") or []]
        if objects:
            client.delete_objects(Bucket=bucket, Delete={"Objects": objects})
        if not listed.get("IsTruncated"):
            return
        token = listed.get("NextContinuationToken")


def _drop_unused_silver_glue(
    *,
    source: str,
    keep: set[str],
    company: str,
    environment: str | None,
    region: str | None,
) -> list[str]:
    from hiveflow.catalog.glue_schema import drop_unused_silver_tables

    return drop_unused_silver_tables(
        source=source,
        keep_entities=keep,
        company=company or None,
        environment=environment,
        region=region,
        layer="silver",
    )


def _copy_s3_entity(*, bucket: str, source: str, entity: str) -> bool:
    import boto3
    from botocore.exceptions import ClientError

    client = boto3.client("s3")
    stg_key = silver_stg_entity_parquet_key(source, entity)
    silver_key = silver_entity_parquet_key(source, entity)
    try:
        client.head_object(Bucket=bucket, Key=stg_key)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in {"404", "NoSuchKey", "NotFound"}:
            return False
        raise
    client.copy_object(
        Bucket=bucket,
        Key=silver_key,
        CopySource={"Bucket": bucket, "Key": stg_key},
    )
    logger.info("Copied s3://%s/%s → s3://%s/%s", bucket, stg_key, bucket, silver_key)
    return True


def _copy_local_entity(*, data_dir: Path, source: str, entity: str) -> bool:
    src = prefix_path(data_dir, silver_stg_entity_prefix(source, entity), "data.parquet")
    if not src.is_file():
        return False
    dest_dir = prefix_path(data_dir, silver_entity_prefix(source, entity))
    dest_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest_dir / "data.parquet")
    return True


def _sync_dna_silver_glue(
    settings: Any,
    *,
    source: str,
    entity: str,
    company: str,
    environment: str | None,
    region: str | None,
) -> bool:
    from hiveflow.catalog.glue_schema import sync_silver_table_schema
    from hiveflow.silver.settings import ConsolidateSettings

    if not settings.s3_bucket:
        return False
    consolidate = ConsolidateSettings(
        source=source,
        data_dir=settings.data_dir,
        s3_bucket=settings.s3_bucket,
    )
    try:
        sync_silver_table_schema(
            consolidate,
            entity,
            company=company or None,
            environment=environment,
            region=region,
            layer="silver",
        )
    except (FileNotFoundError, ValueError) as exc:
        logger.warning(
            "DNA silver catalog sync skipped for %s/%s: %s",
            source,
            entity,
            exc,
        )
        return False
    return True
