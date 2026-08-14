from __future__ import annotations

from typing import Any

from aws_cdk import Duration
from aws_cdk import aws_glue as glue
from aws_cdk import aws_iam as iam
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_stepfunctions as sfn
from aws_cdk import aws_stepfunctions_tasks as tasks
from constructs import Construct

from glue_bundle import MeshflowGlueJobAssets
from meshflow.process_config import Process, glue_job_name_for_process

DEFAULT_GLUE_MAX_CAPACITY = 0.0625
DEFAULT_GLUE_TIMEOUT_MINUTES = 120


def create_dna_refresh_glue_job(
    scope: Construct,
    construct_id: str,
    *,
    company: str,
    environment: str,
    data_bucket: s3.IBucket,
    glue_assets: MeshflowGlueJobAssets,
    grant_glue_catalog_sync,
    grant_athena_query,
    source: str = "",
    glue_max_capacity: float = DEFAULT_GLUE_MAX_CAPACITY,
    glue_timeout_minutes: int = DEFAULT_GLUE_TIMEOUT_MINUTES,
) -> dict[str, Any]:
    """Client DNA Glue job: silver_stg → silver SQL + gold SQL."""
    glue_job_role = iam.Role(
        scope,
        f"{construct_id}DnaRefreshGlueRole",
        assumed_by=iam.ServicePrincipal("glue.amazonaws.com"),
        description=f"Glue DNA refresh for {company}/{environment}",
    )
    glue_job_role.add_managed_policy(
        iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSGlueServiceRole")
    )

    data_bucket.grant_read_write(glue_job_role)
    grant_glue_catalog_sync(glue_job_role, company=company, environment=environment)
    grant_athena_query(glue_job_role, company=company, environment=environment)

    glue_assets.script_asset.grant_read(glue_job_role)
    glue_assets.extra_py_files_asset.grant_read(glue_job_role)

    glue_job_name = glue_job_name_for_process(company, environment, "all", Process.DNA_APPLY)
    default_arguments: dict[str, str] = {
        "--JOB_NAME": glue_job_name,
        "--job-language": "python",
        "--enable-metrics": "true",
        "--extra-py-files": glue_assets.extra_py_files_asset.s3_object_url,
        "--MESHFLOW_COMPANY": company,
        "--MESHFLOW_ENVIRONMENT": environment,
        "--MESHFLOW_S3_BUCKET": data_bucket.bucket_name,
        "--MESHFLOW_SOURCE": source.strip().lower(),
    }

    dna_glue_job = glue.CfnJob(
        scope,
        f"{construct_id}DnaRefreshGlueJob",
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
            f"DNA refresh: copy pack silver_stg entities to silver, replay SQL "
            f"for {company}/{environment}"
        ),
    )

    return {
        "glue_job": dna_glue_job,
        "glue_job_name": glue_job_name,
        "default_arguments": default_arguments,
    }


def create_dna_refresh_glue_task(
    scope: Construct,
    construct_id: str,
    *,
    dna_glue_job: glue.CfnJob,
    default_arguments: dict[str, str],
) -> tasks.GlueStartJobRun:
    glue_job_name = dna_glue_job.name
    if not glue_job_name:
        raise ValueError("DNA refresh Glue job is missing a name")

    dna_task = tasks.GlueStartJobRun(
        scope,
        f"{construct_id}DnaRefreshGlueTask",
        glue_job_name=glue_job_name,
        integration_pattern=sfn.IntegrationPattern.RUN_JOB,
        arguments=sfn.TaskInput.from_object(default_arguments),
        result_path="$.glue_dna_refresh",
    )
    dna_task.node.add_dependency(dna_glue_job)
    dna_task.add_retry(
        errors=["Glue.ConcurrentRunsExceededException"],
        interval=Duration.seconds(30),
        max_attempts=6,
        backoff_rate=2,
    )
    return dna_task
