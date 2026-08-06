from __future__ import annotations

from datetime import datetime
from typing import Any
from xml.etree.ElementTree import Element

from lxml import etree

from meshflow.qbd.models import EntityType
from meshflow.qbd.qbxml.entity_tags import RET_TAG


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def _element_to_dict(el: Element) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for child in el:
        tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
        if len(child):
            if tag.endswith("Ret") or tag.endswith("Line") or tag == "AppliedToTxnRet":
                result.setdefault(tag, []).append(_element_to_dict(child))
            else:
                nested = _element_to_dict(child)
                if nested:
                    result[tag] = nested
                elif child.text:
                    result[tag] = child.text
        elif child.text is not None:
            existing = result.get(tag)
            if existing is None:
                result[tag] = child.text
            elif isinstance(existing, list):
                existing.append(child.text)
            else:
                result[tag] = [existing, child.text]
    return result


def parse_iterator_info(response_xml: str) -> tuple[str | None, int | None]:
    root = etree.fromstring(response_xml.encode("utf-8"))
    for rs in root.iter():
        tag = rs.tag.split("}")[-1] if "}" in rs.tag else rs.tag
        if tag.endswith("QueryRs"):
            iterator_id = rs.get("iteratorID")
            remaining = rs.get("iteratorRemainingCount")
            return iterator_id, int(remaining) if remaining else None
    return None, None


def parse_status_code(response_xml: str) -> tuple[int, str | None]:
    ok, code, message = parse_query_status(response_xml)
    if ok:
        return 0 if code != 0 else code, message
    return code, message


def _is_empty_query_result(code: int, message: str | None) -> bool:
    if code == 1:
        return True
    if message and "did not find a matching object" in message.casefold():
        return True
    return False


def parse_query_status(response_xml: str) -> tuple[bool, int, str | None]:
    """Return whether a QueryRs response should be treated as success."""
    root = etree.fromstring(response_xml.encode("utf-8"))
    for rs in root.iter():
        tag = rs.tag.split("}")[-1] if "}" in rs.tag else rs.tag
        if tag.endswith("QueryRs"):
            code = int(rs.get("statusCode", "0"))
            message = rs.get("statusMessage")
            if code == 0:
                return True, code, message
            if _is_empty_query_result(code, message):
                return True, code, message
            return False, code, message
    return True, 0, None


def extract_records(response_xml: str, entity_type: EntityType) -> list[dict[str, Any]]:
    root = etree.fromstring(response_xml.encode("utf-8"))
    ret_tag = RET_TAG[entity_type]
    records: list[dict[str, Any]] = []

    for el in root.iter():
        tag = el.tag.split("}")[-1] if "}" in el.tag else el.tag
        if tag == ret_tag:
            data = _element_to_dict(el)
            if data:
                records.append(data)

    return records


def is_open_invoice(record: dict[str, Any]) -> bool:
    if str(record.get("IsPaid", "")).lower() == "true":
        return False
    balance = record.get("BalanceRemaining", record.get("AppliedAmount"))
    if balance in (None, ""):
        return True
    try:
        return float(str(balance).replace(",", "")) > 0
    except ValueError:
        return True
