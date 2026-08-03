from __future__ import annotations

from typing import Any

from aws_cdk import CfnOutput, Duration, Stack, Tags
from aws_cdk import aws_apigateway as apigateway
from aws_cdk import aws_cognito as cognito
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as _lambda
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_secretsmanager as secretsmanager
from constructs import Construct

from lambda_bundle import MeshflowLambdaRuntime, meshflow_lambda_runtime
class ReportingStack(Stack):
    """Per-portal-client reporting UI — charts, KPIs, and dashboard views over gold DNA outputs."""

    web_api: apigateway.RestApi

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        client_id: str,
        company: str,
        environment: str,
        data_bucket_name: str,
        source: str,
        client_config: dict[str, Any],
        dna_config: dict[str, Any],
        portal_user_pool: cognito.IUserPool,
        portal_user_pool_client: cognito.IUserPoolClient,
        portal_session_secret: secretsmanager.ISecret,
        domain_config: dict[str, Any],
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        if not data_bucket_name.strip():
            raise ValueError("data_bucket_name is required for ReportingStack")
        if not source.strip():
            raise ValueError("source connector is required for ReportingStack (typically dbc)")

        self._apply_cost_allocation_tags(client_id, company, environment)

        data_bucket = s3.Bucket.from_bucket_name(
            self,
            "ImportedDataBucket",
            data_bucket_name,
        )

        pack_id = str(
            client_config.get("pack_id")
            or dna_config.get("pack_id")
            or "bc_intra_v1"
        )

        lambda_runtime = meshflow_lambda_runtime(self, profile="reporting")
        reporting_fn = self._create_reporting_lambda(
            data_bucket=data_bucket,
            lambda_runtime=lambda_runtime,
            client_id=client_id,
            company=company,
            environment=environment,
            source=source,
            pack_id=pack_id,
            portal_user_pool=portal_user_pool,
            portal_user_pool_client=portal_user_pool_client,
            portal_session_secret=portal_session_secret,
            domain_config=domain_config,
        )

        self.web_api = apigateway.RestApi(
            self,
            "ReportingWebApi",
            rest_api_name=f"meshflow-reporting-{client_id}-{environment}".lower(),
            description=f"Client reporting UI for portal client {client_id} ({environment})",
            deploy_options=apigateway.StageOptions(
                stage_name="prod",
                logging_level=apigateway.MethodLoggingLevel.INFO,
                data_trace_enabled=False,
            ),
            endpoint_configuration=apigateway.EndpointConfiguration(
                types=[apigateway.EndpointType.REGIONAL]
            ),
            binary_media_types=["*/*"],
        )

        ui_integration = apigateway.LambdaIntegration(
            reporting_fn,
            proxy=True,
            allow_test_invoke=False,
        )
        self.web_api.root.add_method("ANY", ui_integration)
        self.web_api.root.add_proxy(default_integration=ui_integration, any_method=True)

        from meshflow.project_config import resolve_reporting_site_url

        reporting_url = resolve_reporting_site_url(
            domain_config,
            client_config,
            client_id,
            fallback=self.web_api.url,
        )

        CfnOutput(self, "PortalClientId", value=client_id)
        CfnOutput(self, "ReportingCompany", value=company)
        CfnOutput(self, "DataBucketName", value=data_bucket_name)
        CfnOutput(self, "ReportingFunctionName", value=reporting_fn.function_name)
        CfnOutput(self, "ReportingWebUrl", value=reporting_url)
        CfnOutput(self, "ApiGatewayUrl", value=self.web_api.url)
        CfnOutput(
            self,
            "WebApiId",
            value=self.web_api.rest_api_id,
            export_name=f"meshflow-reporting-{client_id.strip().lower().replace('_', '-')}-{environment}-web-api-id",
        )

    def _apply_cost_allocation_tags(self, client_id: str, company: str, environment: str) -> None:
        from meshflow.project_config import cost_allocation_tags

        for key, value in cost_allocation_tags(company, environment).items():
            Tags.of(self).add(key, value)
        Tags.of(self).add("PortalClientId", client_id.strip().lower())

    def _create_reporting_lambda(
        self,
        *,
        data_bucket: s3.IBucket,
        lambda_runtime: MeshflowLambdaRuntime,
        client_id: str,
        company: str,
        environment: str,
        source: str,
        pack_id: str,
        portal_user_pool: cognito.IUserPool,
        portal_user_pool_client: cognito.IUserPoolClient,
        portal_session_secret: secretsmanager.ISecret,
        domain_config: dict[str, Any],
    ) -> _lambda.Function:
        zone_name = str(domain_config.get("zone_name", "")).strip().lower().rstrip(".")
        primary_hostname = str(domain_config.get("primary_hostname", zone_name)).strip().lower().rstrip(".")
        global_login_url = f"https://{primary_hostname}/portal/login" if primary_hostname else ""

        environment_vars = {
            "MESHFLOW_UI_MODE": "reporting",
            "MESHFLOW_COMPANY": company,
            "MESHFLOW_ENVIRONMENT": environment,
            "MESHFLOW_S3_BUCKET": data_bucket.bucket_name,
            "MESHFLOW_DNA_SOURCE": source,
            "MESHFLOW_DNA_PACK_ID": pack_id,
            "MESHFLOW_PORTAL_CLIENT_ID": client_id.strip().lower(),
            "HIVEFLOW_PORTAL_COOKIE_SECURE": "true",
            "HIVEFLOW_COGNITO_USER_POOL_ID": portal_user_pool.user_pool_id,
            "HIVEFLOW_COGNITO_CLIENT_ID": portal_user_pool_client.user_pool_client_id,
            "HIVEFLOW_PORTAL_SESSION_SECRET_ARN": portal_session_secret.secret_arn,
        }
        if global_login_url:
            environment_vars["HIVEFLOW_GLOBAL_LOGIN_URL"] = global_login_url
        if zone_name:
            environment_vars["HIVEFLOW_PORTAL_COOKIE_DOMAIN"] = f".{zone_name}"

        reporting_fn = _lambda.Function(
            self,
            "ReportingUiFunction",
            function_name=f"{client_id.strip().lower()}-{environment}-reporting-ui-serve",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="meshflow.dna.web.lambda_handler.ui_handler",
            timeout=Duration.seconds(30),
            memory_size=512,
            description=(
                f"Client reporting UI for portal client {client_id}: "
                f"charts, KPIs, and dashboards for {company}/{environment}"
            ),
            code=lambda_runtime.code,
            layers=lambda_runtime.layers,
            environment=environment_vars,
        )

        data_bucket.grant_read(reporting_fn)
        portal_session_secret.grant_read(reporting_fn)
        reporting_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "cognito-idp:AdminGetUser",
                ],
                resources=[portal_user_pool.user_pool_arn],
            )
        )
        return reporting_fn
