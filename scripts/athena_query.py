"""Run an Athena SQL query against the Meshflow Glue catalog."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap  # noqa: E402, F401

from meshflow.project_config import (
    DEFAULT_CONFIG_PATH,
    athena_workgroup_name,
    glue_database_name,
    resolve_aws_deploy_env,
    resolve_selection,
)


def main() -> None:
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

    company, environment = resolve_selection(path=Path(args.config))
    database = args.database or glue_database_name(company, environment, path=Path(args.config))
    workgroup = args.workgroup or athena_workgroup_name(company, environment, path=Path(args.config))

    if not args.query:
        parser.error("query is required")

    from meshflow.project_config import get_environment_config

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


if __name__ == "__main__":
    main()
