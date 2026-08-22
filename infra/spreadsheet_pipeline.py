from __future__ import annotations

from typing import Any

from aws_cdk import Duration
from aws_cdk import aws_lambda as _lambda
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_stepfunctions as sfn
from aws_cdk import aws_stepfunctions_tasks as tasks
from constructs import Construct

from lambda_bundle import HiveFlowLambdaRuntime
from hiveflow.process_config import Process, lambda_name_for_process, step_function_name_for_process


def _apply_lambda_throttle_retry(task: tasks.LambdaInvoke) -> tasks.LambdaInvoke:
    task.add_retry(
        errors=["Lambda.TooManyRequestsException"],
        interval=Duration.seconds(5),
        max_attempts=8,
        backoff_rate=2,
    )
    return task


def create_spreadsheet_pipeline(
    scope: Construct,
    construct_id: str,
    *,
    company: str,
    environment: str,
    data_bucket: s3.IBucket,
    lambda_runtime: HiveFlowLambdaRuntime,
    common_env: dict[str, str],
    grant_bedrock: Any,
) -> dict[str, Any]:
    """Spreadsheet Engine: parse -> profile -> interpret -> propose."""
    prefix = construct_id

    parse_fn = _lambda.Function(
        scope,
        f"{prefix}SpreadsheetParseFunction",
        function_name=lambda_name_for_process(
            company, environment, "all", Process.SPREADSHEET_PARSE
        ),
        runtime=_lambda.Runtime.PYTHON_3_12,
        handler="hiveflow.spreadsheet.handlers.parse_handler",
        timeout=Duration.minutes(5),
        memory_size=1024,
        description="Spreadsheet Engine: parse uploaded Excel workbooks",
        code=lambda_runtime.code,
        layers=lambda_runtime.layers,
        environment=common_env,
    )
    profile_fn = _lambda.Function(
        scope,
        f"{prefix}SpreadsheetProfileFunction",
        function_name=lambda_name_for_process(
            company, environment, "all", Process.SPREADSHEET_PROFILE
        ),
        runtime=_lambda.Runtime.PYTHON_3_12,
        handler="hiveflow.spreadsheet.handlers.profile_handler",
        timeout=Duration.minutes(5),
        memory_size=1024,
        description="Spreadsheet Engine: profile spreadsheet table candidates",
        code=lambda_runtime.code,
        layers=lambda_runtime.layers,
        environment=common_env,
    )
    interpret_fn = _lambda.Function(
        scope,
        f"{prefix}SpreadsheetInterpretFunction",
        function_name=lambda_name_for_process(
            company, environment, "all", Process.SPREADSHEET_INTERPRET
        ),
        runtime=_lambda.Runtime.PYTHON_3_12,
        handler="hiveflow.spreadsheet.handlers.interpret_handler",
        timeout=Duration.minutes(10),
        memory_size=1024,
        description="Spreadsheet Engine: Bedrock semantic analysis of spreadsheet tables",
        code=lambda_runtime.code,
        layers=lambda_runtime.layers,
        environment=common_env,
    )
    propose_fn = _lambda.Function(
        scope,
        f"{prefix}SpreadsheetProposeFunction",
        function_name=lambda_name_for_process(
            company, environment, "all", Process.SPREADSHEET_PROPOSE
        ),
        runtime=_lambda.Runtime.PYTHON_3_12,
        handler="hiveflow.spreadsheet.handlers.propose_handler",
        timeout=Duration.minutes(10),
        memory_size=1024,
        description="Spreadsheet Engine: propose transformations from knowledge base",
        code=lambda_runtime.code,
        layers=lambda_runtime.layers,
        environment=common_env,
    )

    for fn in (parse_fn, profile_fn, interpret_fn, propose_fn):
        data_bucket.grant_read_write(fn)
        grant_bedrock(fn)

    parse_task = _apply_lambda_throttle_retry(
        tasks.LambdaInvoke(
            scope,
            f"{prefix}SpreadsheetParseTask",
            lambda_function=parse_fn,
            output_path="$.Payload",
        )
    )
    profile_task = _apply_lambda_throttle_retry(
        tasks.LambdaInvoke(
            scope,
            f"{prefix}SpreadsheetProfileTask",
            lambda_function=profile_fn,
            output_path="$.Payload",
            payload=sfn.TaskInput.from_object(
                {
                    "job_id": sfn.JsonPath.string_at("$.job_id"),
                }
            ),
        )
    )
    interpret_task = _apply_lambda_throttle_retry(
        tasks.LambdaInvoke(
            scope,
            f"{prefix}SpreadsheetInterpretTask",
            lambda_function=interpret_fn,
            output_path="$.Payload",
            payload=sfn.TaskInput.from_object(
                {
                    "job_id": sfn.JsonPath.string_at("$.job_id"),
                }
            ),
        )
    )
    propose_task = _apply_lambda_throttle_retry(
        tasks.LambdaInvoke(
            scope,
            f"{prefix}SpreadsheetProposeTask",
            lambda_function=propose_fn,
            output_path="$.Payload",
            payload=sfn.TaskInput.from_object(
                {
                    "job_id": sfn.JsonPath.string_at("$.job_id"),
                }
            ),
        )
    )

    definition = parse_task.next(profile_task).next(interpret_task).next(propose_task)
    state_machine = sfn.StateMachine(
        scope,
        f"{prefix}SpreadsheetAnalyzeStateMachine",
        state_machine_name=step_function_name_for_process(
            company, environment, "all", Process.SPREADSHEET_ANALYZE
        ),
        definition_body=sfn.DefinitionBody.from_chainable(definition),
        timeout=Duration.minutes(30),
    )

    return {
        "state_machine": state_machine,
        "parse_function": parse_fn,
        "profile_function": profile_fn,
        "interpret_function": interpret_fn,
        "propose_function": propose_fn,
    }
