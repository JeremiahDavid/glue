from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import jsii
from aws_cdk import (
    BundlingOptions,
    CfnOutput,
    Duration,
    ILocalBundling,
    RemovalPolicy,
    Stack,
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
    """POC ingest stack: S3 landing zone, secret reference, scheduled Lambda."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        company: str,
        environment: str,
        qbo_secret_name: str,
        raw_bucket_name: str,
        s3_prefix: str = "qbo",
        schedule_hour: int = 6,
        schedule_minute: int = 0,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        if not qbo_secret_name.strip():
            raise ValueError(
                "Could not derive QBO secret name from config.yaml for this company/environment"
            )

        if not raw_bucket_name.strip():
            raise ValueError(
                "Could not derive raw S3 bucket name from config.yaml for this company/environment"
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

        qbo_secret = secretsmanager.Secret.from_secret_name_v2(
            self,
            "QboCredentials",
            qbo_secret_name,
        )

        ingest_fn = _lambda.Function(
            self,
            "QboIngestFunction",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="meshflow.lambda_handler.lambda_handler",
            timeout=Duration.minutes(10),
            memory_size=512,
            description=(
                f"Pull QuickBooks Online entities and write raw Parquet to S3 "
                f"({company}/{environment})"
            ),
            code=_lambda.Code.from_asset(
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
            ),
            environment={
                "MESHFLOW_COMPANY": company,
                "MESHFLOW_ENVIRONMENT": environment,
                "MESHFLOW_SOURCE": s3_prefix,
                "MESHFLOW_SECRET_ID": qbo_secret_name,
                "MESHFLOW_S3_BUCKET": raw_bucket.bucket_name,
                "MESHFLOW_S3_PREFIX": s3_prefix,
            },
        )

        qbo_secret.grant_read(ingest_fn)
        qbo_secret.grant_write(ingest_fn)
        raw_bucket.grant_read_write(ingest_fn)

        schedule = events.Rule(
            self,
            "QboIngestSchedule",
            description="Daily QuickBooks Online raw ingest",
            schedule=events.Schedule.cron(minute=str(schedule_minute), hour=str(schedule_hour)),
        )
        schedule.add_target(targets.LambdaFunction(ingest_fn))

        CfnOutput(self, "RawBucketName", value=raw_bucket.bucket_name)
        CfnOutput(self, "QboSecretName", value=qbo_secret.secret_name)
        CfnOutput(self, "QboIngestFunctionName", value=ingest_fn.function_name)
