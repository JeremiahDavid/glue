from __future__ import annotations

from typing import Any

from meshflow.dna.compile import compile_pack
from meshflow.dna.publish import publish_staging
from meshflow.dna.settings import DnaSettings
from meshflow.dna.validate import run_validation
from meshflow.dna.workflow import load_production_pack


def run_dna_pipeline(settings: DnaSettings) -> dict[str, Any]:
    pack = load_production_pack(settings)
    compile_manifest = compile_pack(settings, pack)
    validation_result = run_validation(settings, pack)
    if validation_result["status"] != "passed":
        return {
            "status": "validation_failed",
            "compile": compile_manifest,
            "validation": validation_result,
        }
    publish_manifest = publish_staging(
        settings,
        compile_manifest=compile_manifest,
        validation_result=validation_result,
    )
    return {
        "status": "published",
        "compile": compile_manifest,
        "validation": validation_result,
        "publish": publish_manifest,
    }


def handler(event: dict[str, Any] | None, _context: Any) -> dict[str, Any]:
    import os
    from pathlib import Path

    from meshflow.config import DEFAULT_DATA_DIR
    from meshflow.project_config import (
        get_environment_config,
        iter_configured_connectors,
        resolve_raw_bucket_name,
        resolve_selection,
    )

    company, environment = resolve_selection()
    env_config = get_environment_config(company, environment)
    bucket = os.getenv("MESHFLOW_S3_BUCKET", "").strip()
    if not bucket:
        from meshflow.project_config import resolve_aws_deploy_env

        account, region = resolve_aws_deploy_env(env_config, environment)
        bucket = resolve_raw_bucket_name(company, environment, account=account, region=region)

    connectors = list(iter_configured_connectors(env_config))
    source = str((event or {}).get("source", "")).strip().lower()
    if not source:
        for connector, _cfg in connectors:
            if connector == "dbc":
                source = connector
                break
        if not source and connectors:
            source = connectors[0][0]

    settings = DnaSettings(
        source=source or "dbc",
        data_dir=Path(os.getenv("MESHFLOW_DATA_DIR", str(DEFAULT_DATA_DIR))),
        s3_bucket=bucket or None,
        pack_id=str((event or {}).get("pack_id", "bc_intra_v1")),
        pack_version=(event or {}).get("pack_version"),
    )
    action = str((event or {}).get("action", "publish")).strip().lower()
    pack = load_production_pack(settings)

    if action == "compile":
        return compile_pack(settings, pack)
    if action == "validate":
        compile_pack(settings, pack)
        return run_validation(settings, pack)
    if action == "publish":
        return run_dna_pipeline(settings)
    raise ValueError(f"Unknown DNA action {action!r}")


def lambda_handler(event: dict[str, Any] | None, context: Any) -> dict[str, Any]:
    return handler(event, context)
