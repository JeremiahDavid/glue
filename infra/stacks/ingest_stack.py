from __future__ import annotations

from typing import Any

from aws_cdk import (
    CfnOutput,
    RemovalPolicy,
    Stack,
    Tags,
    aws_s3 as s3,
    aws_secretsmanager as secretsmanager,
)
from constructs import Construct

from athena_catalog import create_athena_catalog
from iam_grants import grant_glue_catalog_sync
from lambda_bundle import LocalPythonBundling, HiveFlowLambdaRuntime, hiveflow_lambda_runtime
from qbd_soap import create_qbd_soap_endpoint

# Backward-compatible alias for tests or imports referencing the ingest stack bundler.
_LocalPythonBundling = LocalPythonBundling


class IngestStack(Stack):
    """Company ingest stack: shared S3 landing zone and per-connector compute."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        company: str,
        environment: str,
        raw_bucket_name: str,
        connectors: list[tuple[str, dict[str, Any]]],
        secret_names: dict[str, str],
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        if not raw_bucket_name.strip():
            raise ValueError(
                "Could not derive raw S3 bucket name from config.yaml for this company/environment"
            )
        if not connectors:
            raise ValueError(
                f"No connectors configured for {company}/{environment}. "
                "Add qbo and/or qbd blocks under companies.*.environments.* in config.yaml."
            )

        self._apply_cost_allocation_tags(company, environment)

        raw_bucket = s3.Bucket(
            self,
            "RawDataBucket",
            bucket_name=raw_bucket_name,
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            versioned=True,
            removal_policy=RemovalPolicy.RETAIN,
        )

        lambda_runtime = hiveflow_lambda_runtime(self)
        from glue_bundle import hiveflow_glue_bronze_assets, hiveflow_glue_extra_py_files_asset, hiveflow_glue_silver_assets

        glue_extra_py_files = hiveflow_glue_extra_py_files_asset(self)
        glue_bronze_assets = hiveflow_glue_bronze_assets(self, extra_py_files_asset=glue_extra_py_files)
        glue_silver_assets = hiveflow_glue_silver_assets(self, extra_py_files_asset=glue_extra_py_files)

        consolidate_glue = self._create_consolidate_glue_job(
            raw_bucket=raw_bucket,
            glue_assets=glue_silver_assets,
            company=company,
            environment=environment,
        )

        for connector, connector_cfg in connectors:
            secret_name = secret_names.get(connector, "").strip()
            if not secret_name:
                raise ValueError(
                    f"Could not derive secret name for connector {connector!r} "
                    f"({company}/{environment})"
                )

            credentials_secret = secretsmanager.Secret.from_secret_name_v2(
                self,
                f"{connector.title()}Credentials",
                secret_name,
            )
            common_env = {
                "HIVEFLOW_COMPANY": company,
                "HIVEFLOW_ENVIRONMENT": environment,
                "HIVEFLOW_SOURCE": connector,
                "HIVEFLOW_SECRET_ID": secret_name,
                "HIVEFLOW_S3_BUCKET": raw_bucket.bucket_name,
                "HIVEFLOW_S3_PREFIX": f"raw/{connector}",
            }

            if connector == "qbd":
                self._create_qbd_soap(
                    raw_bucket=raw_bucket,
                    credentials_secret=credentials_secret,
                    lambda_runtime=lambda_runtime,
                    common_env=common_env,
                    company=company,
                    environment=environment,
                    secret_name=secret_name,
                )
                self._create_refresh_pipeline(
                    construct_id="Qbd",
                    connector=connector,
                    company=company,
                    environment=environment,
                    consolidate_glue_job_name=consolidate_glue["glue_job_name"],
                    consolidate_glue_job=consolidate_glue["glue_job"],
                    consolidate_glue_default_arguments=consolidate_glue["default_arguments"],
                    raw_bucket=raw_bucket,
                    credentials_secret=None,
                    lambda_runtime=None,
                    common_env=None,
                    secret_name=secret_name,
                    schedule_hour=None,
                    schedule_minute=None,
                )
                continue

            if connector == "qbo":
                schedule_cfg = connector_cfg.get("schedule", {})
                if not isinstance(schedule_cfg, dict):
                    schedule_cfg = {}
                self._create_refresh_pipeline(
                    construct_id="Qbo",
                    connector=connector,
                    company=company,
                    environment=environment,
                    consolidate_glue_job_name=consolidate_glue["glue_job_name"],
                    consolidate_glue_job=consolidate_glue["glue_job"],
                    consolidate_glue_default_arguments=consolidate_glue["default_arguments"],
                    raw_bucket=raw_bucket,
                    credentials_secret=credentials_secret,
                    lambda_runtime=lambda_runtime,
                    common_env=common_env,
                    secret_name=secret_name,
                    connector_cfg=connector_cfg,
                    glue_bronze_assets=glue_bronze_assets,
                    schedule_hour=int(schedule_cfg.get("hour", 6)),
                    schedule_minute=int(schedule_cfg.get("minute", 0)),
                )
                continue

            if connector == "dbc":
                schedule_cfg = connector_cfg.get("schedule", {})
                if not isinstance(schedule_cfg, dict):
                    schedule_cfg = {}
                self._create_refresh_pipeline(
                    construct_id="Dbc",
                    connector=connector,
                    company=company,
                    environment=environment,
                    consolidate_glue_job_name=consolidate_glue["glue_job_name"],
                    consolidate_glue_job=consolidate_glue["glue_job"],
                    consolidate_glue_default_arguments=consolidate_glue["default_arguments"],
                    raw_bucket=raw_bucket,
                    credentials_secret=credentials_secret,
                    lambda_runtime=lambda_runtime,
                    common_env=common_env,
                    secret_name=secret_name,
                    connector_cfg=connector_cfg,
                    glue_bronze_assets=glue_bronze_assets,
                    schedule_hour=int(schedule_cfg.get("hour", 6)),
                    schedule_minute=int(schedule_cfg.get("minute", 0)),
                )
                continue

            raise ValueError(f"Unsupported ingest connector {connector!r}")

        self._create_athena_catalog(
            data_bucket=raw_bucket,
            company=company,
            environment=environment,
            connectors=connectors,
        )

        CfnOutput(self, "DataBucketName", value=raw_bucket.bucket_name)
        CfnOutput(self, "RawBucketName", value=raw_bucket.bucket_name)

    def _apply_cost_allocation_tags(self, company: str, environment: str) -> None:
        from hiveflow.project_config import cost_allocation_tags

        for key, value in cost_allocation_tags(company, environment).items():
            Tags.of(self).add(key, value)

    def _create_refresh_pipeline(
        self,
        *,
        construct_id: str,
        connector: str,
        company: str,
        environment: str,
        consolidate_glue_job_name: str,
        consolidate_glue_job: Any,
        consolidate_glue_default_arguments: dict[str, str],
        raw_bucket: s3.Bucket,
        credentials_secret: secretsmanager.ISecret | None,
        lambda_runtime: HiveFlowLambdaRuntime | None,
        common_env: dict[str, str] | None,
        secret_name: str,
        connector_cfg: dict[str, Any] | None = None,
        glue_bronze_assets: Any = None,
        schedule_hour: int | None = None,
        schedule_minute: int | None = None,
    ) -> None:
        from ingest_fanout import DEFAULT_GLUE_MAX_CAPACITY, DEFAULT_GLUE_TIMEOUT_MINUTES, create_bronze_ingest_steps
        from refresh_pipeline import create_refresh_pipeline

        bronze_ingest_definition = None
        if (
            credentials_secret is not None
            and lambda_runtime is not None
            and common_env is not None
            and glue_bronze_assets is not None
        ):
            cfg = connector_cfg if isinstance(connector_cfg, dict) else {}
            glue_max_capacity = cfg.get("glue_max_capacity", DEFAULT_GLUE_MAX_CAPACITY)
            glue_timeout_minutes = int(cfg.get("glue_timeout_minutes", DEFAULT_GLUE_TIMEOUT_MINUTES))
            bronze_resources = create_bronze_ingest_steps(
                self,
                construct_id,
                connector=connector,
                company=company,
                environment=environment,
                raw_bucket=raw_bucket,
                credentials_secret=credentials_secret,
                lambda_runtime=lambda_runtime,
                common_env=common_env,
                grant_glue_catalog_sync=grant_glue_catalog_sync,
                glue_assets=glue_bronze_assets,
                glue_max_capacity=float(glue_max_capacity),
                glue_timeout_minutes=glue_timeout_minutes,
            )
            bronze_ingest_definition = bronze_resources["definition"]

            output_prefix = connector.upper()
            CfnOutput(
                self,
                f"{output_prefix}BronzePrepareFunctionName",
                value=bronze_resources["prepare_function"].function_name,
            )
            CfnOutput(
                self,
                f"{output_prefix}BronzeIngestGlueJobName",
                value=bronze_resources["ingest_glue_job"].name or "",
            )
            CfnOutput(
                self,
                f"{output_prefix}BronzeFinalizeFunctionName",
                value=bronze_resources["finalize_function"].function_name,
            )

        resources = create_refresh_pipeline(
            self,
            construct_id,
            connector=connector,
            company=company,
            environment=environment,
            consolidate_glue_job_name=consolidate_glue_job_name,
            consolidate_glue_job=consolidate_glue_job,
            consolidate_glue_default_arguments=consolidate_glue_default_arguments,
            bronze_ingest_definition=bronze_ingest_definition,
            schedule_hour=schedule_hour,
            schedule_minute=schedule_minute,
        )

        output_prefix = connector.upper()
        if bronze_ingest_definition is not None:
            CfnOutput(self, f"{output_prefix}SecretName", value=secret_name)
        CfnOutput(
            self,
            f"{output_prefix}RefreshStateMachineArn",
            value=resources["state_machine"].state_machine_arn,
        )
        CfnOutput(
            self,
            f"{output_prefix}RefreshStateMachineName",
            value=resources["state_machine"].state_machine_name,
        )

    def _create_consolidate_glue_job(
        self,
        *,
        raw_bucket: s3.Bucket,
        glue_assets: Any,
        company: str,
        environment: str,
    ) -> dict[str, Any]:
        from silver_consolidate import create_silver_consolidate_glue_job

        resources = create_silver_consolidate_glue_job(
            self,
            "All",
            company=company,
            environment=environment,
            raw_bucket=raw_bucket,
            glue_assets=glue_assets,
            grant_glue_catalog_sync=grant_glue_catalog_sync,
        )
        CfnOutput(
            self,
            "AllSilverConsolidateGlueJobName",
            value=resources["glue_job_name"],
        )
        return resources

    def _create_athena_catalog(
        self,
        *,
        data_bucket: s3.Bucket,
        company: str,
        environment: str,
        connectors: list[tuple[str, dict[str, Any]]],
    ) -> None:
        resources = create_athena_catalog(
            self,
            data_bucket=data_bucket,
            company=company,
            environment=environment,
            connectors=connectors,
        )
        CfnOutput(self, "GlueDatabaseName", value=resources["database_name"])
        CfnOutput(self, "AthenaWorkGroupName", value=resources["workgroup_name"])
        CfnOutput(
            self,
            "AthenaResultsBucketName",
            value=resources["results_bucket"].bucket_name,
        )
        sample_queries = resources["sample_queries"]
        if sample_queries:
            CfnOutput(
                self,
                "AthenaSampleQuery",
                value=sample_queries[0],
                description="Example Athena query for silver row counts",
            )

    def _create_qbd_soap(
        self,
        *,
        raw_bucket: s3.Bucket,
        credentials_secret: secretsmanager.ISecret,
        lambda_runtime: HiveFlowLambdaRuntime,
        common_env: dict[str, str],
        company: str,
        environment: str,
        secret_name: str,
    ) -> None:
        resources = create_qbd_soap_endpoint(
            self,
            raw_bucket=raw_bucket,
            credentials_secret=credentials_secret,
            lambda_runtime=lambda_runtime,
            common_env=common_env,
            company=company,
            environment=environment,
            grant_glue_catalog_sync=grant_glue_catalog_sync,
        )

        CfnOutput(self, "QbdSecretName", value=secret_name)
        CfnOutput(
            self,
            "QbdBronzeIngestFunctionName",
            value=resources["function"].function_name,
        )
        CfnOutput(self, "QbdSoapUrl", value=resources["url"])
