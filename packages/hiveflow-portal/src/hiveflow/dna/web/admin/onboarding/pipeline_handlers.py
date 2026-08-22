"""Onboarding pipeline kickoffs and ingest validation for platform admin."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from hiveflow.compat import UTC
from typing import Any, Callable

from hiveflow.client_registry import ClientRecord
from hiveflow.process_config import Process, step_function_name_for_process
from hiveflow.project_config import (
    get_environment_config,
    resolve_aws_deploy_env,
    resolve_data_bucket_name,
    resolve_ingest_s3_prefix,
)

_EXECUTION_NAME_RE = re.compile(r"[^a-zA-Z0-9_-]")
_ACTIVE_EXECUTION_STATUSES = frozenset({"running", "pending_redrive"})


def build_ingest_validation_report(manifest: dict[str, Any]) -> dict[str, Any]:
    """Summarize a bronze ingest manifest for the validation overlay."""
    entities = manifest.get("entities")
    if not isinstance(entities, list):
        entities = []

    tables: list[dict[str, Any]] = []
    failed_tables: list[dict[str, Any]] = []
    for item in entities:
        if not isinstance(item, dict):
            continue
        table_name = str(item.get("entity") or item.get("table") or "unknown").strip() or "unknown"
        row_count = item.get("row_count")
        try:
            parsed_rows = int(row_count) if row_count is not None else 0
        except (TypeError, ValueError):
            parsed_rows = 0
        entry = {
            "table": table_name,
            "row_count": parsed_rows,
            "status": str(item.get("status") or "ok"),
        }
        if entry["status"] == "failed":
            failed_tables.append(entry)
        else:
            tables.append(entry)

    tables.sort(key=lambda row: row["table"])
    failed_tables.sort(key=lambda row: row["table"])
    summary = manifest.get("ingest_summary")
    if not isinstance(summary, dict):
        summary = {}

    return {
        "source": str(manifest.get("source") or ""),
        "ingested_at": str(manifest.get("ingested_at") or ""),
        "table_count": len(tables),
        "failed_table_count": len(failed_tables),
        "total_rows": sum(int(row["row_count"]) for row in tables),
        "tables": tables,
        "failed_tables": failed_tables,
        "ingest_summary": {
            "succeeded": int(summary.get("succeeded") or len(tables)),
            "failed": int(summary.get("failed") or len(failed_tables)),
            "total": int(summary.get("total") or len(entities)),
        },
    }


def _sanitize_execution_name(*, prefix: str) -> str:
    slug = _EXECUTION_NAME_RE.sub("-", prefix.strip().lower() or "onboarding")
    suffix = uuid.uuid4().hex[:10]
    return f"{slug}-{suffix}"[:80]


def _resolve_region(record: ClientRecord, *, region: str | None = None) -> str:
    if region:
        return region
    env_config = get_environment_config(record.company, record.environment)
    _, deploy_region = resolve_aws_deploy_env(env_config, record.environment)
    return deploy_region


def _state_machine_arn(
    *,
    company: str,
    environment: str,
    connector: str,
    process_key: str,
    region: str,
    account_resolver: Callable[[], str] | None = None,
) -> str:
    name = step_function_name_for_process(company, environment, connector, process_key)
    if account_resolver is not None:
        account = account_resolver()
    else:
        import boto3

        account = boto3.client("sts").get_caller_identity()["Account"]
    return f"arn:aws:states:{region}:{account}:stateMachine:{name}"


def _stepfunctions_client(*, region: str):
    import boto3

    return boto3.client("stepfunctions", region_name=region)


def _s3_client(*, region: str):
    import boto3

    return boto3.client("s3", region_name=region)


def _describe_execution(
    execution_arn: str,
    *,
    region: str,
    describe_fn: Callable[[str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if not execution_arn.strip():
        return {}
    if describe_fn is not None:
        return describe_fn(execution_arn)
    client = _stepfunctions_client(region=region)
    return client.describe_execution(executionArn=execution_arn)


def _latest_execution(
    state_machine_arn: str,
    *,
    region: str,
    list_fn: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if not state_machine_arn.strip():
        return {}
    if list_fn is not None:
        payload = list_fn(stateMachineArn=state_machine_arn, maxResults=1)
    else:
        client = _stepfunctions_client(region=region)
        payload = client.list_executions(stateMachineArn=state_machine_arn, maxResults=1)
    executions = payload.get("executions")
    if not isinstance(executions, list) or not executions:
        return {}
    item = executions[0]
    if not isinstance(item, dict):
        return {}
    return item


def _execution_status_payload(
    *,
    execution_arn: str,
    region: str,
    describe_fn: Callable[[str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if not execution_arn.strip():
        return {
            "execution_arn": "",
            "status": "not_started",
            "started_at": "",
            "stopped_at": "",
            "error": "",
        }
    payload = _describe_execution(execution_arn, region=region, describe_fn=describe_fn)
    return {
        "execution_arn": execution_arn,
        "status": str(payload.get("status") or "unknown").strip().lower(),
        "started_at": str(payload.get("startDate") or ""),
        "stopped_at": str(payload.get("stopDate") or ""),
        "error": str(payload.get("error") or payload.get("cause") or ""),
    }


def _connector_pipeline_label(connector: str) -> str:
    labels = {
        "dbc": "Business Central",
        "qbo": "QuickBooks Online",
        "qbd": "QuickBooks Desktop",
    }
    return labels.get(connector.strip().lower(), connector)


def _ingest_kickoff_note(connector: str) -> str:
    if connector.strip().lower() == "qbd":
        return (
            "QBD ingest is driven by QuickBooks Web Connector. "
            "This run refreshes silver consolidation only."
        )
    return "Runs bronze ingest and silver consolidation for this connector."


def _load_manifest_from_s3(
    *,
    bucket: str,
    prefix: str,
    region: str,
    run_id: str | None = None,
    s3_get_json: Callable[[str, str], dict[str, Any] | None] | None = None,
) -> dict[str, Any] | None:
    normalized_prefix = prefix.strip().strip("/") + "/"
    if run_id:
        key = f"{normalized_prefix}{run_id.strip()}/manifest.json"
        if s3_get_json is not None:
            manifest = s3_get_json(bucket, key)
        else:
            from hiveflow.ingest.storage import read_json_s3

            manifest = read_json_s3(bucket, key)
        return manifest if isinstance(manifest, dict) else None

    if s3_get_json is not None:
        latest_key = ""
        return s3_get_json(bucket, latest_key) if latest_key else None

    client = _s3_client(region=region)
    manifest_candidates: list[tuple[str, datetime]] = []
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=normalized_prefix):
        for item in page.get("Contents", []):
            if not isinstance(item, dict):
                continue
            key = str(item.get("Key") or "")
            if not key.endswith("/manifest.json"):
                continue
            modified = item.get("LastModified")
            if isinstance(modified, datetime):
                manifest_candidates.append((key, modified))
    if not manifest_candidates:
        return None
    manifest_candidates.sort(key=lambda pair: pair[1], reverse=True)
    latest_key = manifest_candidates[0][0]
    from hiveflow.ingest.storage import read_json_s3

    manifest = read_json_s3(bucket, latest_key)
    return manifest if isinstance(manifest, dict) else None


def ingest_validation_report(
    record: ClientRecord,
    *,
    connector: str,
    run_id: str | None = None,
    region: str | None = None,
    s3_get_json: Callable[[str, str], dict[str, Any] | None] | None = None,
) -> dict[str, Any]:
    connector_key = connector.strip().lower()
    deploy_region = _resolve_region(record, region=region)
    env_config = get_environment_config(record.company, record.environment)
    account, _ = resolve_aws_deploy_env(env_config, record.environment)
    bucket = resolve_data_bucket_name(
        record.company,
        record.environment,
        account=account,
        region=deploy_region,
    )
    prefix = resolve_ingest_s3_prefix(
        record.company,
        record.environment,
        source=connector_key,
    )
    manifest = _load_manifest_from_s3(
        bucket=bucket,
        prefix=prefix,
        region=deploy_region,
        run_id=run_id,
        s3_get_json=s3_get_json,
    )
    if manifest is None:
        return {
            "ok": False,
            "connector": connector_key,
            "message": "No ingest manifest found for this connector yet.",
        }
    report = build_ingest_validation_report(manifest)
    report.update(
        {
            "ok": True,
            "connector": connector_key,
            "connector_label": _connector_pipeline_label(connector_key),
            "bucket": bucket,
            "prefix": prefix,
            "run_id": run_id or "",
        }
    )
    return report


def trigger_ingest_refresh(
    record: ClientRecord,
    *,
    connector: str,
    region: str | None = None,
    full_load: bool = True,
    start_fn: Callable[..., dict[str, Any]] | None = None,
    describe_fn: Callable[[str], dict[str, Any]] | None = None,
    list_fn: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    connector_key = connector.strip().lower()
    if connector_key not in record.connector_sources:
        return {"ok": False, "message": f"Connector {connector_key!r} is not configured for this client."}

    deploy_region = _resolve_region(record, region=region)
    state_machine_arn = _state_machine_arn(
        company=record.company,
        environment=record.environment,
        connector=connector_key,
        process_key=Process.REFRESH,
        region=deploy_region,
    )
    latest = _latest_execution(state_machine_arn, region=deploy_region, list_fn=list_fn)
    latest_arn = str(latest.get("executionArn") or "")
    if latest_arn:
        latest_status = _execution_status_payload(
            execution_arn=latest_arn,
            region=deploy_region,
            describe_fn=describe_fn,
        )
        if latest_status["status"] in _ACTIVE_EXECUTION_STATUSES:
            return {
                "ok": False,
                "status": "in_progress",
                "connector": connector_key,
                "execution_arn": latest_arn,
                "message": "An ingest refresh is already running for this connector.",
            }

    payload = {
        "full_load": bool(full_load),
        "full_rebuild": False,
        "trigger": "admin_onboarding",
        "client_id": record.client_id,
    }
    execution_name = _sanitize_execution_name(prefix=f"onboard-ingest-{connector_key}")
    if start_fn is not None:
        response = start_fn(
            stateMachineArn=state_machine_arn,
            name=execution_name,
            input=json.dumps(payload),
        )
    else:
        client = _stepfunctions_client(region=deploy_region)
        response = client.start_execution(
            stateMachineArn=state_machine_arn,
            name=execution_name,
            input=json.dumps(payload),
        )
    execution_arn = str(response.get("executionArn") or "")
    if not execution_arn:
        return {"ok": False, "message": "Ingest refresh did not return an execution ARN."}
    return {
        "ok": True,
        "connector": connector_key,
        "execution_arn": execution_arn,
        "state_machine_arn": state_machine_arn,
        "message": f"Started ingest refresh for {_connector_pipeline_label(connector_key)}.",
        "note": _ingest_kickoff_note(connector_key),
    }


def trigger_dna_refresh(
    record: ClientRecord,
    *,
    region: str | None = None,
    username: str = "admin",
    start_fn: Callable[..., dict[str, Any]] | None = None,
    describe_fn: Callable[[str], dict[str, Any]] | None = None,
    list_fn: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if not record.dna_enabled:
        return {"ok": False, "message": "DNA is not enabled for this client."}

    deploy_region = _resolve_region(record, region=region)
    state_machine_arn = _state_machine_arn(
        company=record.company,
        environment=record.environment,
        connector="all",
        process_key=Process.DNA_REFRESH,
        region=deploy_region,
    )
    latest = _latest_execution(state_machine_arn, region=deploy_region, list_fn=list_fn)
    latest_arn = str(latest.get("executionArn") or "")
    if latest_arn:
        latest_status = _execution_status_payload(
            execution_arn=latest_arn,
            region=deploy_region,
            describe_fn=describe_fn,
        )
        if latest_status["status"] in _ACTIVE_EXECUTION_STATUSES:
            return {
                "ok": False,
                "status": "in_progress",
                "execution_arn": latest_arn,
                "message": "A DNA refresh is already running.",
            }

    payload = {
        "trigger": "admin_onboarding",
        "client_id": record.client_id,
        "username": username,
    }
    execution_name = _sanitize_execution_name(prefix="onboard-dna")
    if start_fn is not None:
        response = start_fn(
            stateMachineArn=state_machine_arn,
            name=execution_name,
            input=json.dumps(payload),
        )
    else:
        client = _stepfunctions_client(region=deploy_region)
        response = client.start_execution(
            stateMachineArn=state_machine_arn,
            name=execution_name,
            input=json.dumps(payload),
        )
    execution_arn = str(response.get("executionArn") or "")
    if not execution_arn:
        return {"ok": False, "message": "DNA refresh did not return an execution ARN."}
    return {
        "ok": True,
        "execution_arn": execution_arn,
        "state_machine_arn": state_machine_arn,
        "message": "Started DNA refresh.",
    }


def client_pipeline_status(
    record: ClientRecord,
    *,
    region: str | None = None,
    tracked_executions: dict[str, str] | None = None,
    describe_fn: Callable[[str], dict[str, Any]] | None = None,
    list_fn: Callable[..., dict[str, Any]] | None = None,
    has_report_fn: Callable[[str], bool] | None = None,
) -> dict[str, Any]:
    deploy_region = _resolve_region(record, region=region)
    tracked = dict(tracked_executions or {})
    ingest: dict[str, Any] = {}

    for connector in record.connector_sources:
        connector_key = connector.strip().lower()
        state_machine_arn = _state_machine_arn(
            company=record.company,
            environment=record.environment,
            connector=connector_key,
            process_key=Process.REFRESH,
            region=deploy_region,
        )
        execution_arn = str(tracked.get(f"ingest:{connector_key}") or "")
        if not execution_arn:
            latest = _latest_execution(state_machine_arn, region=deploy_region, list_fn=list_fn)
            execution_arn = str(latest.get("executionArn") or "")
        status_payload = _execution_status_payload(
            execution_arn=execution_arn,
            region=deploy_region,
            describe_fn=describe_fn,
        )
        has_report = False
        if status_payload["status"] == "succeeded":
            if has_report_fn is not None:
                has_report = has_report_fn(connector_key)
            else:
                try:
                    report = ingest_validation_report(record, connector=connector_key, region=region)
                    has_report = bool(report.get("ok"))
                except ValueError:
                    has_report = False
        ingest[connector_key] = {
            "connector": connector_key,
            "label": _connector_pipeline_label(connector_key),
            "state_machine_arn": state_machine_arn,
            "note": _ingest_kickoff_note(connector_key),
            **status_payload,
            "has_report": has_report,
        }

    dna_payload: dict[str, Any] = {"enabled": record.dna_enabled}
    if record.dna_enabled:
        state_machine_arn = _state_machine_arn(
            company=record.company,
            environment=record.environment,
            connector="all",
            process_key=Process.DNA_REFRESH,
            region=deploy_region,
        )
        execution_arn = str(tracked.get("dna") or "")
        if not execution_arn:
            latest = _latest_execution(state_machine_arn, region=deploy_region, list_fn=list_fn)
            execution_arn = str(latest.get("executionArn") or "")
        status_payload = _execution_status_payload(
            execution_arn=execution_arn,
            region=deploy_region,
            describe_fn=describe_fn,
        )
        dna_payload.update(
            {
                "state_machine_arn": state_machine_arn,
                **status_payload,
            }
        )

    return {
        "company": record.company,
        "client_id": record.client_id,
        "environment": record.environment,
        "ingest": ingest,
        "dna": dna_payload,
        "checked_at": datetime.now(UTC).isoformat(),
    }
