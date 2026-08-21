from __future__ import annotations

from typing import Any

from aws_cdk import (
    Duration,
    RemovalPolicy,
    Stack,
    aws_athena as athena,
    aws_glue as glue,
    aws_s3 as s3,
)
from constructs import Construct


def create_athena_catalog(
    scope: Construct,
    *,
    data_bucket: s3.Bucket,
    company: str,
    environment: str,
    connectors: list[tuple[str, dict[str, Any]]],
) -> dict[str, Any]:
    """Athena results bucket, Glue database/tables, and workgroup for the lake."""
    from glue_catalog import (
        raw_table_props,
        sample_validation_queries,
        silver_stg_table_props,
        silver_table_props,
    )
    from meshflow.project_config import (
        athena_workgroup_name,
        glue_database_name,
        is_silver_only_catalog_entity,
        iter_catalog_entities,
        resolve_athena_results_bucket_name,
    )

    stack = Stack.of(scope)
    account = stack.account
    region = stack.region
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
        scope,
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
        scope,
        "GlueDatabase",
        catalog_id=account,
        database_input=glue.CfnDatabase.DatabaseInputProperty(
            name=database_name,
            description=f"Meshflow lake tables for {company}/{environment}",
        ),
    )

    for source, entity in catalog_entities:
        safe_id = f"{source}_{entity}".replace("-", "_")
        silver_stg_props = silver_stg_table_props(
            bucket_name=data_bucket.bucket_name,
            source=source,
            entity=entity,
        )
        silver_stg_table = glue.CfnTable(
            scope,
            f"SilverStgTable{safe_id}",
            catalog_id=account,
            database_name=database_name,
            table_input=glue.CfnTable.TableInputProperty(**silver_stg_props),
        )
        silver_stg_table.node.add_dependency(glue_database)

        silver_props = silver_table_props(
            bucket_name=data_bucket.bucket_name,
            source=source,
            entity=entity,
        )
        silver_table = glue.CfnTable(
            scope,
            f"SilverTable{safe_id}",
            catalog_id=account,
            database_name=database_name,
            table_input=glue.CfnTable.TableInputProperty(**silver_props),
        )
        silver_table.node.add_dependency(glue_database)

        if is_silver_only_catalog_entity(source, entity):
            continue

        raw_props = raw_table_props(
            bucket_name=data_bucket.bucket_name,
            source=source,
            entity=entity,
        )
        raw_table = glue.CfnTable(
            scope,
            f"RawTable{safe_id}",
            catalog_id=account,
            database_name=database_name,
            table_input=glue.CfnTable.TableInputProperty(**raw_props),
        )
        raw_table.node.add_dependency(glue_database)

    athena_workgroup = athena.CfnWorkGroup(
        scope,
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
    return {
        "results_bucket": results_bucket,
        "database_name": database_name,
        "workgroup_name": workgroup_name,
        "sample_queries": sample_queries,
    }
