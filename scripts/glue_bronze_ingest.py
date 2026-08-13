"""Glue Python Shell entry: bronze ingest for one client connector source.

Deployed as the Glue job script; not intended for local ``python scripts/...`` use.
See ``meshflow.ingest.glue_runner`` for the ingest implementation.
"""

from __future__ import annotations

import json
import os
import sys

from awsglue.utils import getResolvedOptions  # type: ignore[import-untyped]

_JOB_ARGS = [
    "JOB_NAME",
    "MESHFLOW_COMPANY",
    "MESHFLOW_ENVIRONMENT",
    "MESHFLOW_SOURCE",
    "MESHFLOW_SECRET_ID",
    "MESHFLOW_S3_BUCKET",
    "MESHFLOW_S3_PREFIX",
    "run_id",
    "full_load",
]


def _apply_job_env(args: dict[str, str]) -> None:
    for key in (
        "MESHFLOW_COMPANY",
        "MESHFLOW_ENVIRONMENT",
        "MESHFLOW_SOURCE",
        "MESHFLOW_SECRET_ID",
        "MESHFLOW_S3_BUCKET",
        "MESHFLOW_S3_PREFIX",
    ):
        value = str(args.get(key, "")).strip()
        if value:
            os.environ[key] = value


def main() -> None:
    args = getResolvedOptions(sys.argv, _JOB_ARGS)
    _apply_job_env(args)

    run_id = str(args["run_id"]).strip()
    if not run_id:
        raise ValueError("run_id is required")

    full_load = str(args.get("full_load", "false")).strip().lower() in {"1", "true", "yes"}

    from meshflow.ingest.glue_runner import run_bronze_ingest_glue

    manifest = run_bronze_ingest_glue(run_id=run_id, full_load=full_load)
    summary = {
        "status": "ok",
        "run_id": run_id,
        "manifest_path": manifest.get("manifest_path"),
        "ingest_summary": manifest.get("ingest_summary"),
    }
    print(json.dumps(summary, default=str))


if __name__ == "__main__":
    main()
