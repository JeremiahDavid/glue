from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from meshflow.ingest.storage import read_parquet_local, read_parquet_s3
from meshflow.silver.settings import ConsolidateSettings

RUN_STAMP_PATTERN = re.compile(r"^\d{8}T\d{6}Z$")
RESERVED_PREFIXES = frozenset({"_state", "_consolidated"})


def list_bronze_runs(settings: ConsolidateSettings) -> list[str]:
    if settings.s3_bucket:
        return _list_bronze_runs_s3(settings)
    return _list_bronze_runs_local(settings)


def _list_bronze_runs_local(settings: ConsolidateSettings) -> list[str]:
    root = settings.data_dir / "raw" / settings.s3_prefix
    if not root.is_dir():
        return []
    runs = [
        path.name
        for path in root.iterdir()
        if path.is_dir() and path.name not in RESERVED_PREFIXES and RUN_STAMP_PATTERN.match(path.name)
    ]
    return sorted(runs)


def _list_bronze_runs_s3(settings: ConsolidateSettings) -> list[str]:
    import boto3

    prefix = settings.s3_prefix.strip("/") + "/"
    client = boto3.client("s3")
    paginator = client.get_paginator("list_objects_v2")
    runs: set[str] = set()
    for page in paginator.paginate(Bucket=settings.s3_bucket, Prefix=prefix, Delimiter="/"):
        for entry in page.get("CommonPrefixes", []):
            folder = str(entry.get("Prefix", "")).removeprefix(prefix).strip("/")
            if folder and folder not in RESERVED_PREFIXES and RUN_STAMP_PATTERN.match(folder):
                runs.add(folder)
    return sorted(runs)


def read_run_manifest(settings: ConsolidateSettings, run_id: str) -> dict[str, Any] | None:
    if settings.s3_bucket:
        return _read_json_s3(settings, f"{settings.s3_prefix}/{run_id}/manifest.json")
    path = settings.data_dir / "raw" / settings.s3_prefix / run_id / "manifest.json"
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def read_entity_rows(settings: ConsolidateSettings, run_id: str, entity_name: str) -> list[dict[str, Any]]:
    if settings.s3_bucket:
        key = f"{settings.s3_prefix}/{run_id}/{entity_name}.parquet"
        return read_parquet_s3(settings.s3_bucket, key)
    path = settings.data_dir / "raw" / settings.s3_prefix / run_id / f"{entity_name}.parquet"
    return read_parquet_local(path)


def read_consolidation_state(settings: ConsolidateSettings) -> dict[str, Any]:
    payload = _read_state_payload(settings)
    if not payload:
        return {"processed_runs": []}
    processed = payload.get("processed_runs", [])
    if not isinstance(processed, list):
        processed = []
    return {"processed_runs": [str(item) for item in processed]}


def write_consolidation_state(settings: ConsolidateSettings, payload: dict[str, Any]) -> str:
    if settings.s3_bucket:
        return _write_json_s3(settings, f"{settings.consolidated_prefix}/state.json", payload)
    out_dir = settings.data_dir / "raw" / settings.consolidated_prefix
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "state.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return str(path)


def write_consolidated_manifest(settings: ConsolidateSettings, manifest: dict[str, Any]) -> str:
    if settings.s3_bucket:
        return _write_json_s3(settings, f"{settings.consolidated_prefix}/manifest.json", manifest)
    out_dir = settings.data_dir / "raw" / settings.consolidated_prefix
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return str(path)


def write_consolidated_entity(
    settings: ConsolidateSettings,
    entity_name: str,
    rows: list[dict[str, Any]],
) -> str:
    from meshflow.ingest.storage import write_parquet_local, write_parquet_s3

    if settings.s3_bucket:
        key = f"{settings.consolidated_prefix}/{entity_name}.parquet"
        return write_parquet_s3(settings, key, rows)
    out_dir = settings.data_dir / "raw" / settings.consolidated_prefix
    return write_parquet_local(out_dir, f"{entity_name}.parquet", rows)


def read_consolidated_entity(settings: ConsolidateSettings, entity_name: str) -> list[dict[str, Any]]:
    if settings.s3_bucket:
        key = f"{settings.consolidated_prefix}/{entity_name}.parquet"
        try:
            return read_parquet_s3(settings.s3_bucket, key)
        except FileNotFoundError:
            return []
    path = settings.data_dir / "raw" / settings.consolidated_prefix / f"{entity_name}.parquet"
    return read_parquet_local(path)


def _read_state_payload(settings: ConsolidateSettings) -> dict[str, Any] | None:
    if settings.s3_bucket:
        return _read_json_s3(settings, f"{settings.consolidated_prefix}/state.json")
    path = settings.data_dir / "raw" / settings.consolidated_prefix / "state.json"
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_json_s3(settings: ConsolidateSettings, key: str) -> dict[str, Any] | None:
    import boto3
    from botocore.exceptions import ClientError

    client = boto3.client("s3")
    try:
        response = client.get_object(Bucket=settings.s3_bucket, Key=key)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in {"NoSuchKey", "404"}:
            return None
        raise
    payload = json.loads(response["Body"].read().decode("utf-8"))
    return payload if isinstance(payload, dict) else None


def _write_json_s3(settings: ConsolidateSettings, key: str, payload: dict[str, Any]) -> str:
    import boto3

    body = json.dumps(payload, indent=2).encode("utf-8")
    boto3.client("s3").put_object(
        Bucket=settings.s3_bucket,
        Key=key,
        Body=body,
        ContentType="application/json",
    )
    return f"s3://{settings.s3_bucket}/{key}"
