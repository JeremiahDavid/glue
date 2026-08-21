from __future__ import annotations

from typing import Any, Callable

from aws_cdk import (
    Duration,
    aws_apigateway as apigateway,
    aws_lambda as _lambda,
    aws_s3 as s3,
    aws_secretsmanager as secretsmanager,
)
from constructs import Construct

from lambda_bundle import MeshflowLambdaRuntime


def create_qbd_soap_endpoint(
    scope: Construct,
    *,
    raw_bucket: s3.Bucket,
    credentials_secret: secretsmanager.ISecret,
    lambda_runtime: MeshflowLambdaRuntime,
    common_env: dict[str, str],
    company: str,
    environment: str,
    grant_glue_catalog_sync: Callable[..., None],
) -> dict[str, Any]:
    """QBD bronze ingest Lambda behind an API Gateway SOAP endpoint (Web Connector)."""
    from meshflow.process_config import Process, lambda_name_for_process

    soap_fn = _lambda.Function(
        scope,
        "QbdBronzeIngestFunction",
        function_name=lambda_name_for_process(company, environment, "qbd", Process.QBD_INGEST),
        runtime=_lambda.Runtime.PYTHON_3_12,
        handler="meshflow.qbd.soap_handler.soap_handler",
        timeout=Duration.minutes(2),
        memory_size=1024,
        description=(
            f"Bronze ingest for QBD via QuickBooks Web Connector ({company}/{environment})"
        ),
        code=lambda_runtime.code,
        layers=lambda_runtime.layers,
        environment={
            **common_env,
            "QBD_QBXML_VERSION": "17.0",
        },
    )

    credentials_secret.grant_read(soap_fn)
    raw_bucket.grant_read_write(soap_fn)
    grant_glue_catalog_sync(soap_fn, company=company, environment=environment)

    soap_api = apigateway.RestApi(
        scope,
        "QbdSoapApi",
        rest_api_name=f"meshflow-qbd-{company}-{environment}".lower(),
        description="QuickBooks Web Connector SOAP endpoint",
        deploy_options=apigateway.StageOptions(
            stage_name="prod",
            logging_level=apigateway.MethodLoggingLevel.INFO,
            data_trace_enabled=False,
        ),
        endpoint_configuration=apigateway.EndpointConfiguration(
            types=[apigateway.EndpointType.REGIONAL]
        ),
    )
    soap_resource = soap_api.root.add_resource("soap")
    soap_integration = apigateway.LambdaIntegration(
        soap_fn,
        proxy=True,
        allow_test_invoke=False,
    )
    for method in ("POST", "GET"):
        soap_resource.add_method(method, soap_integration)

    soap_url = f"{soap_api.url}soap"

    return {
        "function": soap_fn,
        "api": soap_api,
        "url": soap_url,
    }
