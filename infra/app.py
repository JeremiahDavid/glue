#!/usr/bin/env python3
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from typing import Any

INFRA_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = INFRA_DIR.parent
sys.path.insert(0, str(INFRA_DIR))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import aws_cdk as cdk
from cdk_scope import resolve_cdk_scope
from meshflow.project_config import (
    dna_stack_module_name,
    dna_stack_name,
    get_dna_config,
    get_platform_config,
    get_ui_config,
    global_dns_stack_module_name,
    global_dns_stack_name,
    global_ui_stack_module_name,
    global_ui_stack_name,
    global_ui_web_api_export_name,
    ingest_stack_module_name,
    ingest_stack_name,
    is_dna_stack_enabled,
    is_platform_ui_enabled,
    is_global_dns_stack_enabled,
    iter_cdk_deploy_targets,
    iter_configured_connectors,
    iter_platform_deploy_environments,
    iter_portal_reporting_clients,
    reporting_stack_module_name,
    reporting_stack_name,
    reporting_web_api_export_name,
    resolve_aws_deploy_env,
    resolve_data_bucket_name,
    resolve_dna_source,
    resolve_portal_client_buckets,
    resolve_qbo_secret_name,
)

app = cdk.App()


def _resolve_web_api_id(*, context_key: str, export_name: str) -> str:
    """Use a CDK context override during migration, otherwise import a stable stack export."""
    override = app.node.try_get_context(context_key)
    if override:
        return str(override).strip()
    return cdk.Fn.import_value(export_name)


def _reporting_web_api_context_key(client_id: str) -> str:
    slug = client_id.strip().lower().replace("_", "-")
    return f"{slug}ReportingWebApiId"


def _dns_manage_base_path_mappings() -> bool:
    value = app.node.try_get_context("dnsManageBasePathMappings")
    if value is None:
        return True
    return str(value).strip().lower() not in ("0", "false", "no")

filter_company = app.node.try_get_context("company") or os.getenv("MESHFLOW_COMPANY")
filter_environment = app.node.try_get_context("environment") or os.getenv("MESHFLOW_ENVIRONMENT")
cdk_scope = resolve_cdk_scope(
    context=app.node.try_get_context("scope"),
    env=os.getenv("MESHFLOW_CDK_SCOPE"),
)

platform_config = get_platform_config()
platform_enabled = bool(platform_config.get("environments"))

if cdk_scope in ("all", "ingest"):
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
                description=f"Meshflow DNA semantic engine for {company}/{environment}",
            )

if cdk_scope in ("all", "platform") and platform_enabled:
    global_ui_module = importlib.import_module(f"stacks.{global_ui_stack_module_name()}")
    global_dns_module = importlib.import_module(f"stacks.{global_dns_stack_module_name()}")
    reporting_module = importlib.import_module(f"stacks.{reporting_stack_module_name()}")

    for environment, platform_env_config in iter_platform_deploy_environments():
        if filter_environment and environment != filter_environment:
            continue

        account, region = resolve_aws_deploy_env(platform_env_config, environment)
        ui_config = get_ui_config(platform_env_config)
        dns_stack_enabled = is_global_dns_stack_enabled(platform_env_config)
        client_buckets = resolve_portal_client_buckets(
            platform_env_config,
            environment,
            account=account,
            region=region,
        )

        global_ui_stack = None
        if is_platform_ui_enabled(platform_env_config):
            global_ui_stack = global_ui_module.GlobalUiStack(
                app,
                global_ui_stack_name(environment),
                environment=environment,
                ui_config=ui_config,
                client_buckets=client_buckets,
                env=cdk.Environment(
                    account=account,
                    region=region,
                ),
                description=f"Global HiveFlowAI UI for {environment}",
            )

        reporting_stacks: list[tuple[str, dict, Any]] = []
        for client_id, reporting_company, client_cfg in iter_portal_reporting_clients(platform_env_config):
            if filter_company and reporting_company != filter_company:
                continue

            company_env_config = None
            try:
                from meshflow.project_config import get_environment_config

                company_env_config = get_environment_config(reporting_company, environment)
            except KeyError:
                continue

            if not is_dna_stack_enabled(company_env_config):
                continue

            if global_ui_stack is None:
                continue

            reporting_bucket = resolve_data_bucket_name(
                reporting_company,
                environment,
                account=account,
                region=region,
            )
            reporting_stack = reporting_module.ReportingStack(
                app,
                reporting_stack_name(client_id, environment),
                client_id=client_id,
                company=reporting_company,
                environment=environment,
                data_bucket_name=reporting_bucket,
                source=resolve_dna_source(company_env_config),
                client_config=client_cfg,
                dna_config=get_dna_config(company_env_config),
                portal_user_pool=global_ui_stack.portal_user_pool,
                portal_user_pool_client=global_ui_stack.portal_user_pool_client,
                portal_session_secret=global_ui_stack.portal_session_secret,
                domain_config=ui_config.get("domain", {}) if isinstance(ui_config.get("domain"), dict) else {},
                env=cdk.Environment(
                    account=account,
                    region=region,
                ),
                description=(
                    f"Portal reporting UI for client {client_id} "
                    f"({reporting_company}/{environment})"
                ),
            )
            reporting_stacks.append((client_id, client_cfg, reporting_stack))

        if dns_stack_enabled:
            from stacks.global_dns_stack import ReportingDnsTarget

            global_dns_module.GlobalDnsStack(
                app,
                global_dns_stack_name(environment),
                environment=environment,
                ui_config=ui_config,
                global_rest_api_id=_resolve_web_api_id(
                    context_key="globalWebApiId",
                    export_name=global_ui_web_api_export_name(environment),
                ),
                reporting_targets=[
                    ReportingDnsTarget(
                        rest_api_id=_resolve_web_api_id(
                            context_key=_reporting_web_api_context_key(client_id),
                            export_name=reporting_web_api_export_name(client_id, environment),
                        ),
                        client_id=client_id,
                        reporting_hostname=str(client_cfg.get("reporting_hostname", client_id)).strip().lower(),
                    )
                    for client_id, client_cfg, _reporting_stack in reporting_stacks
                ],
                manage_base_path_mappings=_dns_manage_base_path_mappings(),
                env=cdk.Environment(
                    account=account,
                    region=region,
                ),
                description=f"HiveFlowAI public DNS for {environment}",
            )

app.synth()
