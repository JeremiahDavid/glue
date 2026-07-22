#!/usr/bin/env python3
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

INFRA_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = INFRA_DIR.parent
sys.path.insert(0, str(INFRA_DIR))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import aws_cdk as cdk
from meshflow.project_config import (
    ingest_stack_module_name,
    ingest_stack_name,
    iter_cdk_deploy_targets,
    resolve_aws_deploy_env,
    resolve_ingest_s3_prefix,
    resolve_qbo_secret_name,
    resolve_raw_bucket_name,
)

app = cdk.App()

filter_company = app.node.try_get_context("company") or os.getenv("MESHFLOW_COMPANY")
filter_environment = app.node.try_get_context("environment") or os.getenv("MESHFLOW_ENVIRONMENT")

for company, environment, env_config in iter_cdk_deploy_targets(
    company=filter_company,
    environment=filter_environment,
):
    stack_id = ingest_stack_name(company, environment)
    module_name = ingest_stack_module_name(company)
    try:
        stack_module = importlib.import_module(f"stacks.{module_name}")
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            f"No ingest stack module 'stacks/{module_name}.py' for company {company!r}. "
            "Expected file name pattern: ingeststack_<company>.py"
        ) from exc

    ingest_cfg = env_config.get("ingest", {})
    schedule_cfg = ingest_cfg.get("schedule", {}) if isinstance(ingest_cfg, dict) else {}

    account, region = resolve_aws_deploy_env(env_config, environment)
    qbo_secret_name = resolve_qbo_secret_name(company, environment)
    raw_bucket_name = resolve_raw_bucket_name(
        company,
        environment,
        account=account,
        region=region,
    )
    s3_prefix = resolve_ingest_s3_prefix(company, environment)

    stack_module.IngestStack(
        app,
        stack_id,
        company=company,
        environment=environment,
        qbo_secret_name=qbo_secret_name,
        raw_bucket_name=raw_bucket_name,
        s3_prefix=s3_prefix,
        schedule_hour=int(schedule_cfg.get("hour", 6)),
        schedule_minute=int(schedule_cfg.get("minute", 0)),
        env=cdk.Environment(
            account=account,
            region=region,
        ),
        description=f"Meshflow raw ingest for {company} ({environment})",
    )

app.synth()
