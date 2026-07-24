from __future__ import annotations

from pathlib import Path

DATA_LAYERS = ("raw", "silver", "gold")


def layer_source_prefix(layer: str, source: str) -> str:
    """Build `{layer}/{source}` prefix inside the company data bucket."""
    layer_slug = layer.strip().strip("/").lower()
    source_slug = source.strip().strip("/").lower()
    if layer_slug not in DATA_LAYERS:
        raise ValueError(f"Unknown data layer {layer!r}. Expected one of: {', '.join(DATA_LAYERS)}")
    if not source_slug:
        raise ValueError("source is required for source-scoped layers")
    return f"{layer_slug}/{source_slug}"


def raw_source_prefix(source: str) -> str:
    return layer_source_prefix("raw", source)


def silver_source_prefix(source: str) -> str:
    return layer_source_prefix("silver", source)


def gold_prefix() -> str:
    return "gold"


SILVER_ENTITY_FILENAME = "data.parquet"


def silver_entity_prefix(source: str, entity: str) -> str:
    return f"{silver_source_prefix(source)}/{entity.strip().lower()}"


def silver_entity_parquet_key(source: str, entity: str) -> str:
    return f"{silver_entity_prefix(source, entity)}/{SILVER_ENTITY_FILENAME}"


def legacy_silver_entity_parquet_key(source: str, entity: str) -> str:
    return f"{silver_source_prefix(source)}/{entity.strip().lower()}.parquet"


def raw_entity_run_prefix(source: str, run_id: str, entity: str) -> str:
    return f"{raw_source_prefix(source)}/{run_id.strip()}/{entity.strip().lower()}"


def raw_entity_parquet_key(source: str, run_id: str, entity: str) -> str:
    return f"{raw_entity_run_prefix(source, run_id, entity)}/{SILVER_ENTITY_FILENAME}"


def legacy_raw_entity_parquet_key(source: str, run_id: str, entity: str) -> str:
    return f"{raw_source_prefix(source)}/{run_id.strip()}/{entity.strip().lower()}.parquet"


def prefix_path(data_dir: Path, prefix: str, *parts: str) -> Path:
    segments = [segment for segment in prefix.strip("/").split("/") if segment]
    return data_dir.joinpath(*segments, *parts)
