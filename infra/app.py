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
    dna_stack_module_name,
    dna_stack_name,
    get_dna_config,
    get_ui_config,
    ingest_stack_module_name,
    ingest_stack_name,
    is_dna_stack_enabled,
    is_ui_stack_enabled,
    iter_cdk_deploy_targets,
    iter_configured_connectors,
    resolve_aws_deploy_env,
    resolve_data_bucket_name,
    resolve_dna_source,
    resolve_qbo_secret_name,
    ui_stack_module_name,
    ui_stack_name,
)

app = cdk.App()

filter_company = app.node.try_get_context("company") or os.getenv("MESHFLOW_COMPANY")
filter_environment = app.node.try_get_context("environment") or os.getenv("MESHFLOW_ENVIRONMENT")

for company, environment, env_config in iter_cdk_deploy_targets(
    company=filter_company,
    environment=filter_environment,
):
    connectors = list(iter_configured_connectors(env_config))
    if not connectors:
        continue

    account, region = resolve_aws_deploy_env(env_config, environment)
    raw_bucket_name = resolve_data_bucket_name(
        company,
        environment,
        account=account,
        region=region,
    )

    stack_id = ingest_stack_name(company, environment)
    module_name = ingest_stack_module_name(company)
    try:
        stack_module = importlib.import_module(f"stacks.{module_name}")
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            f"No ingest stack module 'stacks/{module_name}.py' for company {company!r}. "
            "Expected file name pattern: ingeststack_<company>.py"
        ) from exc

    secret_names = {
        connector: resolve_qbo_secret_name(company, environment, source=connector)
        for connector, _ in connectors
    }

    stack_module.IngestStack(
        app,
        stack_id,
        company=company,
        environment=environment,
        raw_bucket_name=raw_bucket_name,
        connectors=connectors,
        secret_names=secret_names,
        env=cdk.Environment(
            account=account,
            region=region,
        ),
        description=f"Meshflow raw ingest for {company} ({environment})",
    )

    if is_dna_stack_enabled(env_config):
        dna_module_name = dna_stack_module_name(company)
        try:
            dna_module = importlib.import_module(f"stacks.{dna_module_name}")
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                f"No DNA stack module 'stacks/{dna_module_name}.py' for company {company!r}. "
                "Expected file name pattern: dnastack_<company>.py"
            ) from exc

        dna_module.DnaStack(
            app,
            dna_stack_name(company, environment),
            company=company,
            environment=environment,
            data_bucket_name=raw_bucket_name,
            source=resolve_dna_source(env_config),
            dna_config=get_dna_config(env_config),
            env=cdk.Environment(
                account=account,
                region=region,
            ),
            description=f"Meshflow DNA semantic engine for {company} ({environment})",
        )

    if is_ui_stack_enabled(env_config):
        ui_module_name = ui_stack_module_name(company)
        try:
            ui_module = importlib.import_module(f"stacks.{ui_module_name}")
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                f"No UI stack module 'stacks/{ui_module_name}.py' for company {company!r}. "
                "Expected file name pattern: uistack_<company>.py"
            ) from exc

        ui_module.UiStack(
            app,
            ui_stack_name(company, environment),
            company=company,
            environment=environment,
            data_bucket_name=raw_bucket_name,
            source=resolve_dna_source(env_config),
            ui_config=get_ui_config(env_config),
            dna_config=get_dna_config(env_config),
            env=cdk.Environment(
                account=account,
                region=region,
            ),
            description=f"Meshflow DNA reporting UI for {company} ({environment})",
        )

app.synth()
