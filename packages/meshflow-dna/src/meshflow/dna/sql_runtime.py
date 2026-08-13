"""Deterministic Athena replay of pinned SQL packs (no AI)."""

from __future__ import annotations

import logging
from typing import Any

from meshflow.dna.settings import DnaSettings
from meshflow.dna.sql_pack import (
    SqlPack,
    SqlTransform,
    load_sql_pack,
    load_transform_sql,
    ordered_transforms,
)
from meshflow.storage.paths import (
    gold_dna_entity_parquet_key,
    gold_dna_sql_staging_prefix,
    silver_entity_parquet_key,
    silver_sql_staging_prefix,
)

logger = logging.getLogger(__name__)


def apply_silver_sql_pack(
    settings: DnaSettings,
    *,
    source: str | None = None,
    company: str | None = None,
    environment: str | None = None,
    region: str | None = None,
) -> dict[str, Any]:
    """Replay pinned silver transforms after consolidate. No-op if no SQL pack."""
    pack = load_sql_pack(settings)
    if pack is None:
        return {"status": "skipped", "reason": "no_sql_pack", "applied": []}
    transforms = ordered_transforms(pack.by_layer("silver"))
    if not transforms:
        return {"status": "skipped", "reason": "no_silver_transforms", "applied": []}
    if not settings.s3_bucket:
        return {"status": "skipped", "reason": "no_s3_bucket", "applied": []}

    src = (source or settings.source).strip().lower()
    applied: list[dict[str, Any]] = []
    database, workgroup, resolved_region = _athena_targets(
        company=company or settings.company,
        environment=environment,
        region=region,
    )
    for transform in transforms:
        result = _materialize_silver_transform(
            settings,
            transform,
            pack=pack,
            source=src,
            database=database,
            workgroup=workgroup,
            region=resolved_region,
            company=company or settings.company,
            environment=environment,
        )
        applied.append(result)
    return {
        "status": "ok",
        "pack_version": pack.version,
        "applied": applied,
    }


def apply_gold_sql_pack(
    settings: DnaSettings,
    *,
    company: str | None = None,
    environment: str | None = None,
    region: str | None = None,
) -> dict[str, Any]:
    """Replay pinned gold fact/KPI SQL. No-op if none."""
    pack = load_sql_pack(settings)
    if pack is None:
        return {"status": "skipped", "reason": "no_sql_pack", "applied": []}
    transforms = ordered_transforms(pack.by_layer("gold"))
    if not transforms:
        return {"status": "skipped", "reason": "no_gold_transforms", "applied": []}
    if not settings.s3_bucket:
        return {"status": "skipped", "reason": "no_s3_bucket", "applied": []}

    applied: list[dict[str, Any]] = []
    database, workgroup, resolved_region = _athena_targets(
        company=company or settings.company,
        environment=environment,
        region=region,
    )
    for transform in transforms:
        result = _materialize_gold_transform(
            settings,
            transform,
            pack=pack,
            database=database,
            workgroup=workgroup,
            region=resolved_region,
            company=company or settings.company,
            environment=environment,
        )
        applied.append(result)
    return {
        "status": "ok",
        "pack_version": pack.version,
        "applied": applied,
    }


def has_gold_sql(settings: DnaSettings) -> bool:
    pack = load_sql_pack(settings)
    return bool(pack and pack.by_layer("gold"))


def _materialize_silver_transform(
    settings: DnaSettings,
    transform: SqlTransform,
    *,
    pack: SqlPack,
    source: str,
    database: str,
    workgroup: str,
    region: str | None,
    company: str,
    environment: str | None,
) -> dict[str, Any]:
    from meshflow.athena import materialize_select_to_prefix

    entity = str(transform.target_entity or "").strip().lower()
    sql = load_transform_sql(
        settings,
        transform,
        pack_id=settings.dna_config_id,
        version=pack.version,
        verify_checksum=True,
    )
    if transform.mode == "add_columns":
        from meshflow.dna.silver_enhancement import prepare_add_columns_sql_for_replay
        from meshflow.project_config import catalog_table_name

        sql = prepare_add_columns_sql_for_replay(
            sql,
            database=database,
            table_name=catalog_table_name("silver", source, entity),
            region=region,
        )
    staging = silver_sql_staging_prefix(source, entity, transform.id)
    staging_uri = f"s3://{settings.s3_bucket}/{staging}"
    unload = materialize_select_to_prefix(
        sql,
        s3_output_prefix=staging_uri,
        database=database,
        workgroup=workgroup,
        region=region,
    )
    target_key = silver_entity_parquet_key(source, entity)
    _coalesce_unload_to_parquet(
        bucket=settings.s3_bucket or "",
        staging_prefix=staging,
        target_key=target_key,
    )
    _sync_silver_glue(
        settings,
        source=source,
        entity=entity,
        company=company,
        environment=environment,
        region=region,
    )
    return {
        "id": transform.id,
        "layer": "silver",
        "entity": entity,
        "target_key": target_key,
        "execution_id": unload.get("execution_id"),
    }


