from __future__ import annotations

from aws_cdk import (
    CfnOutput,
    Duration,
    Stack,
    Tags,
    aws_events as events,
    aws_events_targets as targets,
    aws_iam as iam,
    aws_lambda as _lambda,
    aws_s3 as s3,
)
from constructs import Construct

from lambda_bundle import meshflow_lambda_runtime

SOURCE_DOCUMENTATION_BUCKET_NAME = "hiveflowai-source-documentation"


class SourceDocsStack(Stack):
    """Global source documentation — biweekly Microsoft Learn Properties scrape."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        environment: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        Tags.of(self).add("meshflow:component", "source-docs")
        Tags.of(self).add("meshflow:environment", environment.strip().lower())

        # Fixed global bucket for shared connector documentation (all tenants).
        # Import by name so an existing hiveflowai-source-documentation bucket is reused.
        docs_bucket = s3.Bucket.from_bucket_name(
            self,
            "SourceDocumentationBucket",
            SOURCE_DOCUMENTATION_BUCKET_NAME,
        )

        lambda_runtime = meshflow_lambda_runtime(self, profile="full")
        scrape_fn = _lambda.Function(
            self,
            "BcSourceDocsScrapeFunction",
            function_name=f"platform-{environment.strip().lower()}-bc-source-docs-scrape",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="meshflow.bc.source_docs_handler.lambda_handler",
            timeout=Duration.minutes(15),
            memory_size=512,
            description=(
                "Scrape Microsoft Learn APV2 Properties tables into "
                f"s3://{SOURCE_DOCUMENTATION_BUCKET_NAME}/dbc/"
            ),
            code=lambda_runtime.code,
            layers=lambda_runtime.layers,
            environment={
                "MESHFLOW_SOURCE_DOCS_BUCKET": SOURCE_DOCUMENTATION_BUCKET_NAME,
                "MESHFLOW_SOURCE_DOCS_OBJECT_KEY": "dbc/entity_properties.yaml",
                "MESHFLOW_ENVIRONMENT": environment.strip().lower(),
            },
        )

        docs_bucket.grant_read_write(scrape_fn)
        scrape_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["s3:ListBucket"],
                resources=[docs_bucket.bucket_arn],
            )
        )
        scrape_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["s3:GetObject", "s3:PutObject", "s3:AbortMultipartUpload"],
                resources=[f"{docs_bucket.bucket_arn}/dbc/*"],
            )
        )

        schedule = events.Rule(
            self,
            "BcSourceDocsScrapeSchedule",
            rule_name=f"platform-{environment.strip().lower()}-bc-source-docs-scrape",
            description="Biweekly Microsoft Learn APV2 Properties scrape for DBC source docs",
            schedule=events.Schedule.rate(Duration.days(14)),
        )
        schedule.add_target(
            targets.LambdaFunction(
                scrape_fn,
                event=events.RuleTargetInput.from_object(
                    {
                        "source": "dbc",
                        "delay_seconds": 0.35,
                    }
                ),
            )
        )

        CfnOutput(self, "SourceDocumentationBucketName", value=docs_bucket.bucket_name)
        CfnOutput(self, "SourceDocumentationBucketArn", value=docs_bucket.bucket_arn)
        CfnOutput(self, "BcSourceDocsScrapeFunctionName", value=scrape_fn.function_name)
        CfnOutput(self, "BcSourceDocsScrapeScheduleName", value=schedule.rule_name)
