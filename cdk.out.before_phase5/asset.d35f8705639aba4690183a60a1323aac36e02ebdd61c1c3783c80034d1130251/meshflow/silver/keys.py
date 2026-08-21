from __future__ import annotations

from typing import Any

# Output names map to candidate primary-key fields (QBD first, then QBO).
ENTITY_MERGE_KEYS: dict[str, tuple[str, ...]] = {
    "customers": ("id", "ListID", "Id"),
    "vendors": ("ListID", "Id"),
    "items": ("id", "ListID", "Id"),
    "accounts": ("ListID", "Id"),
    "classes": ("ListID", "Id"),
    "invoices": ("TxnID", "Id"),
    "open_invoices": ("TxnID", "Id"),
    "payments": ("TxnID", "Id"),
    "bills": ("TxnID", "Id"),
    "credit_memos": ("TxnID", "Id"),
    "deposits": ("TxnID", "Id"),
    "sales_receipts": ("TxnID", "Id"),
    "estimates": ("TxnID", "Id"),
    "sales_orders": ("id",),
    "sales_shipments": ("id",),
    "sales_invoices": ("id",),
    "open_sales_invoices": ("id",),
    "customer_payments": ("id",),
}


def merge_keys_for_entity(entity_name: str) -> tuple[str, ...]:
    keys = ENTITY_MERGE_KEYS.get(entity_name)
    if keys is not None:
        return keys
    # BC OData entities use a GUID id; default keeps consolidate working for new entities.
    return ("id",)


def row_merge_key(row: dict[str, Any], entity_name: str) -> str | None:
    for key in merge_keys_for_entity(entity_name):
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return None
