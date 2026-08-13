from __future__ import annotations

from typing import Any

from aws_cdk import (
    CfnOutput,
    Duration,
    RemovalPolicy,
    Stack,
    Tags,
    aws_apigateway as apigateway,
    aws_athena as athena,
    aws_glue as glue,
    aws_iam as iam,
    aws_lambda as _lambda,
    aws_s3 as s3,
    aws_secretsmanager as secretsmanager,
)
from constructs import Construct

from lambda_bundle import LocalPythonBundling, MeshflowLambdaRuntime, meshflow_lambda_runtime

# Backward-compatible alias for tests or imports referencing the ingest stack bundler.
_LocalPythonBundling = LocalPythonBundling


class IngestStack(Stack):
    """POC ingest stack: shared S3 landing zone and per-connector compute."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        company: str,
        environment: str,
        raw_bucket_name: str,
        connectors: list[tuple[str, dict[str, Any]]],
        secret_names: dict[str, str],
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        if not raw_bucket_name.strip():
            raise ValueError(
                "Could not derive raw S3 bucket name from config.yaml for this company/environment"
            )
        if not connectors:
            raise ValueError(
                f"No connectors configured for {company}/{environment}. "
                "Add qbo and/or qbd blocks under companies.*.environments.* in config.yaml."
            )

        self._apply_cost_allocation_tags(company, environment)

        raw_bucket = s3.Bucket(
            self,
            "RawDataBucket",
            bucket_name=raw_bucket_name,
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            versioned=True,
            removal_policy=RemovalPolicy.RETAIN,
        )

        lambda_runtime = meshflow_lambda_runtime(self)
        from glue_bundle import meshflow_glue_bronze_assets

        glue_bronze_assets = meshflow_glue_bronze_assets(self)

        consolidate_fn = self._create_consolidate_lambda(
            raw_bucket=raw_bucket,
            lambda_runtime=lambda_runtime,
            company=company,
            environment=environment,
        )

        for connector, connector_cfg in connectors:
            secret_name = secret_names.get(connector, "").strip()
            if not secret_name:
                raise ValueError(
                    f"Could not derive secret name for connector {connector!r} "
                    f"({company}/{environment})"
                )

            credentials_secret = secretsmanager.Secret.from_secret_name_v2(
                self,
                f"{connector.title()}Credentials",
                secret_name,
            )
            common_env = {
                "MESHFLOW_COMPANY": company,
                "MESHFLOW_ENVIRONMENT": environment,
                "MESHFLOW_SOURCE": connector,
                "MESHFLOW_SECRET_ID": secret_name,
                "MESHFLOW_S3_BUCKET": raw_bucket.bucket_name,
                "MESHFLOW_S3_PREFIX": f"raw/{connector}",
            }

            if connector == "qbd":
                self._create_qbd_soap(
                    raw_bucket=raw_bucket,
                    credentials_secret=credentials_secret,
                    lambda_runtime=lambda_runtime,
                    common_env=common_env,
                    company=company,
                    environment=environment,
                    secret_name=secret_name,
                )
                self._create_refresh_pipeline(
                    construct_id="Qbd",
                    connector=connector,
                    company=company,
                    environment=environment,
                    consolidate_function=consolidate_fn,
                    raw_bucket=raw_bucket,
                    credentials_secret=None,
                    lambda_runtime=None,
                    common_env=None,
                    secret_name=secret_name,
                    schedule_hour=None,
                    schedule_minute=None,
                )
                continue

            if connector == "qbo":
                schedule_cfg = connector_cfg.get("schedule", {})
                if not isinstance(schedule_cfg, dict):
                    schedule_cfg = {}
                self._create_refresh_pipeline(
                    construct_id="Qbo",
                    connector=connector,
                    company=company,
                    environment=environment,
                    consolidate_function=consolidate_fn,
                    raw_bucket=raw_bucket,
                    credentials_secret=credentials_secret,
                    lambda_runtime=lambda_runtime,
                    common_env=common_env,
                    secret_name=secret_name,
                    connector_cfg=connector_cfg,
                    glue_bronze_assets=glue_bronze_assets,
                    schedule_hour=int(schedule_cfg.get("hour", 6)),
                    schedule_minute=int(schedule_cfg.get("minute", 0)),
                )
                continue

            if connector == "dbc":
                schedule_cfg = connector_cfg.get("schedule", {})
                if not isinstance(schedule_cfg, dict):
                    schedule_cfg = {}
                self._create_refresh_pipeline(
                    construct_id="Dbc",
                    connector=connector,
                    company=company,
                    environment=environment,
                    consolidate_function=consolidate_fn,
                    raw_bucket=raw_bucket,
                    credentials_secret=credentials_secret,
                    lambda_runtime=lambda_runtime,
                    common_env=common_env,
                    secret_name=secret_name,
                    connector_cfg=connector_cfg,
                    glue_bronze_assets=glue_bronze_assets,
                    schedule_hour=int(schedule_cfg.get("hour", 6)),
                    schedule_minute=int(schedule_cfg.get("minute", 0)),
                )
                continue

            raise ValueError(f"Unsupported ingest connector {connector!r}")

        self._create_athena_catalog(
            data_bucket=raw_bucket,
            company=company,
            environment=environment,
            connectors=connectors,
        )

        CfnOutput(self, "DataBucketName", value=raw_bucket.bucket_name)
        CfnOutput(self, "RawBucketName", value=raw_bucket.bucket_name)

    def _apply_cost_allocation_tags(self, company: str, environment: str) -> None:
        from meshflow.project_config import cost_allocation_tags

        for key, value in cost_allocation_tags(company, environment).items():
            Tags.of(self).add(key, value)

    def _create_refresh_pipeline(
        self,
        *,
        construct_id: str,
        connector: str,
        company: str,
        environment: str,
        consolidate_function: _lambda.Function,
        raw_bucket: s3.Bucket,
        credentials_secret: secretsmanager.ISecret | None,
        lambda_runtime: MeshflowLambdaRuntime | None,
        common_env: dict[str, str] | None,
        secret_name: str,
        connector_cfg: dict[str, Any] | None = None,
        glue_bronze_assets: Any = None,
        schedule_hour: int | None = None,
        schedule_minute: int | None = None,
    ) -> None:
        from glue_bundle import MeshflowGlueBronzeAssets
        from ingest_fanout import DEFAULT_GLUE_MAX_CAPACITY, DEFAULT_GLUE_TIMEOUT_MINUTES, create_bronze_ingest_steps
        from refresh_pipeline import create_refresh_pipeline

        bronze_ingest_definition = None
        if (
            credentials_secret is not None
            and lambda_runtime is not None
            and common_env is not None
            and glue_bronze_assets is not None
        ):
            cfg = connector_cfg if isinstance(connector_cfg, dict) else {}
            glue_max_capacity = cfg.get("glue_max_capacity", DEFAULT_GLUE_MAX_CAPACITY)
            glue_timeout_minutes = int(cfg.get("glue_timeout_minutes", DEFAULT_GLUE_TIMEOUT_MINUTES))
            bronze_resources = create_bronze_ingest_steps(
                self,
                construct_id,
                connector=connector,
                company=company,
                environment=environment,
                raw_bucket=raw_bucket,
                credentials_secret=credentials_secret,
                lambda_runtime=lambda_runtime,
                common_env=common_env,
                grant_glue_catalog_sync=self._grant_glue_catalog_sync,
                glue_assets=glue_bronze_assets,
                glue_max_capacity=float(glue_max_capacity),
                glue_timeout_minutes=glue_timeout_minutes,
            )
            bronze_ingest_definition = bronze_resources["definition"]

            output_prefix = connector.upper()
            CfnOutput(
                self,
                f"{output_prefix}BronzePrepareFunctionName",
                value=bronze_resources["prepare_function"].function_name,
            )
            CfnOutput(
                self,
                f"{output_prefix}BronzeIngestGlueJobName",
                value=bronze_resources["ingest_glue_job"].name or "",
            )
            CfnOutput(
                self,
                f"{output_prefix}BronzeFinalizeFunctionName",
                value=bronze_resources["finalize_function"].function_name,
            )

        resources = create_refresh_pipeline(
            self,
            construct_id,
            connector=connector,
            company=company,
            environment=environment,
            consolidate_function=consolidate_function,
            bronze_ingest_definition=bronze_ingest_definition,
            schedule_hour=schedule_hour,
            schedule_minute=schedule_minute,
        )

        output_prefix = connector.upper()
        if bronze_ingest_definition is not None:
            CfnOutput(self, f"{output_prefix}SecretName", value=secret_name)
        CfnOutput(
            self,
            f"{output_prefix}RefreshStateMachineArn",
            value=resources["state_machine"].state_machine_arn,
        )
        CfnOutput(
            self,
            f"{output_prefix}RefreshStateMachineName",
            value=resources["state_machine"].state_machine_name,
        )

    def _create_consolidate_lambda(
        self,
        *,
        raw_bucket: s3.Bucket,
        lambda_runtime: MeshflowLambdaRuntime,
        company: str,
        environment: str,
    ) -> _lambda.Function:
        from meshflow.process_config import Process, lambda_name_for_process

        consolidate_fn = _lambda.Function(
            self,
            "SilverConsolidateFunction",
            function_name=lambda_name_for_process(company, environment, "all", Process.CONSOLIDATE),
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="meshflow.silver.lambda_handler.lambda_handler",
            timeout=Duration.minutes(10),
            memory_size=512,
            description=(
                f"Silver consolidate: merge bronze parquet runs for {company}/{environment}"
            ),
            code=lambda_runtime.code,
            layers=lambda_runtime.layers,
            environment={
                "MESHFLOW_COMPANY": company,
                "MESHFLOW_ENVIRONMENT": environment,
                "MESHFLOW_S3_BUCKET": raw_bucket.bucket_name,
            },
        )

        raw_bucket.grant_read_write(consolidate_fn)

        self._grant_glue_catalog_sync(consolidate_fn, company=company, environment=environment)
        self._grant_athena_query(consolidate_fn, company=company, environment=environment)

        CfnOutput(self, "AllSilverConsolidateFunctionName", value=consolidate_fn.function_name)
        return consolidate_fn

    def _create_athena_catalog(
        self,
        *,
        data_bucket: s3.Bucket,
        company: str,
        environment: str,
        connectors: list[tuple[str, dict[str, Any]]],
    ) -> None:
        from glue_catalog import raw_table_props, sample_validation_queries, silver_table_props
        from meshflow.project_config import (
            athena_workgroup_name,
            glue_database_name,
            is_silver_only_catalog_entity,
            iter_catalog_entities,
            resolve_athena_results_bucket_name,
        )

        account = Stack.of(self).account
        region = Stack.of(self).region
        if not account or not region:
            raise ValueError("AWS account and region are required to create the Athena catalog")

        results_bucket_name = resolve_athena_results_bucket_name(
            company,
            environment,
            account=account,
            region=region,
        )
        database_name = glue_database_name(company, environment)
        workgroup_name = athena_workgroup_name(company, environment)
        catalog_entities = iter_catalog_entities(connectors)

        results_bucket = s3.Bucket(
            self,
            "AthenaResultsBucket",
            bucket_name=results_bucket_name,
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            lifecycle_rules=[
                s3.LifecycleRule(expiration=Duration.days(30), enabled=True),
            ],
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        glue_database = glue.CfnDatabase(
            self,
            "GlueDatabase",
            catalog_id=account,
            database_input=glue.CfnDatabase.DatabaseInputProperty(
                name=database_name,
                description=f"Meshflow lake tables for {company}/{environment}",
            ),
        )

        for source, entity in catalog_entities:
            safe_id = f"{source}_{entity}".replace("-", "_")
            silver_props = silver_table_props(
                bucket_name=data_bucket.bucket_name,
                source=source,
                entity=entity,
            )
            silver_table = glue.CfnTable(
                self,
                f"SilverTable{safe_id}",
                catalog_id=account,
                database_name=database_name,
                table_input=glue.CfnTable.TableInputProperty(**silver_props),
            )
            silver_table.add_dependency(glue_database)

            if is_silver_only_catalog_entity(source, entity):
                continue

            raw_props = raw_table_props(
                bucket_name=data_bucket.bucket_name,
                source=source,
                entity=entity,
            )
            raw_table = glue.CfnTable(
                self,
                f"RawTable{safe_id}",
                catalog_id=account,
                database_name=database_name,
                table_input=glue.CfnTable.TableInputProperty(**raw_props),
            )
            raw_table.add_dependency(glue_database)

        athena_workgroup = athena.CfnWorkGroup(
            self,
            "AthenaWorkGroup",
            name=workgroup_name,
            description=f"Meshflow validation queries for {company}/{environment}",
            recursive_delete_option=False,
            state="ENABLED",
            work_group_configuration=athena.CfnWorkGroup.WorkGroupConfigurationProperty(
                enforce_work_group_configuration=True,
                publish_cloud_watch_metrics_enabled=True,
                result_configuration=athena.CfnWorkGroup.ResultConfigurationProperty(
                    output_location=f"s3://{results_bucket.bucket_name}/",
                ),
            ),
        )
        athena_workgroup.node.add_dependency(results_bucket)

        sample_queries = sample_validation_queries(database_name, catalog_entities)
        CfnOutput(self, "GlueDatabaseName", value=database_name)
        CfnOutput(self, "AthenaWorkGroupName", value=workgroup_name)
        CfnOutput(self, "AthenaResultsBucketName", value=results_bucket.bucket_name)
        if sample_queries:
            CfnOutput(
                self,
                "AthenaSampleQuery",
                value=sample_queries[0],
                description="Example Athena query for silver row counts",
            )

    def _grant_glue_catalog_sync(
        self,
        principal: iam.IRole | _lambda.Function,
        *,
        company: str,
        environment: str,
    ) -> None:
        from meshflow.project_config import glue_database_name

        database_name = glue_database_name(company, environment)
        policy = iam.PolicyStatement(
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
        if isinstance(principal, _lambda.Function):
            principal.add_to_role_policy(policy)
        else:
            principal.add_to_policy(policy)

    def _grant_athena_query(
        self,
        fn: _lambda.Function,
        *,
        company: str,
        environment: str,
    ) -> None:
        """Allow deterministic SQL pack replay / validation against the company workgroup."""
        from meshflow.project_config import (
            athena_workgroup_name,
            glue_database_name,
            resolve_athena_results_bucket_name,
        )

        database_name = glue_database_name(company, environment)
        workgroup = athena_workgroup_name(company, environment)
        results_bucket = resolve_athena_results_bucket_name(
            company,
            environment,
            account=Stack.of(self).account,
            region=Stack.of(self).region,
        )
        fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "athena:StartQueryExecution",
                    "athena:GetQueryExecution",
                    "athena:GetQueryResults",
                    "athena:StopQueryExecution",
                    "athena:GetWorkGroup",
                ],
                resources=["*"],
            )
        )
        fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "glue:GetDatabase",
                    "glue:GetDatabases",
                    "glue:GetTable",
                    "glue:GetTables",
                    "glue:GetPartition",
                    "glue:GetPartitions",
                ],
                resources=[
                    f"arn:aws:glue:{Stack.of(self).region}:{Stack.of(self).account}:catalog",
                    f"arn:aws:glue:{Stack.of(self).region}:{Stack.of(self).account}:database/{database_name}",
                    f"arn:aws:glue:{Stack.of(self).region}:{Stack.of(self).account}:table/{database_name}/*",
                ],
            )
        )
        fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "s3:GetBucketLocation",
                    "s3:GetObject",
                    "s3:ListBucket",
                    "s3:PutObject",
                    "s3:DeleteObject",
                ],
                resources=[
                    f"arn:aws:s3:::{results_bucket}",
                    f"arn:aws:s3:::{results_bucket}/*",
                ],
            )
        )
        # Workgroup name is informational for IAM scoping when using identity-based policies.
        _ = workgroup

    def _create_qbd_soap(
        self,
        *,
        raw_bucket: s3.Bucket,
        credentials_secret: secretsmanager.ISecret,
        lambda_runtime: MeshflowLambdaRuntime,
        common_env: dict[str, str],
        company: str,
        environment: str,
        secret_name: str,
    ) -> None:
        from meshflow.process_config import Process, lambda_name_for_process

        soap_fn = _lambda.Function(
            self,
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
        self._grant_glue_catalog_sync(soap_fn, company=company, environment=environment)

        soap_api = apigateway.RestApi(
            self,
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

        CfnOutput(self, "QbdSecretName", value=secret_name)
        CfnOutput(self, "QbdBronzeIngestFunctionName", value=soap_fn.function_name)
        CfnOutput(self, "QbdSoapUrl", value=soap_url)
