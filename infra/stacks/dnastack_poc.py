from __future__ import annotations

from typing import Any

from aws_cdk import (
    CfnOutput,
    CustomResource,
    Duration,
    Stack,
    Tags,
    aws_iam as iam,
    aws_lambda as _lambda,
    aws_s3 as s3,
    custom_resources as cr,
)
from constructs import Construct

from lambda_bundle import MeshflowLambdaRuntime, meshflow_lambda_runtime


class DnaStack(Stack):
    """DNA Semantic Engine stack — independent of ingest; reads silver, writes gold."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        company: str,
        environment: str,
        data_bucket_name: str,
        source: str,
        dna_config: dict[str, Any],
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        if not data_bucket_name.strip():
            raise ValueError("data_bucket_name is required for DnaStack")
        if not source.strip():
            raise ValueError("source connector is required for DnaStack (typically dbc)")

        self._apply_cost_allocation_tags(company, environment)

        data_bucket = s3.Bucket.from_bucket_name(
            self,
            "ImportedDataBucket",
            data_bucket_name,
        )

        from meshflow.storage.paths import company_dna_config_id

        # Gold semantic layer always uses the company DNA config pack.
        pack_id = company_dna_config_id(company)
        lambda_runtime = meshflow_lambda_runtime(self)
        dna_publish_fn = self._create_dna_publish_lambda(
            data_bucket=data_bucket,
            lambda_runtime=lambda_runtime,
            company=company,
            environment=environment,
            pack_id=pack_id,
        )

        schedule_cfg = dna_config.get("schedule", {})
        if not isinstance(schedule_cfg, dict):
            schedule_cfg = {}
        schedule_hour = schedule_cfg.get("hour")
        schedule_minute = schedule_cfg.get("minute")
        if schedule_hour is not None:
            schedule_hour = int(schedule_hour)
        if schedule_minute is not None:
            schedule_minute = int(schedule_minute)

        from dna_pipeline import create_dna_pipeline

        resources = create_dna_pipeline(
            self,
            "Dna",
            company=company,
            environment=environment,
            source=source,
            dna_publish_function=dna_publish_fn,
            schedule_hour=schedule_hour,
            schedule_minute=schedule_minute,
            pack_id=pack_id,
        )

        self._seed_governance_on_deploy(
            dna_publish_fn,
            company=company,
            environment=environment,
            pack_id=pack_id,
        )

        CfnOutput(self, "DataBucketName", value=data_bucket_name)
        CfnOutput(self, "DnaPublishFunctionName", value=dna_publish_fn.function_name)
        CfnOutput(
            self,
            "DnaRefreshStateMachineArn",
            value=resources["state_machine"].state_machine_arn,
        )
        CfnOutput(
            self,
            "DnaRefreshStateMachineName",
            value=resources["state_machine"].state_machine_name,
        )

    def _apply_cost_allocation_tags(self, company: str, environment: str) -> None:
        from meshflow.project_config import cost_allocation_tags

        for key, value in cost_allocation_tags(company, environment).items():
            Tags.of(self).add(key, value)

    def _seed_governance_on_deploy(
        self,
        dna_publish_fn: _lambda.Function,
        *,
        company: str,
        environment: str,
        pack_id: str,
    ) -> None:
        """Seed governance boilerplates on stack create/update via CFN Provider.

        Uses a Provider (not AwsCustomResource Lambda invoke) so handler failures
        fail the deploy instead of reporting CREATE_COMPLETE with FunctionError.
        """
        provider = cr.Provider(
            self,
            "GovernanceInitProvider",
            on_event_handler=dna_publish_fn,
        )
        # Distinct id from the previous AwsCustomResource so CFN replaces the broken seed.
        seed = CustomResource(
            self,
            "InitClientGovernanceV2",
            service_token=provider.service_token,
            properties={
                "pack_id": pack_id,
                # Bump to force re-invoke after seed logic changes.
                "seed_revision": "20260804-company-dna-config",
                "company": company,
                "environment": environment,
            },
        )
        seed.node.add_dependency(dna_publish_fn)
        CfnOutput(
            self,
            "GovernanceInitResource",
            value=f"{company.lower()}-{environment}-governance-init-v2",
            description="Custom resource that seeds governance/ on DnaStack deploy (skips if present)",
        )

    def _create_dna_publish_lambda(
        self,
        *,
        data_bucket: s3.IBucket,
        lambda_runtime: MeshflowLambdaRuntime,
        company: str,
        environment: str,
        pack_id: str,
    ) -> _lambda.Function:
        from meshflow.process_config import Process, lambda_name_for_process

        dna_fn = _lambda.Function(
            self,
            "DnaPublishFunction",
            function_name=lambda_name_for_process(company, environment, "all", Process.DNA_PUBLISH),
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="meshflow.dna.lambda_handler.lambda_handler",
            timeout=Duration.minutes(10),
            memory_size=512,
            description=(
                f"DNA publish: compile, validate, and publish certified gold tables "
                f"for {company}/{environment}"
            ),
            code=lambda_runtime.code,
            layers=lambda_runtime.layers,
            environment={
                "MESHFLOW_COMPANY": company,
                "MESHFLOW_ENVIRONMENT": environment,
                "MESHFLOW_S3_BUCKET": data_bucket.bucket_name,
                "MESHFLOW_DNA_PACK_ID": pack_id,  # {company}_dna_config
            },
        )

        data_bucket.grant_read_write(dna_fn)
        self._grant_glue_catalog_sync(dna_fn, company=company, environment=environment)
        return dna_fn

    def _grant_glue_catalog_sync(
        self,
        fn: _lambda.Function,
        *,
        company: str,
        environment: str,
    ) -> None:
        from meshflow.project_config import glue_database_name

        database_name = glue_database_name(company, environment)
        fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "glue:CreateTable",
                    "glue:DeleteTable",
                    "glue:GetTable",
                    "glue:UpdateTable",
                ],
                resources=[
                    f"arn:aws:glue:{Stack.of(self).region}:{Stack.of(self).account}:catalog",
                    f"arn:aws:glue:{Stack.of(self).region}:{Stack.of(self).account}:database/{database_name}",
                    f"arn:aws:glue:{Stack.of(self).region}:{Stack.of(self).account}:table/{database_name}/*",
                ],
            )
        )
