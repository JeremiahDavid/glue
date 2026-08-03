from __future__ import annotations

import argparse
import sys
from pathlib import Path

from meshflow.config import load_qbo_settings
from meshflow.project_config import DEFAULT_CONFIG_PATH, resolve_qbo_ingest_entities
from meshflow.qbo.client import QBOClient
from meshflow.qbo.ingest import ingest_all, ingest_single
from meshflow.qbo.oauth import connect_quickbooks
from meshflow.secrets_manager import create_qbo_secrets_from_yaml


def create_secrets_main() -> None:
    parser = argparse.ArgumentParser(
        description="Create Meshflow QBO secrets in AWS Secrets Manager from a YAML file"
    )
    parser.add_argument(
        "--file",
        required=True,
        help="YAML file describing one or more QBO secrets to create",
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="Project config.yaml used to resolve secret names and regions (default: config.yaml)",
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="Update existing secrets with values from the YAML file",
    )
    args = parser.parse_args()

    secrets_path = Path(args.file)
    if not secrets_path.is_file():
        raise FileNotFoundError(f"Secrets file not found: {secrets_path}")

    config_path = Path(args.config)
    if not config_path.is_file():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    created, existing, updated = create_qbo_secrets_from_yaml(
        secrets_path,
        config_path=config_path,
        update_existing=args.update,
    )
    print(f"Done. Created {created}, already existed {existing}, updated {updated}.")


def auth_main() -> None:
    settings = load_qbo_settings()
    tokens = connect_quickbooks(settings)
    print("QuickBooks connected.")
    print(f"  Company realm ID: {tokens.realm_id}")
    print(f"  Tokens saved to:  AWS secret {settings.secret_id}")


def ingest_main() -> None:
    parser = argparse.ArgumentParser(description="Ingest raw entities from QuickBooks Online")
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="Project config.yaml used to resolve entity bundle (default: config.yaml)",
    )
    parser.add_argument(
        "--entity",
        help="Ingest a single entity instead of the configured bundle",
    )
    args = parser.parse_args()

    entity_bundle, entities = resolve_qbo_ingest_entities(path=Path(args.config))
    if args.entity and args.entity not in entities:
        available = ", ".join(sorted(entities))
        parser.error(f"Unknown entity {args.entity!r} for bundle {entity_bundle!r}. Available: {available}")

    settings = load_qbo_settings()
    client = QBOClient.from_saved_tokens(settings)

    if args.entity:
        import json

        result = ingest_single(client, settings, args.entity, entities=entities)
        print(json.dumps(result, indent=2))
        return

    manifest = ingest_all(
        client,
        settings,
        entities=entities,
        entity_bundle=entity_bundle,
    )
    print("QuickBooks ingest complete.")
    print(f"  Bundle: {entity_bundle}")
    print(f"  Company: {manifest.get('company_name')}")
    print(f"  Manifest: {manifest['manifest_path']}")
    for entity in manifest["entities"]:
        print(f"  - {entity['entity']}: {entity['row_count']} rows -> {entity['path']}")


def bc_ingest_main() -> None:
    import json

    parser = argparse.ArgumentParser(description="Ingest raw entities from Dynamics 365 Business Central")
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="Project config.yaml used to resolve entity bundle (default: config.yaml)",
    )
    parser.add_argument(
        "--entity",
        help="Ingest a single entity instead of the configured bundle",
    )
    parser.add_argument(
        "--full-load",
        action="store_true",
        help="Ignore incremental watermarks and pull all rows",
    )
    args = parser.parse_args()

    from meshflow.config import load_bc_settings
    from meshflow.project_config import resolve_bc_ingest_entities
    from meshflow.bc.client import BCClient
    from meshflow.bc.ingest import ingest_all, ingest_single

    entity_bundle, specs = resolve_bc_ingest_entities(path=Path(args.config))
    if args.entity and args.entity not in {spec.output_name for spec in specs}:
        available = ", ".join(sorted(spec.output_name for spec in specs))
        parser.error(f"Unknown entity {args.entity!r} for bundle {entity_bundle!r}. Available: {available}")

    settings = load_bc_settings()
    client = BCClient.from_settings(settings)
    incremental = not args.full_load

    if args.entity:
        result = ingest_single(
            client,
            settings,
            args.entity,
            specs=specs,
            incremental=incremental,
        )
        print(json.dumps(result, indent=2))
        return

    manifest = ingest_all(
        client,
        settings,
        specs=specs,
        entity_bundle=entity_bundle,
        incremental=incremental,
    )
    print("Business Central ingest complete.")
    print(f"  Bundle: {entity_bundle}")
    print(f"  Company: {manifest.get('company_name')}")
    print(f"  Manifest: {manifest['manifest_path']}")
    for entity in manifest["entities"]:
        print(f"  - {entity['entity']}: {entity['row_count']} rows -> {entity['path']}")


