from __future__ import annotations

from typing import Any

from meshflow.project_config import resolve_bc_ingest_entities, resolve_qbo_ingest_entities


def run_bronze_ingest_glue(*, run_id: str, full_load: bool) -> dict[str, Any]:
    """Run a full bronze ingest for the connector configured via ``MESHFLOW_SOURCE``."""
    import os

    connector = str(os.environ.get("MESHFLOW_SOURCE", "")).strip().lower()
    if connector == "dbc":
        return _run_bc_ingest(run_id=run_id, full_load=full_load)
    if connector == "qbo":
        return _run_qbo_ingest(run_id=run_id, full_load=full_load)
    raise ValueError(f"Glue bronze ingest does not support connector {connector!r}")


def _run_bc_ingest(*, run_id: str, full_load: bool) -> dict[str, Any]:
    from meshflow.bc.client import BCClient
    from meshflow.bc.ingest import ingest_all
    from meshflow.config import load_bc_settings

    settings = load_bc_settings()
    if not settings.s3_bucket:
        raise ValueError("MESHFLOW_S3_BUCKET must be set for Glue bronze ingest")

    entity_bundle, specs = resolve_bc_ingest_entities()
    client = BCClient.from_settings(settings)
    return ingest_all(
        client,
        settings,
        specs=specs,
        entity_bundle=entity_bundle,
        incremental=not full_load,
        run_id=run_id,
    )


def _run_qbo_ingest(*, run_id: str, full_load: bool) -> dict[str, Any]:
    from meshflow.config import load_qbo_settings
    from meshflow.qbo.client import QBOClient
    from meshflow.qbo.ingest import ingest_all

    settings = load_qbo_settings()
    if not settings.s3_bucket:
        raise ValueError("MESHFLOW_S3_BUCKET must be set for Glue bronze ingest")

    entity_bundle, entities = resolve_qbo_ingest_entities()
    client = QBOClient.from_saved_tokens(settings)
    return ingest_all(
        client,
        settings,
        entities=entities,
        entity_bundle=entity_bundle,
        run_id=run_id,
    )
