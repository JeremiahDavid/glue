"""Connector-owned entity resolution registry (platform hub stays connector-free).

Connectors and lake unpack helpers register callbacks at import time via
``register_*`` so ``project_config`` can resolve catalog/fan-out entities without
importing ``meshflow.bc`` / ``meshflow.qbo`` / ``meshflow.qbd`` / ``meshflow.silver``.
"""

from __future__ import annotations

from typing import Any, Callable

CatalogEntitiesFn = Callable[[dict[str, Any]], list[str]]
FanoutEntitiesFn = Callable[[dict[str, Any]], list[str]]
BundleResolveFn = Callable[[dict[str, Any]], tuple[str, Any]]

_catalog_resolvers: dict[str, CatalogEntitiesFn] = {}
_fanout_resolvers: dict[str, FanoutEntitiesFn] = {}
_bundle_resolvers: dict[str, BundleResolveFn] = {}


def register_catalog_entities(connector: str, resolver: CatalogEntitiesFn) -> None:
    _catalog_resolvers[connector.strip().lower()] = resolver


def register_fanout_entities(connector: str, resolver: FanoutEntitiesFn) -> None:
    _fanout_resolvers[connector.strip().lower()] = resolver


def register_bundle_resolver(connector: str, resolver: BundleResolveFn) -> None:
    _bundle_resolvers[connector.strip().lower()] = resolver


def ensure_connectors_registered() -> None:
    """Import connector registration modules (idempotent)."""
    # Local imports keep platform importable without connectors installed.
    try:
        import meshflow.bc.entities  # noqa: F401
    except ImportError:
        pass
    try:
        import meshflow.qbo.entities  # noqa: F401
    except ImportError:
        pass
    try:
        import meshflow.qbd.entities  # noqa: F401
    except ImportError:
        pass


def catalog_entity_names(connector: str, connector_cfg: dict[str, Any]) -> list[str]:
    ensure_connectors_registered()
    key = connector.strip().lower()
    if key in {"dbc", "bc", "business_central"}:
        key = "dbc"
    resolver = _catalog_resolvers.get(key)
    if resolver is None:
        raise ValueError(f"No catalog entity resolver registered for connector {connector!r}")
    return resolver(connector_cfg)


def fanout_entity_names(connector: str, connector_cfg: dict[str, Any]) -> list[str]:
    ensure_connectors_registered()
    key = connector.strip().lower()
    if key in {"dbc", "bc", "business_central"}:
        key = "dbc"
    resolver = _fanout_resolvers.get(key)
    if resolver is None:
        raise ValueError(f"No fan-out entity resolver registered for connector {connector!r}")
    return resolver(connector_cfg)


def resolve_bundle(connector: str, connector_cfg: dict[str, Any]) -> tuple[str, Any]:
    ensure_connectors_registered()
    key = connector.strip().lower()
    if key in {"dbc", "bc", "business_central"}:
        key = "dbc"
    resolver = _bundle_resolvers.get(key)
    if resolver is None:
        raise ValueError(f"No bundle resolver registered for connector {connector!r}")
    return resolver(connector_cfg)
