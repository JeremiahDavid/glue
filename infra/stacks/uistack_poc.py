from __future__ import annotations

from typing import Any

from aws_cdk import CfnOutput, Duration, Stack, Tags, aws_apigateway as apigateway, aws_lambda as _lambda, aws_s3 as s3
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

        lambda_code = meshflow_lambda_code()
        ui_fn = self._create_ui_lambda(
            data_bucket=data_bucket,
            lambda_code=lambda_code,
            company=company,
            environment=environment,
            source=source,
            pack_id=pack_id,
            ui_config=ui_config,
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

    def _apply_cost_allocation_tags(self, company: str, environment: str) -> None:
        from meshflow.project_config import cost_allocation_tags

        for key, value in cost_allocation_tags(company, environment).items():
            Tags.of(self).add(key, value)

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
    ) -> _lambda.Function:
        from meshflow.process_config import Process, lambda_name_for_process

        portal_cfg = ui_config.get("portal", {})
        if not isinstance(portal_cfg, dict):
            portal_cfg = {}

        environment_vars = {
            "MESHFLOW_COMPANY": company,
            "MESHFLOW_ENVIRONMENT": environment,
            "MESHFLOW_S3_BUCKET": data_bucket.bucket_name,
            "MESHFLOW_DNA_SOURCE": source,
            "MESHFLOW_DNA_PACK_ID": pack_id,
            "HIVEFLOW_PORTAL_COOKIE_SECURE": "true",
        }

        secret_name = str(portal_cfg.get("credentials_secret_name", "")).strip()
        if secret_name:
            environment_vars["HIVEFLOW_PORTAL_SECRET_NAME"] = secret_name

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
        if secret_name:
            portal_secret = secretsmanager.Secret.from_secret_name_v2(
                self,
                "PortalCredentialsSecret",
                secret_name,
            )
            portal_secret.grant_read(ui_fn)
        return ui_fn
