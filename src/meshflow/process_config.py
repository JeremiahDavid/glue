from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml

from meshflow.project_config import (
    PROJECT_ROOT,
    lambda_function_name,
    step_function_name,
)

ResourceType = Literal["lambda", "step_function"]

DEFAULT_PROCESS_CONFIG_PATH = PROJECT_ROOT / "process_config.yaml"


@dataclass(frozen=True)
class ProcessDefinition:
    key: str
    stage: str
    slug: str
    resource: ResourceType
    description: str
    connectors: tuple[str, ...]


class Process:
    """Stable process keys — must match process_config.yaml."""

    PREPARE = "prepare"
    INGEST = "ingest"
    FINALIZE = "finalize"
    FANOUT = "fanout"
    CONSOLIDATE = "consolidate"


def default_process_config_path() -> Path:
    configured = os.getenv("MESHFLOW_PROCESS_CONFIG_PATH", "").strip()
    if configured:
        return Path(configured)

    bundled = Path(__file__).resolve().parent.parent / "process_config.yaml"
    if bundled.exists():
        return bundled

    return DEFAULT_PROCESS_CONFIG_PATH


@lru_cache(maxsize=1)
def load_process_config(path: Path | None = None) -> dict[str, Any]:
    config_path = path or default_process_config_path()
    if not config_path.exists():
        raise FileNotFoundError(f"Process config not found: {config_path}")

    with config_path.open(encoding="utf-8") as handle:
        payload = yaml.safe_load(handle)

    if not isinstance(payload, dict):
        raise ValueError(f"{config_path} must contain a YAML mapping at the top level")
    return payload


def shared_connector_slug(path: Path | None = None) -> str:
    payload = load_process_config(path)
    naming = payload.get("naming", {})
    if not isinstance(naming, dict):
        return "all"
    slug = str(naming.get("connector_shared", "all")).strip().lower()
    return slug or "all"


def list_process_keys(path: Path | None = None) -> list[str]:
    payload = load_process_config(path)
    processes = payload.get("processes", {})
    if not isinstance(processes, dict):
        return []
    return sorted(str(key) for key in processes)


def get_process(process_key: str, *, path: Path | None = None) -> ProcessDefinition:
    payload = load_process_config(path)
    processes = payload.get("processes", {})
    if not isinstance(processes, dict):
        raise ValueError("process_config.yaml processes section must be a mapping")

    raw = processes.get(process_key)
    if not isinstance(raw, dict):
        available = ", ".join(list_process_keys(path))
        raise ValueError(f"Unknown process {process_key!r}. Available: {available}")

    stage = str(raw.get("stage", "")).strip().lower()
    slug = str(raw.get("slug", process_key)).strip().lower()
    resource = str(raw.get("resource", "")).strip().lower()
    description = str(raw.get("description", "")).strip()
    connectors_raw = raw.get("connectors", [])
    if not stage:
        raise ValueError(f"Process {process_key!r} is missing stage")
    if not slug:
        raise ValueError(f"Process {process_key!r} is missing slug")
    if resource not in {"lambda", "step_function"}:
        raise ValueError(
            f"Process {process_key!r} has invalid resource {resource!r} "
            "(expected lambda or step_function)"
        )
    if not isinstance(connectors_raw, list) or not connectors_raw:
        raise ValueError(f"Process {process_key!r} must declare at least one connector")

    connectors = tuple(str(item).strip().lower() for item in connectors_raw if str(item).strip())
    if not connectors:
        raise ValueError(f"Process {process_key!r} must declare at least one connector")

    return ProcessDefinition(
        key=process_key,
        stage=stage,
        slug=slug,
        resource=resource,  # type: ignore[arg-type]
        description=description,
        connectors=connectors,
    )


def resolve_process_connector(connector: str, process_key: str, *, path: Path | None = None) -> str:
    """Return connector slug used in resource names for a process."""
    process = get_process(process_key, path=path)
    normalized = connector.strip().lower()
    shared = shared_connector_slug(path)

    if shared in process.connectors:
        return shared
    if normalized in process.connectors:
        return normalized
    raise ValueError(
        f"Process {process_key!r} does not apply to connector {connector!r}. "
        f"Allowed connectors: {', '.join(process.connectors)}"
    )


def lambda_name_for_process(
    company: str,
    environment: str,
    connector: str,
    process_key: str,
    *,
    path: Path | None = None,
) -> str:
    process = get_process(process_key, path=path)
    if process.resource != "lambda":
        raise ValueError(f"Process {process_key!r} is not a Lambda resource ({process.resource})")
    resolved_connector = resolve_process_connector(connector, process_key, path=path)
    return lambda_function_name(company, environment, resolved_connector, process.stage, process.slug)


def step_function_name_for_process(
    company: str,
    environment: str,
    connector: str,
    process_key: str,
    *,
    path: Path | None = None,
) -> str:
    process = get_process(process_key, path=path)
    if process.resource != "step_function":
        raise ValueError(
            f"Process {process_key!r} is not a Step Functions resource ({process.resource})"
        )
    resolved_connector = resolve_process_connector(connector, process_key, path=path)
    return step_function_name(company, environment, resolved_connector, process.stage, process.slug)
