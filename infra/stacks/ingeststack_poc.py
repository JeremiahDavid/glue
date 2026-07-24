from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import jsii
from aws_cdk import (
    BundlingOptions,
    CfnOutput,
    Duration,
    ILocalBundling,
    RemovalPolicy,
    Stack,
    aws_apigateway as apigateway,
    aws_events as events,
    aws_events_targets as targets,
    aws_lambda as _lambda,
    aws_s3 as s3,
    aws_secretsmanager as secretsmanager,
)
from constructs import Construct

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@jsii.implements(ILocalBundling)
class _LocalPythonBundling:
    """Bundle Lambda deps with local pip when Docker is unavailable."""

    def try_bundle(self, output_dir: str, _options: BundlingOptions) -> bool:
        pip_platform = "manylinux2014_x86_64"
        pip_python = "3.12"
        common = [
            sys.executable,
            "-m",
            "pip",
            "install",
            "-t",
            output_dir,
            "--platform",
            pip_platform,
            "--python-version",
            pip_python,
            "--only-binary=:all:",
        ]
        try:
            subprocess.run(
                [*common, "-r", str(PROJECT_ROOT / "requirements.txt")],
                check=True,
                capture_output=True,
            )
            shutil.copytree(
                PROJECT_ROOT / "src" / "meshflow",
                Path(output_dir) / "meshflow",
                dirs_exist_ok=True,
            )
            shutil.copy2(PROJECT_ROOT / "config.yaml", Path(output_dir) / "config.yaml")
        except (subprocess.CalledProcessError, OSError):
            return False
        return True


class IngestStack(Stack):
    """POC ingest stack: shared S3 landing zone and per-connector compute."""

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

        lambda_code = _lambda.Code.from_asset(
            str(PROJECT_ROOT),
            bundling=BundlingOptions(
                image=_lambda.Runtime.PYTHON_3_12.bundling_image,
                command=[
                    "bash",
                    "-c",
                    "pip install -r /asset-input/requirements.txt -t /asset-output && "
                    "pip install /asset-input -t /asset-output --no-deps && "
                    "cp /asset-input/config.yaml /asset-output/config.yaml",
                ],
                local=_LocalPythonBundling(),
            ),
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
                "MESHFLOW_COMPANY": company,
                "MESHFLOW_ENVIRONMENT": environment,
                "MESHFLOW_SOURCE": connector,
                "MESHFLOW_SECRET_ID": secret_name,
                "MESHFLOW_S3_BUCKET": raw_bucket.bucket_name,
                "MESHFLOW_S3_PREFIX": connector,
            }

            if connector == "qbd":
                self._create_qbd_soap(
                    raw_bucket=raw_bucket,
                    credentials_secret=credentials_secret,
                    lambda_code=lambda_code,
                    common_env=common_env,
                    company=company,
                    environment=environment,
                    secret_name=secret_name,
                )
                continue

            if connector == "qbo":
                schedule_cfg = connector_cfg.get("schedule", {})
                if not isinstance(schedule_cfg, dict):
                    schedule_cfg = {}
                self._create_qbo_scheduled_ingest(
                    raw_bucket=raw_bucket,
                    credentials_secret=credentials_secret,
                    lambda_code=lambda_code,
                    common_env=common_env,
                    schedule_hour=int(schedule_cfg.get("hour", 6)),
                    schedule_minute=int(schedule_cfg.get("minute", 0)),
                    secret_name=secret_name,
                )
                continue

            raise ValueError(f"Unsupported ingest connector {connector!r}")

        CfnOutput(self, "RawBucketName", value=raw_bucket.bucket_name)

    def _create_qbo_scheduled_ingest(
        self,
        *,
        raw_bucket: s3.Bucket,
        credentials_secret: secretsmanager.ISecret,
        lambda_code: _lambda.Code,
        common_env: dict[str, str],
        schedule_hour: int,
        schedule_minute: int,
        secret_name: str,
    ) -> None:
        ingest_fn = _lambda.Function(
            self,
            "QboIngestFunction",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="meshflow.lambda_handler.lambda_handler",
            timeout=Duration.minutes(10),
            memory_size=512,
            description="Pull QuickBooks Online entities and write raw Parquet to S3",
            code=lambda_code,
            environment=common_env,
        )

        credentials_secret.grant_read(ingest_fn)
        credentials_secret.grant_write(ingest_fn)
        raw_bucket.grant_read_write(ingest_fn)

        schedule = events.Rule(
            self,
            "QboIngestSchedule",
            description="Daily QuickBooks Online raw ingest",
            schedule=events.Schedule.cron(minute=str(schedule_minute), hour=str(schedule_hour)),
        )
        schedule.add_target(targets.LambdaFunction(ingest_fn))

        CfnOutput(self, "QboSecretName", value=secret_name)
        CfnOutput(self, "QboIngestFunctionName", value=ingest_fn.function_name)

    def _create_qbd_soap(
        self,
        *,
        raw_bucket: s3.Bucket,
        credentials_secret: secretsmanager.ISecret,
        lambda_code: _lambda.Code,
        common_env: dict[str, str],
        company: str,
        environment: str,
        secret_name: str,
    ) -> None:
        soap_fn = _lambda.Function(
            self,
            "QbdSoapFunction",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="meshflow.qbd.soap_handler.soap_handler",
            timeout=Duration.minutes(2),
            memory_size=1024,
            description=(
                f"QuickBooks Web Connector SOAP endpoint for {company}/{environment}"
            ),
            code=lambda_code,
            environment={
                **common_env,
                "QBD_QBXML_VERSION": "17.0",
            },
        )

        credentials_secret.grant_read(soap_fn)
        raw_bucket.grant_read_write(soap_fn)

        soap_api = apigateway.RestApi(
            self,
            "QbdSoapApi",
            rest_api_name=f"meshflow-qbd-{company}-{environment}".lower(),
            description="QuickBooks Web Connector SOAP endpoint",
            deploy_options=apigateway.StageOptions(
                stage_name="prod",
                logging_level=apigateway.MethodLoggingLevel.INFO,
                data_trace_enabled=False,
            ),
            endpoint_configuration=apigateway.EndpointConfiguration(
                types=[apigateway.EndpointType.REGIONAL]
            ),
        )
        soap_resource = soap_api.root.add_resource("soap")
        soap_integration = apigateway.LambdaIntegration(
            soap_fn,
            proxy=True,
            allow_test_invoke=False,
        )
        for method in ("POST", "GET"):
            soap_resource.add_method(method, soap_integration)

        soap_url = f"{soap_api.url}soap"

        CfnOutput(self, "QbdSecretName", value=secret_name)
        CfnOutput(self, "QbdSoapFunctionName", value=soap_fn.function_name)
        CfnOutput(self, "QbdSoapUrl", value=soap_url)