def _materialize_gold_transform(
    settings: DnaSettings,
    transform: SqlTransform,
    *,
    pack: SqlPack,
    database: str,
    workgroup: str,
    region: str | None,
    company: str,
    environment: str | None,
) -> dict[str, Any]:
    from meshflow.athena import materialize_select_to_prefix

    output_id = str(transform.output_id or "").strip().lower()
    sql = load_transform_sql(
        settings,
        transform,
        pack_id=settings.dna_config_id,
        version=pack.version,
        verify_checksum=True,
    )
    staging = gold_dna_sql_staging_prefix(transform.id)
    staging_uri = f"s3://{settings.s3_bucket}/{staging}"
    unload = materialize_select_to_prefix(
        sql,
        s3_output_prefix=staging_uri,
        database=database,
        workgroup=workgroup,
        region=region,
    )
    target_key = gold_dna_entity_parquet_key(output_id)
    _coalesce_unload_to_parquet(
        bucket=settings.s3_bucket or "",
        staging_prefix=staging,
        target_key=target_key,
    )
    _sync_dna_glue(
        settings,
        output_id=output_id,
        company=company,
        environment=environment,
        region=region,
    )
    return {
        "id": transform.id,
        "layer": "gold",
        "output_id": output_id,
        "target_key": target_key,
        "execution_id": unload.get("execution_id"),
    }


def _coalesce_unload_to_parquet(*, bucket: str, staging_prefix: str, target_key: str) -> None:
    """Read Athena UNLOAD parts and write a single data.parquet at the canonical key."""
    import io

    import boto3
    import pyarrow as pa
    import pyarrow.parquet as pq

    s3 = boto3.client("s3")
    prefix = staging_prefix.rstrip("/") + "/"
    listed = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
    keys = [
        obj["Key"]
        for obj in listed.get("Contents") or []
        if str(obj["Key"]).endswith(".parquet") or "/data." in str(obj["Key"]) or str(obj["Key"]).endswith(".gz")
    ]
    # Athena UNLOAD typically writes extension-less or .parquet parts under the prefix.
    if not keys:
        keys = [obj["Key"] for obj in listed.get("Contents") or [] if not str(obj["Key"]).endswith("/")]
    if not keys:
        raise FileNotFoundError(f"No UNLOAD parts under s3://{bucket}/{prefix}")

    tables: list[pa.Table] = []
    for key in sorted(keys):
        obj = s3.get_object(Bucket=bucket, Key=key)
        body = obj["Body"].read()
        if not body:
            continue
        tables.append(pq.read_table(io.BytesIO(body)))
    if not tables:
        raise FileNotFoundError(f"Empty UNLOAD parts under s3://{bucket}/{prefix}")
    merged = pa.concat_tables(tables, promote_options="default")
    buf = io.BytesIO()
    pq.write_table(merged, buf, compression="snappy")
    s3.put_object(Bucket=bucket, Key=target_key, Body=buf.getvalue())
    # Best-effort cleanup of staging parts.
    for key in keys:
        try:
            s3.delete_object(Bucket=bucket, Key=key)
        except Exception:  # noqa: BLE001
            logger.warning("Failed to delete staging object s3://%s/%s", bucket, key)


def _sync_silver_glue(
    settings: DnaSettings,
    *,
    source: str,
    entity: str,
    company: str,
    environment: str | None,
    region: str | None,
) -> None:
    from meshflow.catalog.glue_schema import sync_silver_table_schema
    from meshflow.silver.settings import ConsolidateSettings

    consolidate = ConsolidateSettings(
        source=source,
        data_dir=settings.data_dir,
        s3_bucket=settings.s3_bucket,
    )
    sync_silver_table_schema(
        consolidate,
        entity,
        company=company or None,
        environment=environment,
        region=region,
    )


def _sync_dna_glue(
    settings: DnaSettings,
    *,
    output_id: str,
    company: str,
    environment: str | None,
    region: str | None,
) -> None:
    from meshflow.catalog.glue_schema import sync_dna_output_schema

    if not settings.s3_bucket:
        return
    sync_dna_output_schema(
        bucket=settings.s3_bucket,
        output_id=output_id,
        company=company or None,
        environment=environment,
        region=region,
    )


def _athena_targets(
    *,
    company: str,
    environment: str | None,
    region: str | None,
) -> tuple[str, str, str | None]:
    from meshflow.project_config import (
        athena_workgroup_name,
        get_environment_config,
        glue_database_name,
        resolve_aws_deploy_env,
        resolve_selection,
    )

    resolved_company = (company or "").strip()
    resolved_env = (environment or "").strip()
    if not resolved_company or not resolved_env:
        sel_company, sel_env = resolve_selection()
        resolved_company = resolved_company or sel_company
        resolved_env = resolved_env or sel_env
    database = glue_database_name(resolved_company, resolved_env)
    workgroup = athena_workgroup_name(resolved_company, resolved_env)
    resolved_region = region
    if not resolved_region:
        try:
            env_config = get_environment_config(resolved_company, resolved_env)
            _account, resolved_region = resolve_aws_deploy_env(env_config, resolved_env)
        except Exception:  # noqa: BLE001
            resolved_region = None
    return database, workgroup, resolved_region
