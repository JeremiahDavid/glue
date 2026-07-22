from __future__ import annotations

import io
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from meshflow.config import QBOSettings
from meshflow.qbo.client import QBOClient
from meshflow.qbo.entities import DEFAULT_ENTITIES, DEFAULT_ENTITY_BUNDLE


def _run_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _local_run_dir(settings: QBOSettings) -> Path:
    return settings.data_dir / "raw" / "qbo" / _run_stamp()


def _s3_run_prefix(settings: QBOSettings) -> str:
    prefix = settings.s3_prefix.strip("/")
    return f"{prefix}/{_run_stamp()}"


def _normalize_row_for_parquet(row: dict[str, Any]) -> dict[str, Any]:
    """Serialize nested API objects so PyArrow can write stable Parquet schemas."""
    normalized: dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, dict | list):
            normalized[key] = json.dumps(value, default=str)
        else:
            normalized[key] = value
    return normalized


def _rows_to_parquet_bytes(rows: list[dict[str, Any]]) -> bytes:
    import pyarrow as pa
    import pyarrow.parquet as pq

    normalized_rows = [_normalize_row_for_parquet(row) for row in rows]
    table = pa.Table.from_pylist(normalized_rows) if normalized_rows else pa.table({})
    buffer = io.BytesIO()
    pq.write_table(table, buffer, compression="snappy")
    return buffer.getvalue()


def _write_json_local(output_dir: Path, filename: str, payload: dict[str, Any]) -> str:
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / filename
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return str(out_path)


def _write_parquet_local(output_dir: Path, filename: str, rows: list[dict[str, Any]]) -> str:
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / filename
    out_path.write_bytes(_rows_to_parquet_bytes(rows))
    return str(out_path)


def _write_json_s3(settings: QBOSettings, key: str, payload: dict[str, Any]) -> str:
    import boto3

    body = json.dumps(payload, indent=2).encode("utf-8")
    boto3.client("s3").put_object(
        Bucket=settings.s3_bucket,
        Key=key,
        Body=body,
        ContentType="application/json",
    )
    return f"s3://{settings.s3_bucket}/{key}"


def _write_parquet_s3(settings: QBOSettings, key: str, rows: list[dict[str, Any]]) -> str:
    import boto3

    boto3.client("s3").put_object(
        Bucket=settings.s3_bucket,
        Key=key,
        Body=_rows_to_parquet_bytes(rows),
        ContentType="application/vnd.apache.parquet",
    )
    return f"s3://{settings.s3_bucket}/{key}"


def ingest_entity(
    client: QBOClient,
    *,
    entity_name: str,
    query: str,
    settings: QBOSettings,
    run_path: Path | str,
) -> dict[str, Any]:
    rows = client.query(query)
    ingested_at = datetime.now(UTC).isoformat()

    if settings.s3_bucket:
        key = f"{run_path}/{entity_name}.parquet"
        location = _write_parquet_s3(settings, key, rows)
    else:
        location = _write_parquet_local(Path(run_path), f"{entity_name}.parquet", rows)

    return {
        "entity": entity_name,
        "format": "parquet",
        "query": query,
        "row_count": len(rows),
        "ingested_at": ingested_at,
        "path": location,
    }


def ingest_single(
    client: QBOClient,
    settings: QBOSettings,
    entity_name: str,
    *,
    entities: dict[str, str] | None = None,
) -> dict[str, Any]:
    selected_entities = entities or DEFAULT_ENTITIES
    if entity_name not in selected_entities:
        raise ValueError(
            f"Unknown entity '{entity_name}'. Choose from: {', '.join(sorted(selected_entities))}"
        )

    run_path: Path | str
    if settings.s3_bucket:
        run_path = _s3_run_prefix(settings)
    else:
        run_path = _local_run_dir(settings)

    return ingest_entity(
        client,
        entity_name=entity_name,
        query=selected_entities[entity_name],
        settings=settings,
        run_path=run_path,
    )


def ingest_all(
    client: QBOClient,
    settings: QBOSettings,
    *,
    entities: dict[str, str] | None = None,
    entity_bundle: str | None = None,
) -> dict[str, Any]:
    selected_entities = entities or DEFAULT_ENTITIES
    if settings.s3_bucket:
        run_path = _s3_run_prefix(settings)
    else:
        run_path = _local_run_dir(settings)

    company = client.company_info()
    results = []
    for entity_name, query in selected_entities.items():
        results.append(
            ingest_entity(
                client,
                entity_name=entity_name,
                query=query,
                settings=settings,
                run_path=run_path,
            )
        )

    manifest = {
        "source": "qbo",
        "entity_bundle": entity_bundle or DEFAULT_ENTITY_BUNDLE,
        "realm_id": client.tokens.realm_id,
        "company_name": company.get("CompanyName"),
        "environment": settings.environment,
        "ingested_at": datetime.now(UTC).isoformat(),
        "entities": results,
    }

    if settings.s3_bucket:
        manifest_key = f"{run_path}/manifest.json"
        manifest_path = _write_json_s3(settings, manifest_key, manifest)
    else:
        manifest_path = _write_json_local(Path(run_path), "manifest.json", manifest)

    manifest["manifest_path"] = manifest_path
    return manifest
