from __future__ import annotations

from typing import Any

from aws_cdk import Duration
from aws_cdk import aws_glue as glue
from aws_cdk import aws_iam as iam
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_stepfunctions as sfn
from aws_cdk import aws_stepfunctions_tasks as tasks
from constructs import Construct

from glue_bundle import MeshflowGlueSilverAssets
from meshflow.process_config import Process, glue_job_name_for_process

# Silver consolidate can run Athena SQL replay; allow a longer window than the old Lambda.
DEFAULT_GLUE_MAX_CAPACITY = 0.0625
DEFAULT_GLUE_TIMEOUT_MINUTES = 120


def create_silver_consolidate_glue_job(
    scope: Construct,
    construct_id: str,
    *,
    company: str,
    environment: str,
    raw_bucket: s3.Bucket,
    glue_assets: MeshflowGlueSilverAssets,
    grant_glue_catalog_sync,
    glue_max_capacity: float = DEFAULT_GLUE_MAX_CAPACITY,
    glue_timeout_minutes: int = DEFAULT_GLUE_TIMEOUT_MINUTES,
) -> dict[str, Any]:
    """Shared silver consolidate Glue job for all connectors in this environment."""
    glue_job_role = iam.Role(
        scope,
        f"{construct_id}SilverConsolidateGlueRole",
        assumed_by=iam.ServicePrincipal("glue.amazonaws.com"),
        description=f"Glue silver consolidate for {company}/{environment}",
    )
    glue_job_role.add_managed_policy(
        iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSGlueServiceRole")
    )

    raw_bucket.grant_read_write(glue_job_role)
    grant_glue_catalog_sync(glue_job_role, company=company, environment=environment)

    glue_assets.script_asset.grant_read(glue_job_role)
    glue_assets.extra_py_files_asset.grant_read(glue_job_role)

    glue_job_name = glue_job_name_for_process(company, environment, "all", Process.CONSOLIDATE)
    default_arguments: dict[str, str] = {
        "--JOB_NAME": glue_job_name,
        "--job-language": "python",
        "--enable-metrics": "true",
        "--extra-py-files": glue_assets.extra_py_files_asset.s3_object_url,
        "--MESHFLOW_COMPANY": company,
        "--MESHFLOW_ENVIRONMENT": environment,
        "--MESHFLOW_S3_BUCKET": raw_bucket.bucket_name,
        "--MESHFLOW_SOURCE": "",
        "--full_rebuild": "false",
    }

    consolidate_glue_job = glue.CfnJob(
        scope,
        f"{construct_id}SilverConsolidateGlueJob",
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
        description=(
            f"Silver_stg consolidate: merge bronze parquet runs into silver_stg "
            f"for {company}/{environment}"
        ),
    )

    return {
        "glue_job": consolidate_glue_job,
        "glue_job_name": glue_job_name,
        "default_arguments": default_arguments,
    }


def create_silver_consolidate_task(
    scope: Construct,
    construct_id: str,
    *,
    connector: str,
    consolidate_glue_job: glue.CfnJob,
    default_arguments: dict[str, str],
) -> tasks.GlueStartJobRun:
    """Step Functions task that runs the shared silver consolidate Glue job."""
    glue_job_name = consolidate_glue_job.name
    if not glue_job_name:
        raise ValueError("Silver consolidate Glue job is missing a name")

    glue_run_arguments = {
        key: value
        for key, value in default_arguments.items()
        if key not in {"--MESHFLOW_SOURCE", "--full_rebuild"}
    }

    consolidate_task = tasks.GlueStartJobRun(
        scope,
        f"{construct_id}SilverConsolidateGlueTask",
        glue_job_name=glue_job_name,
        integration_pattern=sfn.IntegrationPattern.RUN_JOB,
        arguments=sfn.TaskInput.from_object(
            {
                **glue_run_arguments,
                "--MESHFLOW_SOURCE": connector,
                "--full_rebuild.$": "States.JsonToString($.full_rebuild)",
            }
        ),
        result_path="$.glue_consolidate",
    )
    consolidate_task.add_depends_on(consolidate_glue_job)
    consolidate_task.add_retry(
        errors=["Glue.ConcurrentRunsExceededException"],
        interval=Duration.seconds(30),
        max_attempts=6,
        backoff_rate=2,
    )
    return consolidate_task
