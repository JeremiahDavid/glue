"""Copy lake silver/ objects to silver_stg/ for the ingest cutover.

Does not delete silver/. After this copy:

1. Deploy IngestStack (consolidate writes silver_stg)
2. Deploy DnaStack (dna_apply Glue job)
3. Run DNA refresh once so DNA silver/ and gold/dna/ are rewritten

Copies data.parquet, _baseline_fingerprint.json, _sql_staging/,
manifest.json, and silver/{source}/_state/state.json (as
silver_stg/{source}/_state/state.json), plus any legacy flat keys.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap  # noqa: E402, F401

from hiveflow.project_config import (
    DEFAULT_CONFIG_PATH,
    get_environment_config,
    resolve_aws_deploy_env,
    resolve_data_bucket_name,
    resolve_selection,
)


def _caller_account() -> str:
    import boto3

    return str(boto3.client("sts").get_caller_identity()["Account"]).strip()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Copy s3://{bucket}/silver/ → s3://{bucket}/silver_stg/ (no delete)"
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="Project config.yaml (default: config.yaml)",
    )
    parser.add_argument("--company", help="Company slug (defaults from config.yaml)")
    parser.add_argument("--environment", help="Environment slug (defaults from config.yaml)")
    parser.add_argument(
        "--bucket",
        help="Lake bucket (default: HIVEFLOW_S3_BUCKET, else derived from config + STS)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print aws s3 sync command without running it",
    )
    args = parser.parse_args()
    config_path = Path(args.config)

    company, environment = resolve_selection(
        args.company,
        args.environment,
        path=config_path,
    )
    env_config = get_environment_config(company, environment, path=config_path)
    account, region = resolve_aws_deploy_env(env_config, environment)
    bucket = (
        str(args.bucket or "").strip()
        or os.getenv("HIVEFLOW_S3_BUCKET", "").strip()
    )
    if not bucket:
        if not account:
            account = _caller_account()
        bucket = resolve_data_bucket_name(
            company,
            environment,
            account=account,
            region=region,
            path=config_path,
        )
    src = f"s3://{bucket}/silver/"
    dest = f"s3://{bucket}/silver_stg/"
    cmd = ["aws", "s3", "sync", src, dest]
    if region:
        cmd.extend(["--region", region])
    print(" ".join(cmd))
    print("Does not delete silver/. Deploy IngestStack, then DnaStack, then DNA refresh once.")
    if args.dry_run:
        return
    subprocess.check_call(cmd)


if __name__ == "__main__":
    main()
