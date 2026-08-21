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

    return {"status": "ok", "company": company, "environment": environment, "manifests": manifests}


def lambda_handler(event: dict[str, Any] | None, context: Any) -> dict[str, Any]:
    return handler(event, context)


def _data_dir():
    from pathlib import Path

    from meshflow.config import DEFAULT_DATA_DIR

    return Path(os.getenv("MESHFLOW_DATA_DIR", str(DEFAULT_DATA_DIR)))


def _resolve_aws_env(env_config: dict[str, Any], environment: str) -> tuple[str | None, str | None]:
    from meshflow.project_config import resolve_aws_deploy_env

    return resolve_aws_deploy_env(env_config, environment)
