from __future__ import annotations

from typing import Any

from aws_cdk import Duration
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as targets
from aws_cdk import aws_glue as glue
from aws_cdk import aws_stepfunctions as sfn
from constructs import Construct

from dna_refresh_glue import create_dna_refresh_glue_task
from hiveflow.process_config import Process, step_function_name_for_process


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
    dna_glue_job: glue.CfnJob,
    dna_glue_default_arguments: dict[str, str],
    schedule_hour: int | None = None,
    schedule_minute: int | None = None,
    pack_id: str = "bc_intra_v1",
) -> dict[str, Any]:
    """Step Functions workflow: DNA Glue job (silver_stg → silver + gold)."""
    del source, pack_id
    prefix = construct_id

    refresh_task = create_dna_refresh_glue_task(
        scope,
        prefix,
        dna_glue_job=dna_glue_job,
        default_arguments=dna_glue_default_arguments,
    )

    state_machine = sfn.StateMachine(
        scope,
        f"{prefix}DnaRefreshStateMachine",
        state_machine_name=step_function_name_for_process(
            company, environment, "all", Process.DNA_REFRESH
        ),
        definition_body=sfn.DefinitionBody.from_chainable(refresh_task),
        timeout=Duration.hours(2),
    )

    if schedule_hour is not None and schedule_minute is not None:
        schedule = events.Rule(
            scope,
            f"{prefix}DnaRefreshSchedule",
            rule_name=dna_eventbridge_rule_name(company, environment),
            description="Daily DNA silver + gold refresh (SQL pack replay or compile fallback)",
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
        "glue_job": dna_glue_job,
    }