def qbd_soap_main() -> None:
    from meshflow.qbd.qbwc.server import main

    main()


def qbd_generate_qwc_main() -> None:
    import uuid

    from meshflow.config import load_qbd_settings
    from meshflow.qbd.qwc import build_qwc_xml

    parser = argparse.ArgumentParser(description="Generate a QuickBooks Web Connector .qwc file")
    parser.add_argument("--output", required=True, help="Output .qwc file path")
    parser.add_argument(
        "--soap-url",
        help="QBWC SOAP endpoint URL (defaults to QBWC_SOAP_URL from secret/env)",
    )
    parser.add_argument(
        "--username",
        help="QBWC username (defaults to QBD_QBWC_USERNAME from secret/env)",
    )
    args = parser.parse_args()

    settings = load_qbd_settings()
    soap_url = args.soap_url or settings.qbwc_soap_url or "http://localhost:8080/soap"
    username = args.username or settings.qbwc_username
    if not username:
        parser.error("QBWC username is required (--username or QBD_QBWC_USERNAME in secret)")

    owner_id = settings.owner_id or ("{" + str(uuid.uuid4()).upper() + "}")
    file_id = settings.file_id or ("{" + str(uuid.uuid4()).upper() + "}")

    xml = build_qwc_xml(
        app_name=settings.qbwc_app_name,
        app_url=soap_url,
        app_support_url=soap_url,
        username=username,
        owner_id=owner_id,
        file_id=file_id,
    )
    output = Path(args.output)
    output.write_text(xml, encoding="utf-8")
    print(f"Wrote {output}")
    print(f"  SOAP URL: {soap_url}")
    print(f"  Username: {username}")


def consolidate_main() -> None:
    import json
    import os

    from meshflow.project_config import (
        get_environment_config,
        iter_configured_connectors,
        resolve_aws_deploy_env,
        resolve_ingest_s3_prefix,
        resolve_raw_bucket_name,
        resolve_selection,
    )
    from meshflow.silver.consolidate import consolidate_source
    from meshflow.silver.settings import ConsolidateSettings

    parser = argparse.ArgumentParser(
        description="Consolidate bronze parquet runs into single entity tables"
    )
    parser.add_argument(
        "--source",
        help="Connector to consolidate (qbo, qbd). Defaults to all configured connectors.",
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="Project config.yaml (default: config.yaml)",
    )
    parser.add_argument(
        "--full-rebuild",
        action="store_true",
        help="Reprocess all bronze runs from scratch",
    )
    args = parser.parse_args()

    company, environment = resolve_selection(path=Path(args.config))
    env_config = get_environment_config(company, environment, path=Path(args.config))
    account, region = resolve_aws_deploy_env(env_config, environment)
    bucket = os.getenv("MESHFLOW_S3_BUCKET", "").strip() or resolve_raw_bucket_name(
        company,
        environment,
        account=account,
        region=region,
    )

    connectors = list(iter_configured_connectors(env_config))
    if args.source:
        connectors = [item for item in connectors if item[0] == args.source.strip().lower()]
        if not connectors:
            parser.error(f"Connector {args.source!r} is not configured for {company}/{environment}")

    manifests = {}
    for connector, _connector_cfg in connectors:
        prefix = resolve_ingest_s3_prefix(company, environment, source=connector, path=Path(args.config))
        settings = ConsolidateSettings(
            source=connector,
            data_dir=Path(os.getenv("MESHFLOW_DATA_DIR", "data")),
            s3_bucket=bucket or None,
            raw_prefix=prefix,
        )
        manifests[connector] = consolidate_source(settings, full_rebuild=args.full_rebuild)

    print(json.dumps(manifests, indent=2))


