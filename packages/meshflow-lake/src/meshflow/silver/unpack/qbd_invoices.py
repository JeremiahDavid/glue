from __future__ import annotations

import json
from typing import Any

INVOICE_LINE_ARRAY_KEYS = frozenset({"InvoiceLineRet"})

INVOICE_REF_FIELDS: dict[str, tuple[str, tuple[str, ...]]] = {
    "CustomerRef": ("customer", ("ListID", "FullName")),
    "ARAccountRef": ("ar_account", ("ListID", "FullName")),
    "ClassRef": ("class", ("ListID", "FullName")),
    "TermsRef": ("terms", ("ListID", "FullName")),
    "SalesRepRef": ("sales_rep", ("ListID", "FullName")),
    "TemplateRef": ("template", ("ListID", "FullName")),
    "CustomerMsgRef": ("customer_msg", ("ListID", "FullName")),
    "ShipMethodRef": ("ship_method", ("ListID", "FullName")),
    "ItemSalesTaxRef": ("item_sales_tax", ("ListID", "FullName")),
}

LINE_REF_FIELDS: dict[str, tuple[str, tuple[str, ...]]] = {
    "ItemRef": ("item", ("ListID", "FullName")),
    "ClassRef": ("class", ("ListID", "FullName")),
    "SalesTaxCodeRef": ("sales_tax_code", ("ListID", "FullName")),
}


def parse_json_value(value: Any) -> Any:
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            try:
                return json.loads(stripped)
            except json.JSONDecodeError:
                return value
    return value


def _flatten_ref(prefix: str, ref: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    flattened: dict[str, Any] = {}
    for field in fields:
        suffix = field.lower()
        if suffix == "listid":
            column = f"{prefix}_list_id"
        elif suffix == "fullname":
            column = f"{prefix}_full_name"
        else:
            column = f"{prefix}_{suffix}"
        flattened[column] = ref.get(field)
    return flattened


def _coerce_line_items(value: Any) -> list[dict[str, Any]]:
    parsed = parse_json_value(value)
    if parsed in (None, ""):
        return []
    if isinstance(parsed, dict):
        return [parsed]
    if isinstance(parsed, list):
        return [item for item in parsed if isinstance(item, dict)]
    return []


def unpack_qbd_invoice_header(row: dict[str, Any]) -> dict[str, Any]:
    header: dict[str, Any] = {}
    for key, value in row.items():
        if key in INVOICE_LINE_ARRAY_KEYS:
            continue

        parsed = parse_json_value(value)
        ref_spec = INVOICE_REF_FIELDS.get(key)
        if ref_spec and isinstance(parsed, dict):
            prefix, fields = ref_spec
            header.update(_flatten_ref(prefix, parsed, fields))
            continue

        if isinstance(parsed, (dict, list)):
            header[key] = json.dumps(parsed, default=str)
        else:
            header[key] = parsed
    return header


def unpack_qbd_invoice_line(*, txn_id: str | None, line: dict[str, Any]) -> dict[str, Any]:
    unpacked: dict[str, Any] = {"TxnID": txn_id}
    for key, value in line.items():
        parsed = parse_json_value(value)
        ref_spec = LINE_REF_FIELDS.get(key)
        if ref_spec and isinstance(parsed, dict):
            prefix, fields = ref_spec
            unpacked.update(_flatten_ref(prefix, parsed, fields))
            continue

        if isinstance(parsed, (dict, list)):
            unpacked[key] = json.dumps(parsed, default=str)
        else:
            unpacked[key] = parsed
    return unpacked


def unpack_qbd_invoice_lines(row: dict[str, Any]) -> list[dict[str, Any]]:
    txn_id = row.get("TxnID")
    if txn_id in (None, ""):
        return []

    lines: list[dict[str, Any]] = []
    for line in _coerce_line_items(row.get("InvoiceLineRet")):
        lines.append(unpack_qbd_invoice_line(txn_id=str(txn_id), line=line))
    return lines


def unpack_qbd_invoices(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Flatten invoice headers and explode line items from consolidated QBD invoice rows."""
    headers: list[dict[str, Any]] = []
    lines: list[dict[str, Any]] = []
    for row in rows:
        headers.append(unpack_qbd_invoice_header(row))
        lines.extend(unpack_qbd_invoice_lines(row))
    return headers, lines
