from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from meshflow.ingest.storage import (
    local_run_dir,
    resolve_run_path,
    run_stamp,
    write_json_local,
    write_json_s3,
)


def prepare_ingest_run(*, full_load: bool = False) -> dict[str, Any]:
    """Build shared run metadata for a fan-out ingest execution."""
    from meshflow.project_config import (
        get_connector_config,
        get_environment_config,
        resolve_fanout_entity_names,
        resolve_ingest_connector,
        resolve_selection,
    )

    company, environment = resolve_selection()
    connector = resolve_ingest_connector()
    env_config = get_environment_config(company, environment)
    connector_cfg = get_connector_config(env_config, connector)
    if not connector_cfg:
        ingest_cfg = env_config.get("ingest", {})
        connector_cfg = ingest_cfg if isinstance(ingest_cfg, dict) else {}

    entities = resolve_fanout_entity_names(connector, connector_cfg)
    if not entities:
        raise ValueError(f"No ingest entities configured for connector {connector!r}")

    if connector == "qbo":
        from meshflow.config import load_qbo_settings
        from meshflow.qbo.oauth import ensure_access_token

        ensure_access_token(load_qbo_settings())

    return {
        "run_id": run_stamp(),
        "entities": entities,
        "full_load": full_load,
        "connector": connector,
        "company": company,
        "environment": environment,
    }


def finalize_ingest_run(
    *,
    run_id: str,
    entity_results: list[dict[str, Any]],
    full_load: bool = False,
) -> dict[str, Any]:
    """Write manifest.json and sync catalog after parallel entity ingests."""
    connector = resolve_ingest_connector_from_results(entity_results)
    if connector == "qbo":
        return _finalize_qbo_run(run_id=run_id, entity_results=entity_results)
    if connector == "dbc":
        return _finalize_bc_run(
            run_id=run_id,
            entity_results=entity_results,
            full_load=full_load,
        )
    raise ValueError(f"Unsupported connector for ingest finalize: {connector!r}")


def finalize_ingest_from_manifest(*, run_id: str) -> dict[str, Any]:
    """Load manifest.json written by a Glue bronze ingest job."""
    from meshflow.ingest.storage import read_json_s3, resolve_run_path
    from meshflow.project_config import resolve_ingest_connector

    connector = resolve_ingest_connector()
    if connector == "qbo":
        from meshflow.config import load_qbo_settings

        settings = load_qbo_settings()
    elif connector == "dbc":
        from meshflow.config import load_bc_settings

        settings = load_bc_settings()
    else:
        raise ValueError(f"Unsupported connector for manifest finalize: {connector!r}")

    if not settings.s3_bucket:
        raise ValueError("MESHFLOW_S3_BUCKET must be set for ingest manifest finalize")

    run_path = resolve_run_path(settings, run_id)
    manifest = read_json_s3(settings.s3_bucket, f"{run_path}/manifest.json")
    if manifest is None:
        raise FileNotFoundError(
            f"Bronze manifest not found at s3://{settings.s3_bucket}/{run_path}/manifest.json"
        )
    return manifest


def resolve_ingest_connector_from_results(entity_results: list[dict[str, Any]]) -> str:
    from meshflow.project_config import resolve_ingest_connector

    for item in entity_results:
        connector = str(item.get("connector", "")).strip().lower()
        if connector:
            return connector
    return resolve_ingest_connector()


def _unwrap_entity_results(entity_results: list[Any]) -> list[dict[str, Any]]:
    unwrapped: list[dict[str, Any]] = []
    for item in entity_results:
        if not isinstance(item, dict):
            continue
        payload = item.get("Payload", item)
        if isinstance(payload, dict):
            unwrapped.append(payload)
    return unwrapped


