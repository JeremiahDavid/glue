from __future__ import annotations

from typing import Any

from aws_cdk import Duration
from aws_cdk import aws_glue as glue
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as _lambda
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_secretsmanager as secretsmanager
from aws_cdk import aws_stepfunctions as sfn
from aws_cdk import aws_stepfunctions_tasks as tasks
from constructs import Construct

from glue_bundle import HiveFlowGlueBronzeAssets
from lambda_bundle import HiveFlowLambdaRuntime
from hiveflow.process_config import glue_job_name_for_process, Process, lambda_name_for_process

# Cheapest Glue Python Shell allocation (1/16 DPU). Increase via connector config later if needed.
DEFAULT_GLUE_MAX_CAPACITY = 0.0625
DEFAULT_GLUE_TIMEOUT_MINUTES = 240


def _apply_lambda_throttle_retry(task: tasks.LambdaInvoke) -> tasks.LambdaInvoke:
    task.add_retry(
        errors=["Lambda.TooManyRequestsException"],
        interval=Duration.seconds(5),
        max_attempts=8,
        backoff_rate=2,
    )
    return task


def create_bronze_ingest_steps(
    scope: Construct,
    construct_id: str,
    *,
    connector: str,
    company: str,
    environment: str,
    raw_bucket: s3.Bucket,
    credentials_secret: secretsmanager.ISecret,
    lambda_runtime: HiveFlowLambdaRuntime,
    common_env: dict[str, str],
    grant_glue_catalog_sync,
    glue_assets: HiveFlowGlueBronzeAssets,
    glue_max_capacity: float = DEFAULT_GLUE_MAX_CAPACITY,
    glue_timeout_minutes: int = DEFAULT_GLUE_TIMEOUT_MINUTES,
) -> dict[str, Any]:
    """Bronze ingest: prepare Lambda -> Glue Python Shell job -> finalize Lambda."""
    prefix = construct_id

    glue_job_role = iam.Role(
        scope,
        f"{prefix}BronzeIngestGlueRole",
        assumed_by=iam.ServicePrincipal("glue.amazonaws.com"),
        description=f"Glue bronze ingest for {connector} ({company}/{environment})",
    )
    glue_job_role.add_managed_policy(
        iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSGlueServiceRole")
    )

    prepare_fn = _lambda.Function(
        scope,
        f"{prefix}BronzePrepareFunction",
        function_name=lambda_name_for_process(company, environment, connector, Process.PREPARE),
        runtime=_lambda.Runtime.PYTHON_3_12,
        handler="hiveflow.ingest.orchestration_handlers.prepare_handler",
        timeout=Duration.minutes(2),
        memory_size=512,
        description=f"Bronze ingest: prepare run metadata for {connector} Glue job",
        code=lambda_runtime.code,
        layers=lambda_runtime.layers,
        environment=common_env,
    )

    finalize_fn = _lambda.Function(
        scope,
        f"{prefix}BronzeFinalizeFunction",
        function_name=lambda_name_for_process(company, environment, connector, Process.FINALIZE),
        runtime=_lambda.Runtime.PYTHON_3_12,
        handler="hiveflow.ingest.orchestration_handlers.finalize_handler",
        timeout=Duration.minutes(5),
        memory_size=512,
        description=f"Bronze ingest: finalize after {connector} Glue job",
        code=lambda_runtime.code,
        layers=lambda_runtime.layers,
        environment=common_env,
    )

    for fn in (prepare_fn, finalize_fn):
        credentials_secret.grant_read(fn)
        credentials_secret.grant_write(fn)
        raw_bucket.grant_read_write(fn)
        grant_glue_catalog_sync(fn, company=company, environment=environment)

    credentials_secret.grant_read(glue_job_role)
    credentials_secret.grant_write(glue_job_role)
    raw_bucket.grant_read_write(glue_job_role)
    grant_glue_catalog_sync(glue_job_role, company=company, environment=environment)

    glue_assets.script_asset.grant_read(glue_job_role)
    glue_assets.extra_py_files_asset.grant_read(glue_job_role)

    glue_job_name = glue_job_name_for_process(company, environment, connector, Process.INGEST)
    default_arguments: dict[str, str] = {
        "--JOB_NAME": glue_job_name,
        "--job-language": "python",
        "--enable-metrics": "true",
        "--extra-py-files": glue_assets.extra_py_files_asset.s3_object_url,
        "--HIVEFLOW_COMPANY": common_env["HIVEFLOW_COMPANY"],
        "--HIVEFLOW_ENVIRONMENT": common_env["HIVEFLOW_ENVIRONMENT"],
        "--HIVEFLOW_SOURCE": common_env["HIVEFLOW_SOURCE"],
        "--HIVEFLOW_SECRET_ID": common_env["HIVEFLOW_SECRET_ID"],
        "--HIVEFLOW_S3_BUCKET": common_env["HIVEFLOW_S3_BUCKET"],
        "--HIVEFLOW_S3_PREFIX": common_env["HIVEFLOW_S3_PREFIX"],
        "--full_load": "false",
    }

    ingest_glue_job = glue.CfnJob(
        scope,
        f"{prefix}BronzeIngestGlueJob",
        name=glue_job_name,
        role=glue_job_role.role_arn,
        glue_version="4.0",
        max_capacity=glue_max_capacity,
        timeout=glue_timeout_minutes,
        command=glue.CfnJob.JobCommandProperty(
            name="pythonshell",
            python_version="3.9",
            script_location=glue_assets.script_asset.s3_object_url,
        ),
        default_arguments=default_arguments,
        description=f"Bronze ingest: sequential {connector} entity pull into shared raw run",
    )

    prepare_task = _apply_lambda_throttle_retry(
        tasks.LambdaInvoke(
            scope,
            f"{prefix}BronzePrepareTask",
            lambda_function=prepare_fn,
            output_path="$.Payload",
        )
    )

    glue_run_arguments = {
        key: value
        for key, value in default_arguments.items()
        if key not in {"--run_id", "--full_load"}
    }

    ingest_glue_task = tasks.GlueStartJobRun(
        scope,
        f"{prefix}BronzeIngestGlueTask",
        glue_job_name=glue_job_name,
        integration_pattern=sfn.IntegrationPattern.RUN_JOB,
        arguments=sfn.TaskInput.from_object(
            {
                **glue_run_arguments,
                "--run_id.$": "$.run_id",
                # Glue StartJobRun rejects non-string argument values.
                "--full_load.$": "States.JsonToString($.full_load)",
            }
        ),
        result_path="$.glue_ingest",
    )
    ingest_glue_task.add_retry(
        errors=["Glue.ConcurrentRunsExceededException"],
        interval=Duration.seconds(30),
        max_attempts=6,
        backoff_rate=2,
    )

    finalize_task = _apply_lambda_throttle_retry(
        tasks.LambdaInvoke(
            scope,
            f"{prefix}BronzeFinalizeTask",
            lambda_function=finalize_fn,
            payload=sfn.TaskInput.from_object(
                {
                    "run_id.$": "$.run_id",
                    "full_load.$": "$.full_load",
                    "full_rebuild.$": "$.full_rebuild",
                }
            ),
            output_path="$.Payload",
        )
    )

    definition = prepare_task.next(ingest_glue_task).next(finalize_task)

    return {
        "ingest_glue_job": ingest_glue_job,
        "prepare_function": prepare_fn,
        "finalize_function": finalize_fn,
        "definition": definition,
    }