def athena_query_main() -> None:
    import argparse
    import time
    from pathlib import Path

    from meshflow.project_config import (
        get_environment_config,
        resolve_aws_deploy_env,
    )

    parser = argparse.ArgumentParser(description="Run a validation query in Athena")
    parser.add_argument("query", nargs="?", help="SQL to execute")
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="Project config.yaml (default: config.yaml)",
    )
    parser.add_argument(
        "--database",
        help="Glue database name (defaults from config.yaml company/environment)",
    )
    parser.add_argument(
        "--workgroup",
        help="Athena workgroup name (defaults from config.yaml company/environment)",
    )
    parser.add_argument(
        "--poll-seconds",
        type=float,
        default=2.0,
        help="Polling interval while waiting for query completion",
    )
    args = parser.parse_args()

    from meshflow.project_config import athena_workgroup_name, glue_database_name, resolve_selection

    company, environment = resolve_selection(path=Path(args.config))
    database = args.database or glue_database_name(company, environment, path=Path(args.config))
    workgroup = args.workgroup or athena_workgroup_name(company, environment, path=Path(args.config))

    if not args.query:
        parser.error("query is required")

    env_config = get_environment_config(company, environment, path=Path(args.config))
    _account, region = resolve_aws_deploy_env(env_config, environment)

    import boto3

    client = boto3.client("athena", region_name=region)
    execution = client.start_query_execution(
        QueryString=args.query,
        QueryExecutionContext={"Database": database},
        WorkGroup=workgroup,
    )
    execution_id = execution["QueryExecutionId"]
    print(f"Started query {execution_id} in {database} ({workgroup})")

    while True:
        response = client.get_query_execution(QueryExecutionId=execution_id)
        state = response["QueryExecution"]["Status"]["State"]
        if state == "SUCCEEDED":
            break
        if state in {"FAILED", "CANCELLED"}:
            reason = response["QueryExecution"]["Status"].get("StateChangeReason", state)
            raise RuntimeError(f"Athena query {state.lower()}: {reason}")
        time.sleep(args.poll_seconds)

    results = client.get_query_results(QueryExecutionId=execution_id, MaxResults=1000)
    rows = results.get("ResultSet", {}).get("Rows", [])
    for row in rows:
        values = [column.get("VarCharValue", "") for column in row.get("Data", [])]
        print("\t".join(values))


def sync_athena_catalog_main() -> None:
    import argparse
    import os

    from meshflow.project_config import (
        get_environment_config,
        iter_configured_connectors,
        resolve_aws_deploy_env,
        resolve_data_bucket_name,
        resolve_ingest_s3_prefix,
        resolve_selection,
    )
    from meshflow.catalog.glue_schema import sync_source_catalog
    from meshflow.silver.settings import ConsolidateSettings

    parser = argparse.ArgumentParser(
        description="Sync Glue table columns from silver Parquet files for Athena"
    )
    parser.add_argument(
        "--source",
        help="Connector to sync (qbo, qbd). Defaults to all configured connectors.",
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="Project config.yaml (default: config.yaml)",
    )
    args = parser.parse_args()

    company, environment = resolve_selection(path=Path(args.config))
    env_config = get_environment_config(company, environment, path=Path(args.config))
    account, region = resolve_aws_deploy_env(env_config, environment)
    bucket = os.getenv("MESHFLOW_S3_BUCKET", "").strip() or resolve_data_bucket_name(
        company,
        environment,
        account=account,
        region=region,
        path=Path(args.config),
    )

    connectors = list(iter_configured_connectors(env_config))
    if args.source:
        connectors = [item for item in connectors if item[0] == args.source.strip().lower()]
        if not connectors:
            parser.error(f"Connector {args.source!r} is not configured for {company}/{environment}")

    for connector, _connector_cfg in connectors:
        prefix = resolve_ingest_s3_prefix(
            company,
            environment,
            source=connector,
            path=Path(args.config),
        )
        settings = ConsolidateSettings(
            source=connector,
            data_dir=Path(os.getenv("MESHFLOW_DATA_DIR", "data")),
            s3_bucket=bucket or None,
            raw_prefix=prefix,
        )
        catalog = sync_source_catalog(
            settings,
            company=company,
            environment=environment,
            region=region,
        )
        for item in catalog["silver"]:
            entity = item["entity"]
            if item["status"] == "skipped":
                print(f"silver.{connector}.{entity}: skipped ({item['error']})")
                continue
            print(f"silver.{connector}.{entity}: {item['glue_columns']} columns synced")
        for item in catalog["raw"]:
            entity = item["entity"]
            if item["status"] == "skipped":
                print(f"raw.{connector}.{entity}: skipped ({item['error']})")
                continue
            print(
                f"raw.{connector}.{entity}: {item['glue_columns']} columns "
                f"across {item['run_ids']} runs"
            )


