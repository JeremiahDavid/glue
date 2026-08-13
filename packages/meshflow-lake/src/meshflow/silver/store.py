from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from meshflow.storage.parquet import read_parquet_local, read_parquet_s3
from meshflow.silver.column_names import normalize_silver_rows
from meshflow.silver.settings import ConsolidateSettings
from meshflow.storage.paths import (
    legacy_raw_entity_parquet_key,
    legacy_silver_entity_parquet_key,
    prefix_path,
    raw_entity_parquet_key,
    silver_entity_parquet_key,
    silver_entity_prefix,
)

RUN_STAMP_PATTERN = re.compile(r"^\d{8}T\d{6}Z$")
RAW_RESERVED_PREFIXES = frozenset({"_state"})


def list_bronze_runs(settings: ConsolidateSettings) -> list[str]:
    if settings.s3_bucket:
        return _list_bronze_runs_s3(settings)
    return _list_bronze_runs_local(settings)


def _list_bronze_runs_local(settings: ConsolidateSettings) -> list[str]:
    root = prefix_path(settings.data_dir, settings.bronze_prefix)
    if not root.is_dir():
        return []
    runs = [
        path.name
        for path in root.iterdir()
        if path.is_dir() and path.name not in RAW_RESERVED_PREFIXES and RUN_STAMP_PATTERN.match(path.name)
    ]
    return sorted(runs)


def _list_bronze_runs_s3(settings: ConsolidateSettings) -> list[str]:
    import boto3

    prefix = settings.bronze_prefix.strip("/") + "/"
    client = boto3.client("s3")
    paginator = client.get_paginator("list_objects_v2")
    runs: set[str] = set()
    for page in paginator.paginate(Bucket=settings.s3_bucket, Prefix=prefix, Delimiter="/"):
        for entry in page.get("CommonPrefixes", []):
            folder = str(entry.get("Prefix", "")).removeprefix(prefix).strip("/")
            if folder and folder not in RAW_RESERVED_PREFIXES and RUN_STAMP_PATTERN.match(folder):
                runs.add(folder)
    return sorted(runs)


def read_run_manifest(settings: ConsolidateSettings, run_id: str) -> dict[str, Any] | None:
    if settings.s3_bucket:
        return _read_json_s3(settings, f"{settings.bronze_prefix}/{run_id}/manifest.json")
    path = prefix_path(settings.data_dir, settings.bronze_prefix, run_id, "manifest.json")
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def read_entity_rows(settings: ConsolidateSettings, run_id: str, entity_name: str) -> list[dict[str, Any]]:
    if settings.s3_bucket:
        for key in (
            raw_entity_parquet_key(settings.source, run_id, entity_name),
            legacy_raw_entity_parquet_key(settings.source, run_id, entity_name),
        ):
            try:
                return read_parquet_s3(settings.s3_bucket, key)
            except FileNotFoundError:
                continue
        return []
    for path in (
        prefix_path(
            settings.data_dir,
            settings.bronze_prefix,
            run_id,
            entity_name,
            "data.parquet",
        ),
        prefix_path(settings.data_dir, settings.bronze_prefix, run_id, f"{entity_name}.parquet"),
    ):
        rows = read_parquet_local(path)
        if rows:
            return rows
    return []


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
        return _write_json_s3(settings, f"{settings.silver_prefix}/_state/state.json", payload)
    out_dir = prefix_path(settings.data_dir, settings.silver_prefix, "_state")
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "state.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return str(path)


def write_consolidated_manifest(settings: ConsolidateSettings, manifest: dict[str, Any]) -> str:
    if settings.s3_bucket:
        return _write_json_s3(settings, f"{settings.silver_prefix}/manifest.json", manifest)
    out_dir = prefix_path(settings.data_dir, settings.silver_prefix)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return str(path)


def write_consolidated_entity(
    settings: ConsolidateSettings,
    entity_name: str,
    rows: list[dict[str, Any]],
) -> str:
    from meshflow.storage.parquet import write_parquet_local, write_parquet_s3

    rows = normalize_silver_rows(rows)

    if settings.s3_bucket:
        key = silver_entity_parquet_key(settings.source, entity_name)
        return write_parquet_s3(settings, key, rows)
    out_dir = prefix_path(settings.data_dir, silver_entity_prefix(settings.source, entity_name))
    return write_parquet_local(out_dir, "data.parquet", rows)


def read_consolidated_entity(settings: ConsolidateSettings, entity_name: str) -> list[dict[str, Any]]:
    if settings.s3_bucket:
        for key in (
            silver_entity_parquet_key(settings.source, entity_name),
            legacy_silver_entity_parquet_key(settings.source, entity_name),
        ):
            try:
                return read_parquet_s3(settings.s3_bucket, key)
            except FileNotFoundError:
                continue
        return []
    for relative in (
        prefix_path(settings.data_dir, silver_entity_prefix(settings.source, entity_name), "data.parquet"),
        prefix_path(settings.data_dir, settings.silver_prefix, f"{entity_name}.parquet"),
    ):
        rows = read_parquet_local(relative)
        if rows:
            return rows
    return []


def _read_state_payload(settings: ConsolidateSettings) -> dict[str, Any] | None:
    if settings.s3_bucket:
        return _read_json_s3(settings, f"{settings.silver_prefix}/_state/state.json")
    path = prefix_path(settings.data_dir, settings.silver_prefix, "_state", "state.json")
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
