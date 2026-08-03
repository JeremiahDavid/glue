from __future__ import annotations

from typing import Any

from aws_cdk import CfnOutput, Duration, RemovalPolicy, Stack, Tags
from aws_cdk import aws_apigateway as apigateway
from aws_cdk import aws_cognito as cognito
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as _lambda
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_secretsmanager as secretsmanager
from constructs import Construct

from lambda_bundle import meshflow_lambda_code
from ui_domain import attach_custom_domain


class UiStack(Stack):
    """DNA reporting web UI — API Gateway + Lambda serving read-only gold views."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        company: str,
        environment: str,
        data_bucket_name: str,
        source: str,
        ui_config: dict[str, Any],
        dna_config: dict[str, Any],
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        if not data_bucket_name.strip():
            raise ValueError("data_bucket_name is required for UiStack")
        if not source.strip():
            raise ValueError("source connector is required for UiStack (typically dbc)")

        self._apply_cost_allocation_tags(company, environment)

        data_bucket = s3.Bucket.from_bucket_name(
            self,
            "ImportedDataBucket",
            data_bucket_name,
        )

        pack_id = str(
            ui_config.get("pack_id")
            or dna_config.get("pack_id")
            or "bc_intra_v1"
        )

        portal_resources = self._create_portal_user_pool(company=company, environment=environment, ui_config=ui_config)

        lambda_code = meshflow_lambda_code()
        ui_fn = self._create_ui_lambda(
            data_bucket=data_bucket,
            lambda_code=lambda_code,
            company=company,
            environment=environment,
            source=source,
            pack_id=pack_id,
            ui_config=ui_config,
            portal_resources=portal_resources,
        )

        web_api = apigateway.RestApi(
            self,
            "DnaReportingApi",
            rest_api_name=f"meshflow-ui-{company}-{environment}".lower(),
            description=f"Meshflow DNA reporting UI for {company}/{environment}",
            deploy_options=apigateway.StageOptions(
                stage_name="prod",
                logging_level=apigateway.MethodLoggingLevel.INFO,
                data_trace_enabled=False,
            ),
            endpoint_configuration=apigateway.EndpointConfiguration(
                types=[apigateway.EndpointType.REGIONAL]
            ),
            # Required for PNG/SVG favicon and logo assets via Lambda proxy integration.
            binary_media_types=["*/*"],
        )

        ui_integration = apigateway.LambdaIntegration(
            ui_fn,
            proxy=True,
            allow_test_invoke=False,
        )
        web_api.root.add_method("ANY", ui_integration)
        web_api.root.add_proxy(default_integration=ui_integration, any_method=True)

        reporting_url = web_api.url
        domain_cfg = ui_config.get("domain", {})
        if isinstance(domain_cfg, dict) and str(domain_cfg.get("zone_name", "")).strip():
            domain_resources = attach_custom_domain(
                self,
                web_api=web_api,
                domain_config=domain_cfg,
            )
            reporting_url = domain_resources["custom_urls"][0]

        CfnOutput(self, "DataBucketName", value=data_bucket_name)
        CfnOutput(self, "UiFunctionName", value=ui_fn.function_name)
        CfnOutput(self, "ReportingWebUrl", value=reporting_url)
        CfnOutput(self, "ApiGatewayUrl", value=web_api.url)
        CfnOutput(self, "PortalUserPoolId", value=portal_resources["user_pool"].user_pool_id)
        CfnOutput(self, "PortalUserPoolClientId", value=portal_resources["user_pool_client"].user_pool_client_id)

    def _apply_cost_allocation_tags(self, company: str, environment: str) -> None:
        from meshflow.project_config import cost_allocation_tags

        for key, value in cost_allocation_tags(company, environment).items():
            Tags.of(self).add(key, value)

    def _create_portal_user_pool(
        self,
        *,
        company: str,
        environment: str,
        ui_config: dict[str, Any],
    ) -> dict[str, Any]:
        portal_cfg = ui_config.get("portal", {})
        if not isinstance(portal_cfg, dict):
            portal_cfg = {}

        default_client_id = str(portal_cfg.get("default_client_id", company)).strip().lower() or company.lower()
        pool_name = f"meshflow-portal-{company}-{environment}".lower()
        portal_login_url = "https://hive-flow-ai.com/portal/login"
        domain_cfg = ui_config.get("domain", {})
        if isinstance(domain_cfg, dict):
            primary_hostname = str(domain_cfg.get("primary_hostname", "")).strip()
            if primary_hostname:
                portal_login_url = f"https://{primary_hostname}/portal/login"

        user_pool = cognito.UserPool(
            self,
            "PortalUserPool",
            user_pool_name=pool_name,
            sign_in_aliases=cognito.SignInAliases(username=True, email=True),
            auto_verify=cognito.AutoVerifiedAttrs(email=True),
            standard_attributes=cognito.StandardAttributes(
                email=cognito.StandardAttribute(required=False, mutable=True),
            ),
            custom_attributes={
                "client_id": cognito.StringAttribute(min_len=1, max_len=64, mutable=True),
                "portal_role": cognito.StringAttribute(min_len=1, max_len=16, mutable=True),
            },
            password_policy=cognito.PasswordPolicy(
                min_length=12,
                require_lowercase=True,
                require_uppercase=True,
                require_digits=True,
                require_symbols=False,
            ),
            account_recovery=cognito.AccountRecovery.EMAIL_ONLY,
            user_invitation=cognito.UserInvitationConfig(
                email_subject="Your HiveFlowAI portal account",
                email_body=(
                    "You have been invited to the HiveFlowAI client portal.\n\n"
                    "Username: {username}\n"
                    "Temporary password: {####}\n\n"
                    f"Sign in at {portal_login_url} and set a new password when prompted."
                ),
            ),
            removal_policy=RemovalPolicy.RETAIN,
        )

        user_pool_client = user_pool.add_client(
            "PortalUserPoolClient",
            user_pool_client_name=f"{pool_name}-web",
            auth_flows=cognito.AuthFlow(
                admin_user_password=True,
                user_password=True,
            ),
            generate_secret=False,
        )

        session_secret = secretsmanager.Secret(
            self,
            "PortalSessionSecret",
            secret_name=f"meshflow-{company.lower()}-portal-session-{environment.lower()}",
            description=f"HiveFlowAI portal session signing secret for {company}/{environment}",
            generate_secret_string=secretsmanager.SecretStringGenerator(
                password_length=48,
                exclude_punctuation=True,
            ),
        )

        return {
            "user_pool": user_pool,
            "user_pool_client": user_pool_client,
            "session_secret": session_secret,
            "default_client_id": default_client_id,
        }

    def _create_ui_lambda(
        self,
        *,
        data_bucket: s3.IBucket,
        lambda_code: _lambda.Code,
        company: str,
        environment: str,
        source: str,
        pack_id: str,
        ui_config: dict[str, Any],
        portal_resources: dict[str, Any],
    ) -> _lambda.Function:
        from meshflow.process_config import Process, lambda_name_for_process

        user_pool: cognito.UserPool = portal_resources["user_pool"]
        user_pool_client: cognito.UserPoolClient = portal_resources["user_pool_client"]
        session_secret: secretsmanager.Secret = portal_resources["session_secret"]
        default_client_id: str = portal_resources["default_client_id"]

        environment_vars = {
            "MESHFLOW_COMPANY": company,
            "MESHFLOW_ENVIRONMENT": environment,
            "MESHFLOW_S3_BUCKET": data_bucket.bucket_name,
            "MESHFLOW_DNA_SOURCE": source,
            "MESHFLOW_DNA_PACK_ID": pack_id,
            "HIVEFLOW_PORTAL_COOKIE_SECURE": "true",
            "HIVEFLOW_COGNITO_USER_POOL_ID": user_pool.user_pool_id,
            "HIVEFLOW_COGNITO_CLIENT_ID": user_pool_client.user_pool_client_id,
            "HIVEFLOW_PORTAL_DEFAULT_CLIENT_ID": default_client_id,
            "HIVEFLOW_PORTAL_SESSION_SECRET_ARN": session_secret.secret_arn,
        }

        branding_cfg = ui_config.get("branding", {})
        branding_bucket_name = ""
        if isinstance(branding_cfg, dict):
            branding_bucket_name = str(branding_cfg.get("bucket", "")).strip()
            symbol_key = str(branding_cfg.get("symbol_key", "")).strip()
            logo_key = str(branding_cfg.get("logo_key", "")).strip()
            if branding_bucket_name:
                environment_vars["HIVEFLOW_BRANDING_BUCKET"] = branding_bucket_name
            if symbol_key:
                environment_vars["HIVEFLOW_BRANDING_SYMBOL_KEY"] = symbol_key
            if logo_key:
                environment_vars["HIVEFLOW_BRANDING_LOGO_KEY"] = logo_key

        ui_fn = _lambda.Function(
            self,
            "UiServeFunction",
            function_name=lambda_name_for_process(company, environment, "all", Process.UI_SERVE),
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="meshflow.dna.web.lambda_handler.ui_handler",
            timeout=Duration.seconds(30),
            memory_size=512,
            description=(
                f"HiveFlowAI reporting UI for {company}/{environment} — public site + client portal"
            ),
            code=lambda_code,
            environment=environment_vars,
        )

        data_bucket.grant_read(ui_fn)
        if branding_bucket_name:
            s3.Bucket.from_bucket_name(
                self,
                "BrandingBucket",
                branding_bucket_name,
            ).grant_read(ui_fn)

        session_secret.grant_read(ui_fn)
        ui_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "cognito-idp:AdminInitiateAuth",
                    "cognito-idp:AdminRespondToAuthChallenge",
                    "cognito-idp:AdminGetUser",
                    "cognito-idp:AdminCreateUser",
                    "cognito-idp:AdminDeleteUser",
                    "cognito-idp:ListUsers",
                ],
                resources=[user_pool.user_pool_arn],
            )
        )
        return ui_fn