def dna_main() -> None:
    import argparse
    import json
    import os

    from meshflow.dna.compile import compile_pack
    from meshflow.dna.ingest_docs import draft_pack_from_files
    from meshflow.dna.publish import publish_staging
    from meshflow.dna.schema import load_definition_pack_file, starter_pack_path
    from meshflow.dna.settings import DnaSettings
    from meshflow.dna.validate import run_validation
    from meshflow.dna.workflow import load_production_pack, promote_pack, save_definition_pack
    from meshflow.project_config import (
        get_environment_config,
        iter_configured_connectors,
        resolve_aws_deploy_env,
        resolve_raw_bucket_name,
        resolve_selection,
    )

    parser = argparse.ArgumentParser(description="DNA Semantic Engine — compile, validate, publish")
    subparsers = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    common.add_argument("--source", help="Silver source connector (default: dbc if configured)")
    common.add_argument("--pack-id", default="bc_intra_v1")
    common.add_argument("--pack-version", help="Definition pack version to load")
    common.add_argument("--pack-file", help="Local definition pack YAML path")

    subparsers.add_parser("compile", parents=[common], help="Compile pack to staging gold")
    subparsers.add_parser("validate", parents=[common], help="Run logic regression tests")
    subparsers.add_parser("publish", parents=[common], help="Compile, validate, and publish")
    promote_parser = subparsers.add_parser("promote", parents=[common], help="Promote pack workflow status")
    promote_parser.add_argument("--target", required=True, choices=["draft", "validated", "production"])
    promote_parser.add_argument("--approver", default="")
    promote_parser.add_argument("--notes", default="")
    draft_parser = subparsers.add_parser("draft-from-docs", parents=[common], help="Draft pack from docs")
    draft_parser.add_argument("documents", nargs="+", help="Customer documentation file paths")
    serve_parser = subparsers.add_parser("serve", parents=[common], help="Run DNA web UI locally")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8080)

    portal_user_parser = subparsers.add_parser("portal-user", parents=[common], help="Manage Cognito portal users")
    portal_user_sub = portal_user_parser.add_subparsers(dest="portal_user_command", required=True)
    create_user_parser = portal_user_sub.add_parser("create", help="Create a Cognito portal user with a permanent password")
    create_user_parser.add_argument("--username", required=True)
    create_user_parser.add_argument("--client-id", required=True)
    create_user_parser.add_argument("--password", required=True)
    create_user_parser.add_argument("--email", default="")
    invite_user_parser = portal_user_sub.add_parser("invite", help="Invite a Cognito portal user by email")
    invite_user_parser.add_argument("--username", required=True)
    invite_user_parser.add_argument("--client-id", required=True)
    invite_user_parser.add_argument("--email", required=True)
    invite_user_parser.add_argument("--temporary-password", default="")
    invite_user_parser.add_argument(
        "--force",
        action="store_true",
        help="Skip the per-client seat limit check",
    )

    args = parser.parse_args()
    company, environment = resolve_selection(path=Path(args.config))
    env_config = get_environment_config(company, environment, path=Path(args.config))
    account, region = resolve_aws_deploy_env(env_config, environment)
    bucket = os.getenv("MESHFLOW_S3_BUCKET", "").strip() or resolve_raw_bucket_name(
        company,
        environment,
        account=account,
        region=region,
        path=Path(args.config),
    )

    source = args.source
    if not source:
        for connector, _cfg in iter_configured_connectors(env_config):
            if connector == "dbc":
                source = connector
                break
        if not source:
            connectors = list(iter_configured_connectors(env_config))
            source = connectors[0][0] if connectors else "dbc"

    settings = DnaSettings(
        source=source,
        data_dir=Path(os.getenv("MESHFLOW_DATA_DIR", "data")),
        s3_bucket=bucket or None,
        pack_id=args.pack_id,
        pack_version=args.pack_version,
    )

    if args.command == "draft-from-docs":
        pack = draft_pack_from_files(
            pack_id=args.pack_id,
            source_system=source,
            paths=args.documents,
        )
        path = save_definition_pack(settings, pack)
        print(json.dumps({"status": "draft_saved", "path": path, "pack": pack.to_dict()}, indent=2))
        return

    if args.pack_file:
        pack = load_definition_pack_file(args.pack_file)
    else:
        pack = load_production_pack(settings)

    if args.command == "promote":
        result = promote_pack(
            settings,
            pack,
            target_status=args.target,
            approver=args.approver,
            notes=args.notes,
        )
        print(json.dumps(result, indent=2))
        return

    if args.command == "serve":
        from meshflow.dna.web.app import run_server

        run_server(settings, host=args.host, port=args.port)
        return

    if args.command == "portal-user":
        from meshflow.dna.web.portal.cognito import create_portal_user, invite_portal_user
        from meshflow.dna.web.portal.config import load_client_portal_config

        ui_cfg = env_config.get("ui", {})
        default_pack_id = str(ui_cfg.get("pack_id", args.pack_id))

        if args.portal_user_command == "create":
            result = create_portal_user(
                username=args.username,
                password=args.password,
                client_id=args.client_id,
                email=args.email,
                company=company,
                environment=environment,
            )
            print(json.dumps({"status": "created", **result}, indent=2))
            return
        if args.portal_user_command == "invite":
            client_cfg = load_client_portal_config(
                args.client_id,
                env_config,
                default_pack_id=default_pack_id,
            )
            temp_password = args.temporary_password.strip() or None
            result = invite_portal_user(
                username=args.username,
                client_id=args.client_id,
                email=args.email,
                company=company,
                environment=environment,
                temporary_password=temp_password,
                max_users=client_cfg.max_users,
                enforce_limit=not args.force,
            )
            print(json.dumps({"status": "invited", **result}, indent=2))
            return
        raise SystemExit(f"Unsupported portal-user command: {args.portal_user_command}")

    if args.command == "compile":
        print(json.dumps(compile_pack(settings, pack), indent=2))
        return

    if args.command == "validate":
        compile_pack(settings, pack)
        print(json.dumps(run_validation(settings, pack), indent=2))
        return

    if args.command == "publish":
        compile_manifest = compile_pack(settings, pack)
        validation_result = run_validation(settings, pack)
        if validation_result["status"] != "passed":
            print(json.dumps({"status": "validation_failed", "validation": validation_result}, indent=2))
            raise SystemExit(1)
        publish_manifest = publish_staging(
            settings,
            compile_manifest=compile_manifest,
            validation_result=validation_result,
        )
        if settings.s3_bucket:
            from meshflow.catalog.glue_schema import sync_dna_catalog

            output_ids = [item["output_id"] for item in publish_manifest.get("outputs", [])]
            catalog = sync_dna_catalog(
                bucket=settings.s3_bucket,
                output_ids=output_ids,
                company=company,
                environment=environment,
                region=region,
            )
            publish_manifest["catalog"] = catalog
        print(json.dumps(publish_manifest, indent=2))
        return


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "ingest":
        sys.argv.pop(1)
        ingest_main()
    else:
        auth_main()
