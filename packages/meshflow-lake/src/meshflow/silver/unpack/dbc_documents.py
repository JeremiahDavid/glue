from __future__ import annotations

import json
from typing import Any

from meshflow.silver.unpack.qbd_invoices import parse_json_value

# Header entity → (OData $expand property, silver line table name)
DBC_DOCUMENT_ENTITIES: dict[str, tuple[str, str]] = {
    "sales_quotes": ("salesQuoteLines", "sales_quote_lines"),
    "sales_orders": ("salesOrderLines", "sales_order_lines"),
    "sales_shipments": ("salesShipmentLines", "sales_shipment_lines"),
    "sales_invoices": ("salesInvoiceLines", "sales_invoice_lines"),
    "open_sales_invoices": ("salesInvoiceLines", "sales_invoice_lines"),
    "sales_credit_memos": ("salesCreditMemoLines", "sales_credit_memo_lines"),
    "purchase_orders": ("purchaseOrderLines", "purchase_order_lines"),
    "purchase_receipts": ("purchaseReceiptLines", "purchase_receipt_lines"),
    "purchase_invoices": ("purchaseInvoiceLines", "purchase_invoice_lines"),
    "purchase_credit_memos": ("purchaseCreditMemoLines", "purchase_credit_memo_lines"),
}

DBC_LINE_ENTITY_NAMES: frozenset[str] = frozenset(
    line_entity for _, line_entity in DBC_DOCUMENT_ENTITIES.values()
)


def line_entity_for_header(header_entity: str) -> str | None:
    spec = DBC_DOCUMENT_ENTITIES.get(header_entity)
    if spec is None:
        return None
    return spec[1]


def _coerce_line_items(value: Any) -> list[dict[str, Any]]:
    parsed = parse_json_value(value)
    if parsed in (None, ""):
        return []
    if isinstance(parsed, dict):
        return [parsed]
    if isinstance(parsed, list):
        return [item for item in parsed if isinstance(item, dict)]
    return []


def _normalize_scalar(value: Any) -> Any:
    parsed = parse_json_value(value)
    if isinstance(parsed, (dict, list)):
        return json.dumps(parsed, default=str)
    return parsed


def unpack_dbc_document_header(row: dict[str, Any], *, line_array_key: str) -> dict[str, Any]:
    header: dict[str, Any] = {}
    for key, value in row.items():
        if key == line_array_key:
            continue
        header[key] = _normalize_scalar(value)
    return header


def unpack_dbc_document_line(
    *,
    header_id: str | None,
    header_number: str | None,
    line: dict[str, Any],
) -> dict[str, Any]:
    unpacked: dict[str, Any] = {}
    for key, value in line.items():
        unpacked[key] = _normalize_scalar(value)

    if header_id not in (None, ""):
        unpacked.setdefault("documentId", header_id)
        unpacked["header_id"] = header_id
    if header_number not in (None, ""):
        unpacked.setdefault("documentNumber", header_number)
        unpacked["header_number"] = header_number
    return unpacked


def unpack_dbc_document_lines(
    row: dict[str, Any],
    *,
    line_array_key: str,
) -> list[dict[str, Any]]:
    header_id = row.get("id")
    header_number = row.get("number")
    if header_id in (None, ""):
        return []

    lines: list[dict[str, Any]] = []
    for line in _coerce_line_items(row.get(line_array_key)):
        lines.append(
            unpack_dbc_document_line(
                header_id=str(header_id),
                header_number=str(header_number) if header_number not in (None, "") else None,
                line=line,
            )
        )
    return lines


def unpack_dbc_document_entity(
    header_entity: str,
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    """Split consolidated BC document rows into header and line tables."""
    spec = DBC_DOCUMENT_ENTITIES.get(header_entity)
    if spec is None:
        raise ValueError(f"Unknown DBC document entity: {header_entity}")

    line_array_key, line_entity = spec
    headers: list[dict[str, Any]] = []
    lines: list[dict[str, Any]] = []
    for row in rows:
        headers.append(unpack_dbc_document_header(row, line_array_key=line_array_key))
        lines.extend(unpack_dbc_document_lines(row, line_array_key=line_array_key))
    return headers, lines, line_entity
