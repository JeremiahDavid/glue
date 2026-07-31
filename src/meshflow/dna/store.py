from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from meshflow.dna.settings import DnaSettings
from meshflow.storage.paths import prefix_path


def read_silver_entity(settings: DnaSettings, entity_name: str) -> list[dict[str, Any]]:
    if settings.s3_bucket:
        from meshflow.ingest.storage import read_parquet_s3
        from meshflow.storage.paths import silver_entity_parquet_key

        key = silver_entity_parquet_key(settings.source, entity_name)
        try:
            return read_parquet_s3(settings.s3_bucket, key)
        except FileNotFoundError:
            return []
    from meshflow.ingest.storage import read_parquet_local
    from meshflow.storage.paths import silver_entity_prefix

    path = prefix_path(settings.data_dir, silver_entity_prefix(settings.source, entity_name), "data.parquet")
    return read_parquet_local(path)


def write_staging_output(
    settings: DnaSettings,
    output_id: str,
    rows: list[dict[str, Any]],
) -> str:
    from meshflow.ingest.storage import write_parquet_local, write_parquet_s3

    if settings.s3_bucket:
        key = f"{settings.gold_dna_staging_prefix}/{output_id}/data.parquet"
        return write_parquet_s3(settings, key, rows)

    out_dir = prefix_path(settings.data_dir, settings.gold_dna_staging_prefix, output_id)
    return write_parquet_local(out_dir, "data.parquet", rows)


def read_staging_output(settings: DnaSettings, output_id: str) -> list[dict[str, Any]]:
    if settings.s3_bucket:
        from meshflow.ingest.storage import read_parquet_s3

        key = f"{settings.gold_dna_staging_prefix}/{output_id}/data.parquet"
        try:
            return read_parquet_s3(settings.s3_bucket, key)
        except FileNotFoundError:
            return []
    from meshflow.ingest.storage import read_parquet_local

    path = prefix_path(settings.data_dir, settings.gold_dna_staging_prefix, output_id, "data.parquet")
    return read_parquet_local(path)


def write_production_output(
    settings: DnaSettings,
    output_id: str,
    rows: list[dict[str, Any]],
) -> str:
    from meshflow.ingest.storage import write_parquet_local, write_parquet_s3

    if settings.s3_bucket:
        key = f"{settings.gold_dna_prefix}/{output_id}/data.parquet"
        return write_parquet_s3(settings, key, rows)

    out_dir = prefix_path(settings.data_dir, settings.gold_dna_prefix, output_id)
    return write_parquet_local(out_dir, "data.parquet", rows)


def read_production_output(settings: DnaSettings, output_id: str) -> list[dict[str, Any]]:
    if settings.s3_bucket:
        from meshflow.ingest.storage import read_parquet_s3

        key = f"{settings.gold_dna_prefix}/{output_id}/data.parquet"
        try:
            return read_parquet_s3(settings.s3_bucket, key)
        except FileNotFoundError:
            return []
    from meshflow.ingest.storage import read_parquet_local

    path = prefix_path(settings.data_dir, settings.gold_dna_prefix, output_id, "data.parquet")
    return read_parquet_local(path)


def write_json_artifact(settings: DnaSettings, relative_key: str, payload: dict[str, Any]) -> str:
    if settings.s3_bucket:
        import boto3

        body = json.dumps(payload, indent=2).encode("utf-8")
        boto3.client("s3").put_object(
            Bucket=settings.s3_bucket,
            Key=relative_key,
            Body=body,
            ContentType="application/json",
        )
        return f"s3://{settings.s3_bucket}/{relative_key}"

    path = prefix_path(settings.data_dir, relative_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return str(path)


def read_json_artifact(settings: DnaSettings, relative_key: str) -> dict[str, Any] | None:
    if settings.s3_bucket:
        import boto3
        from botocore.exceptions import ClientError

        client = boto3.client("s3")
        try:
            response = client.get_object(Bucket=settings.s3_bucket, Key=relative_key)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in {"NoSuchKey", "404"}:
                return None
            raise
        payload = json.loads(response["Body"].read().decode("utf-8"))
        return payload if isinstance(payload, dict) else None

    path = prefix_path(settings.data_dir, relative_key)
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def definition_pack_key(pack_id: str, version: str) -> str:
    return f"dna/definition_packs/v{version}/{pack_id}.yaml"


def load_pack_from_settings(settings: DnaSettings) -> Any:
    from meshflow.dna.schema import DefinitionPack, load_definition_pack_file, load_definition_pack_yaml, starter_pack_path

    if settings.pack_version:
        key = definition_pack_key(settings.pack_id, settings.pack_version)
        raw = read_json_artifact(settings, key.replace(".yaml", ".json"))
        if raw:
            from meshflow.dna.schema import load_definition_pack

            return load_definition_pack(raw)
        # Try yaml path via local mirror
        local_path = prefix_path(settings.data_dir, key)
        if local_path.is_file():
            return load_definition_pack_yaml(local_path.read_text(encoding="utf-8"))

    starter = starter_pack_path(settings.pack_id)
    if starter.is_file():
        return load_definition_pack_file(starter)
    raise FileNotFoundError(f"No definition pack found for {settings.pack_id!r}")
