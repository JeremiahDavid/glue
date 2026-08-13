from __future__ import annotations

from typing import Any

from meshflow.ingest.storage import resolve_run_path, run_stamp


def prepare_ingest_run(*, full_load: bool = False) -> dict[str, Any]:
    """Build shared run metadata for a bronze Glue ingest execution."""
    from meshflow.project_config import (
        get_connector_config,
        get_environment_config,
        resolve_fanout_entity_names,
        resolve_ingest_connector,
        resolve_selection,
    )

    company, environment = resolve_selection()
    connector = resolve_ingest_connector()
    env_config = get_environment_config(company, environment)
    connector_cfg = get_connector_config(env_config, connector)
    if not connector_cfg:
        ingest_cfg = env_config.get("ingest", {})
        connector_cfg = ingest_cfg if isinstance(ingest_cfg, dict) else {}

    entities = resolve_fanout_entity_names(connector, connector_cfg)
    if not entities:
        raise ValueError(f"No ingest entities configured for connector {connector!r}")

    if connector == "qbo":
        from meshflow.config import load_qbo_settings
        from meshflow.qbo.oauth import ensure_access_token

        ensure_access_token(load_qbo_settings())

    return {
        "run_id": run_stamp(),
        "entities": entities,
        "full_load": full_load,
        "connector": connector,
        "company": company,
        "environment": environment,
    }


def finalize_ingest_from_manifest(*, run_id: str) -> dict[str, Any]:
    """Load manifest.json written by a Glue bronze ingest job."""
    from meshflow.ingest.storage import read_json_s3
    from meshflow.project_config import resolve_ingest_connector

    connector = resolve_ingest_connector()
    if connector == "qbo":
        from meshflow.config import load_qbo_settings

        settings = load_qbo_settings()
    elif connector == "dbc":
        from meshflow.config import load_bc_settings

        settings = load_bc_settings()
    else:
        raise ValueError(f"Unsupported connector for manifest finalize: {connector!r}")

    if not settings.s3_bucket:
        raise ValueError("MESHFLOW_S3_BUCKET must be set for ingest manifest finalize")

    run_path = resolve_run_path(settings, run_id)
    manifest = read_json_s3(settings.s3_bucket, f"{run_path}/manifest.json")
    if manifest is None:
        raise FileNotFoundError(
            f"Bronze manifest not found at s3://{settings.s3_bucket}/{run_path}/manifest.json"
        )
    return manifest
