from __future__ import annotations

from typing import Any

from aws_cdk import Duration
from aws_cdk import aws_lambda as _lambda
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_secretsmanager as secretsmanager
from aws_cdk import aws_stepfunctions as sfn
from aws_cdk import aws_stepfunctions_tasks as tasks
from constructs import Construct

from lambda_bundle import MeshflowLambdaRuntime
from meshflow.process_config import Process, lambda_name_for_process


def create_bronze_ingest_steps(
    scope: Construct,
    construct_id: str,
    *,
    connector: str,
    company: str,
    environment: str,
    raw_bucket: s3.Bucket,
    credentials_secret: secretsmanager.ISecret,
    lambda_runtime: MeshflowLambdaRuntime,
    common_env: dict[str, str],
    grant_glue_catalog_sync,
    ingest_timeout: Duration = Duration.minutes(10),
    ingest_memory: int = 512,
    map_max_concurrency: int = 10,
) -> dict[str, Any]:
    """Bronze ingest Lambdas and Step Functions chain: prepare -> Map(entities) -> finalize."""
    prefix = construct_id

    ingest_fn = _lambda.Function(
        scope,
        f"{prefix}BronzeIngestFunction",
        function_name=lambda_name_for_process(company, environment, connector, Process.INGEST),
        runtime=_lambda.Runtime.PYTHON_3_12,
        handler="meshflow.lambda_handler.lambda_handler",
        timeout=ingest_timeout,
        memory_size=ingest_memory,
        description=f"Bronze ingest: pull one {connector} entity into a shared raw run",
        code=lambda_runtime.code,
        layers=lambda_runtime.layers,
        environment=common_env,
    )

    prepare_fn = _lambda.Function(
        scope,
        f"{prefix}BronzePrepareFunction",
        function_name=lambda_name_for_process(company, environment, connector, Process.PREPARE),
        runtime=_lambda.Runtime.PYTHON_3_12,
        handler="meshflow.ingest.orchestration_handlers.prepare_handler",
        timeout=Duration.minutes(2),
        memory_size=512,
        description=f"Bronze ingest: prepare fan-out run for {connector}",
        code=lambda_runtime.code,
        layers=lambda_runtime.layers,
        environment=common_env,
    )

    finalize_fn = _lambda.Function(
        scope,
        f"{prefix}BronzeFinalizeFunction",
        function_name=lambda_name_for_process(company, environment, connector, Process.FINALIZE),
        runtime=_lambda.Runtime.PYTHON_3_12,
        handler="meshflow.ingest.orchestration_handlers.finalize_handler",
        timeout=Duration.minutes(5),
        memory_size=512,
        description=f"Bronze ingest: finalize fan-out run for {connector}",
        code=lambda_runtime.code,
        layers=lambda_runtime.layers,
        environment=common_env,
    )

    for fn in (ingest_fn, prepare_fn, finalize_fn):
        credentials_secret.grant_read(fn)
        credentials_secret.grant_write(fn)
        raw_bucket.grant_read_write(fn)
        grant_glue_catalog_sync(fn, company=company, environment=environment)

    prepare_task = tasks.LambdaInvoke(
        scope,
        f"{prefix}BronzePrepareTask",
        lambda_function=prepare_fn,
        output_path="$.Payload",
    )

    ingest_task = tasks.LambdaInvoke(
        scope,
        f"{prefix}BronzeIngestEntityTask",
        lambda_function=ingest_fn,
        payload=sfn.TaskInput.from_json_path_at("$"),
        output_path="$.Payload",
    )

    map_state = sfn.Map(
        scope,
        f"{prefix}BronzeIngestEntitiesMap",
        items_path=sfn.JsonPath.string_at("$.entities"),
        result_path="$.ingest_results",
        max_concurrency=map_max_concurrency,
        item_selector={
            "entity.$": "$$.Map.Item.Value",
            "run_id.$": "$.run_id",
            "full_load.$": "$.full_load",
        },
    ).item_processor(ingest_task)

    finalize_task = tasks.LambdaInvoke(
        scope,
        f"{prefix}BronzeFinalizeTask",
        lambda_function=finalize_fn,
        payload=sfn.TaskInput.from_object(
            {
                "run_id.$": "$.run_id",
                "full_load.$": "$.full_load",
                "full_rebuild.$": "$.full_rebuild",
                "entity_results.$": "$.ingest_results",
            }
        ),
        output_path="$.Payload",
    )

    definition = prepare_task.next(map_state).next(finalize_task)

    return {
        "ingest_function": ingest_fn,
        "prepare_function": prepare_fn,
        "finalize_function": finalize_fn,
        "definition": definition,
    }