def _collect_entity_rows(entity_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for payload in entity_results:
        if payload.get("status") == "failed":
            rows.append(
                {
                    "entity": payload.get("entity"),
                    "status": "failed",
                    "error": payload.get("error"),
                    "http_status": payload.get("http_status"),
                }
            )
            continue

        result = payload.get("result")
        if isinstance(result, dict):
            if result.get("status") == "failed":
                rows.append(result)
            else:
                rows.append(result)
    return rows


def _finalize_qbo_run(*, run_id: str, entity_results: list[dict[str, Any]]) -> dict[str, Any]:
    from meshflow.config import load_qbo_settings
    from meshflow.project_config import resolve_ingest_s3_prefix, resolve_qbo_ingest_entities, resolve_selection
    from meshflow.qbo.client import QBOClient

    settings = load_qbo_settings()
    if not settings.s3_bucket:
        raise ValueError("MESHFLOW_S3_BUCKET must be set for Lambda ingest finalize")

    entity_bundle, _entities = resolve_qbo_ingest_entities()
    unwrapped = _unwrap_entity_results(entity_results)
    results = _collect_entity_rows(unwrapped)
    client = QBOClient.from_saved_tokens(settings)
    company = client.company_info()
    run_path = resolve_run_path(settings, run_id)

    manifest = {
        "source": "qbo",
        "entity_bundle": entity_bundle,
        "run_id": run_id,
        "realm_id": client.tokens.realm_id,
        "company_name": company.get("CompanyName"),
        "environment": settings.environment,
        "ingested_at": datetime.now(UTC).isoformat(),
        "entities": results,
        "ingest_summary": _ingest_summary(results),
    }
    manifest_path = write_json_s3(settings, f"{run_path}/manifest.json", manifest)
    manifest["manifest_path"] = manifest_path

    company_name, meshflow_environment = resolve_selection()
    entity_names = [
        str(item.get("entity", "")).strip()
        for item in results
        if item.get("entity") and item.get("status") != "failed"
    ]
    manifest["glue_catalog"] = {"raw": _sync_raw_catalog(settings, "qbo", company_name, meshflow_environment, entity_names)}
    return manifest


def _finalize_bc_run(
    *,
    run_id: str,
    entity_results: list[dict[str, Any]],
    full_load: bool,
) -> dict[str, Any]:
    from meshflow.bc.client import BCClient
    from meshflow.bc.entities import DEFAULT_ENTITY_BUNDLE
    from meshflow.bc.ingest import _connector_source
    from meshflow.bc.token_store import load_watermarks, save_watermarks
    from meshflow.config import load_bc_settings
    from meshflow.project_config import resolve_bc_ingest_entities, resolve_ingest_s3_prefix, resolve_selection

    settings = load_bc_settings()
    if not settings.s3_bucket:
        raise ValueError("MESHFLOW_S3_BUCKET must be set for Lambda ingest finalize")

    entity_bundle, _specs = resolve_bc_ingest_entities()
    unwrapped = _unwrap_entity_results(entity_results)
    results = _collect_entity_rows(unwrapped)
    client = BCClient.from_settings(settings)
    company = client.company()
    source = _connector_source(settings)
    run_path = resolve_run_path(settings, run_id)

    if not full_load:
        watermarks = load_watermarks(settings)
        for item in results:
            if item.get("status") == "failed":
                continue
            entity_name = str(item.get("entity", "")).strip()
            watermark_to = item.get("watermark_to")
            if entity_name and watermark_to:
                watermarks[entity_name] = str(watermark_to)
        save_watermarks(settings, watermarks)

    manifest = {
        "source": source,
        "entity_bundle": entity_bundle or DEFAULT_ENTITY_BUNDLE,
        "run_id": run_id,
        "company_id": settings.company_id,
        "company_name": company.get("displayName") or company.get("name"),
        "bc_environment": settings.environment_name,
        "environment": settings.environment,
        "ingested_at": datetime.now(UTC).isoformat(),
        "entities": results,
        "ingest_summary": _ingest_summary(results),
    }
    manifest_path = write_json_s3(settings, f"{run_path}/manifest.json", manifest)
    manifest["manifest_path"] = manifest_path

    company_name, meshflow_environment = resolve_selection()
    entity_names = [
        str(item.get("entity", "")).strip()
        for item in results
        if item.get("entity") and item.get("status") != "failed"
    ]
    manifest["glue_catalog"] = {
        "raw": _sync_raw_catalog(settings, source, company_name, meshflow_environment, entity_names)
    }
    return manifest


def _ingest_summary(results: list[dict[str, Any]]) -> dict[str, int]:
    failed = sum(1 for item in results if item.get("status") == "failed")
    return {
        "succeeded": len(results) - failed,
        "failed": failed,
        "total": len(results),
    }


def _sync_raw_catalog(
    settings: Any,
    source: str,
    company: str,
    environment: str,
    entity_names: list[str],
) -> dict[str, Any]:
    from meshflow.catalog.glue_schema import sync_raw_tables_for_entities
    from meshflow.project_config import resolve_ingest_s3_prefix
    from meshflow.silver.settings import ConsolidateSettings

    catalog_settings = ConsolidateSettings(
        source=source,
        data_dir=settings.data_dir,
        s3_bucket=settings.s3_bucket,
        raw_prefix=resolve_ingest_s3_prefix(company, environment, source=source),
    )
    return sync_raw_tables_for_entities(catalog_settings, entity_names)


def write_local_manifest(settings: Any, run_id: str, manifest: dict[str, Any]) -> str:
    run_path = resolve_run_path(settings, run_id)
    if settings.s3_bucket:
        return write_json_s3(settings, f"{run_path}/manifest.json", manifest)
    return write_json_local(Path(run_path), "manifest.json", manifest)
