from __future__ import annotations

from typing import Any

from aws_cdk import Duration
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as targets
from aws_cdk import aws_lambda as _lambda
from aws_cdk import aws_stepfunctions as sfn
from aws_cdk import aws_stepfunctions_tasks as tasks
from constructs import Construct

from meshflow.process_config import Process, step_function_name_for_process


def dna_eventbridge_rule_name(company: str, environment: str) -> str:
    """EventBridge rule for the DNA refresh pipeline."""
    return f"{company.strip().lower()}-{environment.strip().lower()}-dna"


def create_dna_pipeline(
    scope: Construct,
    construct_id: str,
    *,
    company: str,
    environment: str,
    source: str,
    dna_publish_function: _lambda.IFunction,
    schedule_hour: int | None = None,
    schedule_minute: int | None = None,
    pack_id: str = "bc_intra_v1",
) -> dict[str, Any]:
    """Step Functions workflow: DNA compile → validate → publish."""
    prefix = construct_id

    publish_task = tasks.LambdaInvoke(
        scope,
        f"{prefix}DnaPublishTask",
        lambda_function=dna_publish_function,
        payload=sfn.TaskInput.from_object(
            {
                "source": source,
                "action": "publish",
                "pack_id": pack_id,
            }
        ),
        output_path="$.Payload",
    )

    state_machine = sfn.StateMachine(
        scope,
        f"{prefix}DnaRefreshStateMachine",
        state_machine_name=step_function_name_for_process(
            company, environment, "all", Process.DNA_REFRESH
        ),
        definition_body=sfn.DefinitionBody.from_chainable(publish_task),
        timeout=Duration.minutes(30),
    )

    if schedule_hour is not None and schedule_minute is not None:
        schedule = events.Rule(
            scope,
            f"{prefix}DnaRefreshSchedule",
            rule_name=dna_eventbridge_rule_name(company, environment),
            description="Daily DNA semantic publish (compile, validate, gold tables)",
            schedule=events.Schedule.cron(
                minute=str(schedule_minute),
                hour=str(schedule_hour),
            ),
        )
        schedule.add_target(
            targets.SfnStateMachine(
                state_machine,
                input=events.RuleTargetInput.from_object({}),
            )
        )

    return {
        "state_machine": state_machine,
        "publish_function": dna_publish_function,
    }
