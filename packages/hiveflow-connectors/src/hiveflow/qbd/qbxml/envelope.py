from __future__ import annotations

from xml.etree.ElementTree import Element, tostring


def qbxml_envelope(version: str, *requests: Element, on_error: str = "stopOnError") -> str:
    msgs = Element("QBXMLMsgsRq", onError=on_error)
    for req in requests:
        msgs.append(req)

    root = Element("QBXML")
    root.append(msgs)

    decl = f'<?xml version="1.0" encoding="utf-8"?>\n<?qbxml version="{version}"?>\n'
    return decl + tostring(root, encoding="unicode")


def add_text(parent: Element, tag: str, value: str | None) -> None:
    if value is not None:
        child = Element(tag)
        child.text = value
        parent.append(child)


def query_request(
    tag: str,
    *,
    request_id: str = "1",
    max_returned: int = 100,
    from_modified_date: str | None = None,
    wrap_modified_date: bool = False,
    iterator: str | None = None,
    iterator_id: str | None = None,
    include_line_items: bool = False,
) -> Element:
    req = Element(f"{tag}QueryRq", requestID=request_id)
    if iterator:
        req.set("iterator", iterator)
    if iterator_id:
        req.set("iteratorID", iterator_id)

    add_text(req, "MaxReturned", str(max_returned))

    if from_modified_date:
        if wrap_modified_date:
            date_filter = Element("ModifiedDateRangeFilter")
            add_text(date_filter, "FromModifiedDate", from_modified_date)
            req.append(date_filter)
        else:
            add_text(req, "FromModifiedDate", from_modified_date)

    if include_line_items and tag in {
        "Invoice",
        "Bill",
        "SalesReceipt",
        "CreditMemo",
        "Deposit",
        "Estimate",
    }:
        add_text(req, "IncludeLineItems", "true")
    return req
