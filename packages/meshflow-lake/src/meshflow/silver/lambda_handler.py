from __future__ import annotations

import os
from typing import Any

from meshflow.project_config import (
    get_environment_config,
    iter_configured_connectors,
    resolve_ingest_s3_prefix,
    resolve_raw_bucket_name,
    resolve_selection,
)
from meshflow.silver.consolidate import consolidate_source
from meshflow.silver.settings import ConsolidateSettings


def handler(event: dict[str, Any] | None, _context: Any) -> dict[str, Any]:
    """Consolidate bronze parquet runs for all configured connectors in this environment."""
    company, environment = resolve_selection()
    env_config = get_environment_config(company, environment)
    bucket = os.getenv("MESHFLOW_S3_BUCKET", "").strip()
    if not bucket:
        account, region = _resolve_aws_env(env_config, environment)
        bucket = resolve_raw_bucket_name(company, environment, account=account, region=region)
    if not bucket:
        raise ValueError("MESHFLOW_S3_BUCKET must be set for Lambda consolidation")

    full_rebuild = bool((event or {}).get("full_rebuild"))
    requested_source = str((event or {}).get("source", "")).strip().lower()
    connectors = list(iter_configured_connectors(env_config))
    if requested_source:
        connectors = [item for item in connectors if item[0] == requested_source]
        if not connectors:
            raise ValueError(f"Connector {requested_source!r} is not configured for {company}/{environment}")

    manifests: dict[str, Any] = {}
    for connector, _connector_cfg in connectors:
        prefix = resolve_ingest_s3_prefix(company, environment, source=connector)
        settings = ConsolidateSettings(
            source=connector,
            data_dir=_data_dir(),
            s3_bucket=bucket,
            raw_prefix=prefix,
        )
        manifests[connector] = consolidate_source(settings, full_rebuild=full_rebuild)

    # Deterministic replay of pinned silver SQL (DNA governance pack). No AI.
    silver_sql: dict[str, Any] = {"status": "skipped", "reason": "not_run"}
    profile_keys: dict[str, str] = {}
    baseline_keys: dict[str, dict[str, str]] = {}
    try:
        from meshflow.dna.runtime import resolve_dna_settings
        from meshflow.dna.silver_integrity import snapshot_silver_baselines
        from meshflow.dna.sql_runtime import apply_silver_sql_pack
        from meshflow.entity_registry import catalog_entity_names
        from meshflow.silver.schema_profile import (
            build_silver_schema_profile,
            write_silver_schema_profile,
        )

        for connector, connector_cfg in connectors:
            dna_settings = resolve_dna_settings(
                event={
                    "source": connector,
                    "company": company,
                    "action": "apply-silver-sql",
                }
            )
            dna_settings.s3_bucket = bucket
            consolidate_manifest = manifests.get(connector) or {}
            entities = catalog_entity_names(connector, connector_cfg or {})
            entity_names = [
                str(item.get("entity") or "").strip().lower()
                for item in (consolidate_manifest.get("entities") or [])
                if isinstance(item, dict) and str(item.get("entity") or "").strip()
            ]
            if not entity_names:
                entity_names = list(entities)
            baseline_keys[connector] = snapshot_silver_baselines(
                dna_settings,
                source=connector,
                entities=entity_names,
            )
            silver_sql = apply_silver_sql_pack(
                dna_settings,
                source=connector,
                company=company,
                environment=environment,
            )
            if connector in manifests and isinstance(manifests[connector], dict):
                manifests[connector]["silver_sql"] = silver_sql
                manifests[connector]["silver_baselines"] = baseline_keys.get(connector) or {}

            consolidate_manifest = manifests.get(connector) or {}
            prefix = resolve_ingest_s3_prefix(company, environment, source=connector)
            profile_settings = ConsolidateSettings(
                source=connector,
                data_dir=_data_dir(),
                s3_bucket=bucket,
                raw_prefix=prefix,
            )
            entities = catalog_entity_names(connector, connector_cfg or {})
            sql_pack_version = str(silver_sql.get("pack_version") or "").strip() or None
            profile = build_silver_schema_profile(
                profile_settings,
                entities,
                consolidated_at=str(consolidate_manifest.get("consolidated_at") or ""),
                silver_sql_pack_version=sql_pack_version,
                entity_results=list(consolidate_manifest.get("entities") or []),
            )
            profile_key = write_silver_schema_profile(bucket, connector, profile)
            profile_keys[connector] = profile_key
            if isinstance(manifests.get(connector), dict):
                manifests[connector]["silver_schema_profile_key"] = profile_key
    except Exception as exc:  # noqa: BLE001
        silver_sql = {"status": "error", "error": str(exc)}
        raise

    return {
        "status": "ok",
        "company": company,
        "environment": environment,
        "manifests": manifests,
        "silver_sql": silver_sql,
        "silver_schema_profile_keys": profile_keys,
    }


def lambda_handler(event: dict[str, Any] | None, context: Any) -> dict[str, Any]:
    return handler(event, context)


def _data_dir():
    from pathlib import Path

    from meshflow.config import DEFAULT_DATA_DIR

    return Path(os.getenv("MESHFLOW_DATA_DIR", str(DEFAULT_DATA_DIR)))


def _resolve_aws_env(env_config: dict[str, Any], environment: str) -> tuple[str | None, str | None]:
    from meshflow.project_config import resolve_aws_deploy_env

    return resolve_aws_deploy_env(env_config, environment)
