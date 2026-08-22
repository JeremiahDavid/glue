from __future__ import annotations

from aws_cdk import (
    CfnOutput,
    Duration,
    Stack,
    Tags,
    aws_iam as iam,
    aws_lambda as _lambda,
    aws_s3 as s3,
)
from constructs import Construct

from lambda_bundle import hiveflow_lambda_runtime

SOURCE_DOCUMENTATION_BUCKET_NAME = "hiveflowai-source-documentation"
_DEFAULT_BEDROCK_MODEL_ID = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
_DEFAULT_CONNECTOR_SOURCE = "dbc"


class GlobalDnaStack(Stack):
    """Client-agnostic DNA platform jobs — global MS Learn source-docs pipeline."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        environment: str,
        source: str = _DEFAULT_CONNECTOR_SOURCE,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        env = environment.strip().lower()
        connector = source.strip().lower() or _DEFAULT_CONNECTOR_SOURCE
        Tags.of(self).add("hiveflow:component", "global-dna")
        Tags.of(self).add("hiveflow:environment", env)

        from hiveflow.project_config import cost_allocation_tags

        for key, value in cost_allocation_tags("PLATFORM", env).items():
            Tags.of(self).add(key, value)

        docs_bucket = s3.Bucket.from_bucket_name(
            self,
            "SourceDocumentationBucket",
            SOURCE_DOCUMENTATION_BUCKET_NAME,
        )

        lambda_runtime = hiveflow_lambda_runtime(self, profile="full")

        def _grant_docs_bucket(fn: _lambda.Function) -> None:
            docs_bucket.grant_read_write(fn)
            fn.add_to_role_policy(
                iam.PolicyStatement(
                    actions=["s3:ListBucket"],
                    resources=[docs_bucket.bucket_arn],
                )
            )
            fn.add_to_role_policy(
                iam.PolicyStatement(
                    actions=["s3:GetObject", "s3:PutObject", "s3:AbortMultipartUpload"],
                    resources=[f"{docs_bucket.bucket_arn}/{connector}/*"],
                )
            )

        def _grant_bedrock(fn: _lambda.Function) -> None:
            fn.add_to_role_policy(
                iam.PolicyStatement(
                    actions=[
                        "bedrock:InvokeModel",
                        "bedrock:InvokeModelWithResponseStream",
                        "bedrock:Converse",
                        "bedrock:ConverseStream",
                        "aws-marketplace:ViewSubscriptions",
                        "aws-marketplace:Subscribe",
                        "aws-marketplace:Unsubscribe",
                    ],
                    resources=["*"],
                )
            )

        relationships_fn = _lambda.Function(
            self,
            "BcSourceDocsRelationshipsFunction",
            function_name=f"platform-{env}-bc-source-docs-relationships",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="hiveflow.dna.source_docs.handlers.relationships.lambda_handler",
            timeout=Duration.minutes(5),
            memory_size=512,
            description=(
                "Derive PK/FK relationships from "
                f"s3://{SOURCE_DOCUMENTATION_BUCKET_NAME}/{connector}/entity_properties.yaml"
            ),
            code=lambda_runtime.code,
            layers=lambda_runtime.layers,
            environment={
                "HIVEFLOW_SOURCE_DOCS_BUCKET": SOURCE_DOCUMENTATION_BUCKET_NAME,
                "HIVEFLOW_SOURCE_DOCS_OBJECT_KEY": f"{connector}/entity_properties.yaml",
                "HIVEFLOW_SOURCE_DOCS_RELATIONSHIPS_OBJECT_KEY": f"{connector}/entity_relationships.yaml",
                "HIVEFLOW_BEDROCK_MODEL_ID": _DEFAULT_BEDROCK_MODEL_ID,
                "HIVEFLOW_ENVIRONMENT": env,
            },
        )
        _grant_docs_bucket(relationships_fn)
        _grant_bedrock(relationships_fn)

        tags_fn = _lambda.Function(
            self,
            "BcSourceDocsTagsFunction",
            function_name=f"platform-{env}-bc-source-docs-tags",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="hiveflow.dna.source_docs.handlers.tags.lambda_handler",
            timeout=Duration.minutes(15),
            memory_size=1024,
            description=(
                "Generate conceptual property tags from "
                f"s3://{SOURCE_DOCUMENTATION_BUCKET_NAME}/{connector}/entity_properties.yaml"
            ),
            code=lambda_runtime.code,
            layers=lambda_runtime.layers,
            environment={
                "HIVEFLOW_SOURCE_DOCS_BUCKET": SOURCE_DOCUMENTATION_BUCKET_NAME,
                "HIVEFLOW_SOURCE_DOCS_OBJECT_KEY": f"{connector}/entity_properties.yaml",
                "HIVEFLOW_SOURCE_DOCS_TAGS_OBJECT_KEY": f"{connector}/entity_property_tags.yaml",
                "HIVEFLOW_BEDROCK_MODEL_ID": _DEFAULT_BEDROCK_MODEL_ID,
                "HIVEFLOW_ENVIRONMENT": env,
            },
        )
        _grant_docs_bucket(tags_fn)
        _grant_bedrock(tags_fn)

        scrape_fn = _lambda.Function(
            self,
            "BcSourceDocsScrapeFunction",
            function_name=f"platform-{env}-bc-source-docs-scrape",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="hiveflow.dna.source_docs.handlers.scrape.lambda_handler",
            timeout=Duration.minutes(15),
            memory_size=512,
            description=(
                "Scrape Microsoft Learn APV2 Properties tables into "
                f"s3://{SOURCE_DOCUMENTATION_BUCKET_NAME}/{connector}/"
            ),
            code=lambda_runtime.code,
            layers=lambda_runtime.layers,
            environment={
                "HIVEFLOW_SOURCE_DOCS_BUCKET": SOURCE_DOCUMENTATION_BUCKET_NAME,
                "HIVEFLOW_SOURCE_DOCS_OBJECT_KEY": f"{connector}/entity_properties.yaml",
                "HIVEFLOW_SOURCE_DOCS_RELATIONSHIPS_FUNCTION": relationships_fn.function_name,
                "HIVEFLOW_SOURCE_DOCS_TAGS_FUNCTION": tags_fn.function_name,
                "HIVEFLOW_ENVIRONMENT": env,
            },
        )
        _grant_docs_bucket(scrape_fn)
        relationships_fn.grant_invoke(scrape_fn)
        tags_fn.grant_invoke(scrape_fn)

        CfnOutput(self, "SourceDocumentationBucketName", value=docs_bucket.bucket_name)
        CfnOutput(self, "SourceDocumentationBucketArn", value=docs_bucket.bucket_arn)
        CfnOutput(self, "BcSourceDocsScrapeFunctionName", value=scrape_fn.function_name)
        CfnOutput(self, "BcSourceDocsRelationshipsFunctionName", value=relationships_fn.function_name)
        CfnOutput(self, "BcSourceDocsTagsFunctionName", value=tags_fn.function_name)
