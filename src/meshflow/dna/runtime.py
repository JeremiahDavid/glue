from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from meshflow.config import DEFAULT_DATA_DIR
from meshflow.dna.settings import DnaSettings
from meshflow.project_config import (
    get_dna_config,
    get_environment_config,
    get_ui_config,
    iter_configured_connectors,
    resolve_aws_deploy_env,
    resolve_dna_source,
    resolve_raw_bucket_name,
    resolve_selection,
)


def resolve_dna_settings(*, event: dict[str, Any] | None = None) -> DnaSettings:
    """Build DNA settings from env vars and optional Lambda/API event overrides."""
    company, environment = resolve_selection()
    ui_mode = os.getenv("MESHFLOW_UI_MODE", "").strip().lower()
    platform_ui = (
        os.getenv("MESHFLOW_PLATFORM_UI", "").strip().lower() in ("1", "true", "yes")
        or ui_mode == "global"
    )

    if platform_ui:
        from meshflow.project_config import get_platform_environment_config

        try:
            env_config = get_platform_environment_config(environment)
        except KeyError:
            env_config = get_environment_config(company, environment)
    else:
        env_config = get_environment_config(company, environment)

    bucket = os.getenv("MESHFLOW_S3_BUCKET", "").strip()
    if not bucket and not platform_ui:
        account, region = resolve_aws_deploy_env(env_config, environment)
        bucket = resolve_raw_bucket_name(company, environment, account=account, region=region)

    dna_cfg = get_dna_config(env_config)
    ui_cfg = get_ui_config(env_config)
    event_payload = event or {}

    source = str(event_payload.get("source", "")).strip().lower()
    if not source:
        source = os.getenv("MESHFLOW_DNA_SOURCE", "").strip().lower()
    if not source:
        source = resolve_dna_source(env_config)

    pack_id = str(
        event_payload.get("pack_id")
        or os.getenv("MESHFLOW_DNA_PACK_ID")
        or ui_cfg.get("pack_id")
        or dna_cfg.get("pack_id")
        or "bc_intra_v1"
    ).strip()

    pack_version = event_payload.get("pack_version") or os.getenv("MESHFLOW_DNA_PACK_VERSION")
    if pack_version is not None:
        pack_version = str(pack_version).strip() or None

    return DnaSettings(
        source=source or "dbc",
        data_dir=Path(os.getenv("MESHFLOW_DATA_DIR", str(DEFAULT_DATA_DIR))),
        s3_bucket=bucket or None,
        pack_id=pack_id,
        pack_version=pack_version,
    )
