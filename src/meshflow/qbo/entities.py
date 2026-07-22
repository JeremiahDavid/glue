from __future__ import annotations

from typing import Any

DEFAULT_ENTITY_BUNDLE = "v1_accounting"

# Active list entities return only active rows by default; include inactive explicitly.
_ACTIVE_ALL = " WHERE Active IN (true, false)"

ENTITY_BUNDLES: dict[str, dict[str, str]] = {
    "v1_accounting": {
        "customers": "SELECT * FROM Customer",
        "invoices": "SELECT * FROM Invoice",
        "open_invoices": "SELECT * FROM Invoice WHERE Balance > '0'",
        "payments": "SELECT * FROM Payment",
    },
    "full_accounting": {
        "customers": f"SELECT * FROM Customer{_ACTIVE_ALL}",
        "vendors": f"SELECT * FROM Vendor{_ACTIVE_ALL}",
        "items": f"SELECT * FROM Item{_ACTIVE_ALL}",
        "accounts": f"SELECT * FROM Account{_ACTIVE_ALL}",
        "classes": f"SELECT * FROM Class{_ACTIVE_ALL}",
        "departments": f"SELECT * FROM Department{_ACTIVE_ALL}",
        "invoices": "SELECT * FROM Invoice",
        "payments": "SELECT * FROM Payment",
        "bills": "SELECT * FROM Bill",
        "credit_memos": "SELECT * FROM CreditMemo",
        "deposits": "SELECT * FROM Deposit",
        "sales_receipts": "SELECT * FROM SalesReceipt",
        "estimates": "SELECT * FROM Estimate",
    },
}

# Backward-compatible alias used by tests and imports.
DEFAULT_ENTITIES = ENTITY_BUNDLES[DEFAULT_ENTITY_BUNDLE]


def list_entity_bundles() -> list[str]:
    return sorted(ENTITY_BUNDLES)


def resolve_qbo_entities_from_ingest_config(
    ingest_cfg: dict[str, Any],
) -> tuple[str, dict[str, str]]:
    """Resolve QBO entity queries from ingest config.

    Precedence:
    1. ``ingest.entities`` mapping (full override)
    2. ``ingest.entity_bundle`` named bundle (default: v1_accounting)
    """
    explicit = ingest_cfg.get("entities")
    if isinstance(explicit, dict) and explicit:
        entities = {str(name): str(query) for name, query in explicit.items()}
        if not entities:
            raise ValueError("ingest.entities must contain at least one entity query")
        return "custom", entities

    bundle = str(ingest_cfg.get("entity_bundle", DEFAULT_ENTITY_BUNDLE)).strip().lower()
    if bundle not in ENTITY_BUNDLES:
        available = ", ".join(list_entity_bundles())
        raise ValueError(f"Unknown ingest.entity_bundle {bundle!r}. Available bundles: {available}")

    return bundle, dict(ENTITY_BUNDLES[bundle])
