from __future__ import annotations

from datetime import datetime

from hiveflow.qbd.models import EntityType
from hiveflow.qbd.qbxml.envelope import qbxml_envelope, query_request

ENTITY_QUERY_TAG: dict[EntityType, str] = {
    EntityType.COMPANY: "Company",
    EntityType.ACCOUNT: "Account",
    EntityType.CLASS: "Class",
    EntityType.DEPARTMENT: "Department",
    EntityType.CUSTOMER: "Customer",
    EntityType.VENDOR: "Vendor",
    EntityType.ITEM: "Item",
    EntityType.INVOICE: "Invoice",
    EntityType.BILL: "Bill",
    EntityType.SALES_RECEIPT: "SalesReceipt",
    EntityType.CREDIT_MEMO: "CreditMemo",
    EntityType.DEPOSIT: "Deposit",
    EntityType.RECEIVE_PAYMENT: "ReceivePayment",
    EntityType.ESTIMATE: "Estimate",
}

TRANSACTION_ENTITIES = {
    EntityType.INVOICE,
    EntityType.BILL,
    EntityType.SALES_RECEIPT,
    EntityType.CREDIT_MEMO,
    EntityType.DEPOSIT,
    EntityType.ESTIMATE,
}

MODIFIED_DATE_RANGE_ENTITIES = TRANSACTION_ENTITIES | {EntityType.RECEIVE_PAYMENT}

# QuickBooks OSR: these list queries reject iterator attributes (0x80040400).
NO_ITERATOR_ENTITIES = {
    EntityType.ACCOUNT,
    EntityType.CLASS,
}


def format_qb_datetime(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        dt = dt.replace(tzinfo=None)
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def build_entity_query(
    entity_type: EntityType,
    *,
    qbxml_version: str,
    from_modified_date: datetime | None = None,
    max_returned: int = 100,
    iterator: str | None = None,
    iterator_id: str | None = None,
    request_id: str = "1",
) -> str:
    if entity_type == EntityType.COMPANY:
        from xml.etree.ElementTree import Element

        req = Element("CompanyQueryRq", requestID=request_id)
        return qbxml_envelope(qbxml_version, req)

    tag = ENTITY_QUERY_TAG[entity_type]
    from_str = format_qb_datetime(from_modified_date)
    page_iterator = iterator
    if page_iterator is None and not iterator_id and entity_type not in NO_ITERATOR_ENTITIES:
        page_iterator = "Start"
    req = query_request(
        tag,
        request_id=request_id,
        max_returned=max_returned,
        from_modified_date=from_str,
        wrap_modified_date=entity_type in MODIFIED_DATE_RANGE_ENTITIES,
        iterator=page_iterator,
        iterator_id=iterator_id,
        include_line_items=entity_type in TRANSACTION_ENTITIES,
    )
    return qbxml_envelope(qbxml_version, req)
