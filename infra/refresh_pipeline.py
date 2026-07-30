from __future__ import annotations

from typing import Any

from aws_cdk import Duration
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as targets
from aws_cdk import aws_lambda as _lambda
from aws_cdk import aws_stepfunctions as sfn
from aws_cdk import aws_stepfunctions_tasks as tasks
from constructs import Construct

from meshflow.project_config import eventbridge_rule_name
from meshflow.process_config import Process, step_function_name_for_process


def create_refresh_pipeline(
    scope: Construct,
    construct_id: str,
    *,
    connector: str,
    company: str,
    environment: str,
    consolidate_function: _lambda.IFunction,
    bronze_ingest_definition: sfn.IChainable | None = None,
    schedule_hour: int | None = None,
    schedule_minute: int | None = None,
) -> dict[str, Any]:
    """Step Functions workflow: bronze fan-out ingest (optional) then silver consolidate."""
    prefix = construct_id

    consolidate_task = tasks.LambdaInvoke(
        scope,
        f"{prefix}SilverConsolidateTask",
        lambda_function=consolidate_function,
        payload=sfn.TaskInput.from_object(
            {
                "source": connector,
                "full_rebuild.$": "$.full_rebuild",
            }
        ),
        output_path="$.Payload",
    )

    if bronze_ingest_definition is not None:
        definition = bronze_ingest_definition.next(consolidate_task)
        timeout = Duration.hours(3)
    else:
        definition = consolidate_task
        timeout = Duration.minutes(15)

    state_machine = sfn.StateMachine(
        scope,
        f"{prefix}RefreshStateMachine",
        state_machine_name=step_function_name_for_process(
            company, environment, connector, Process.REFRESH
        ),
        definition_body=sfn.DefinitionBody.from_chainable(definition),
        timeout=timeout,
    )

    if schedule_hour is not None and schedule_minute is not None:
        schedule = events.Rule(
            scope,
            f"{prefix}RefreshSchedule",
            rule_name=eventbridge_rule_name(company, environment, connector),
            description=f"Daily {connector} refresh (bronze ingest + silver consolidate)",
            schedule=events.Schedule.cron(
                minute=str(schedule_minute),
                hour=str(schedule_hour),
            ),
        )
        schedule.add_target(
            targets.SfnStateMachine(
                state_machine,
                input=events.RuleTargetInput.from_object(
                    {
                        "full_load": False,
                        "full_rebuild": False,
                    }
                ),
            )
        )

    return {
        "state_machine": state_machine,
        "consolidate_function": consolidate_function,
    }
