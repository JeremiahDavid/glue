from __future__ import annotations

from meshflow.qbd.qbxml.parsers import parse_query_status


def test_empty_query_warn_status_is_success() -> None:
    response = """<?xml version="1.0" ?>
<QBXML>
<QBXMLMsgsRs>
<ReceivePaymentQueryRs requestID="3" statusCode="1" statusSeverity="Warn"
 statusMessage="A query request did not find a matching object in QuickBooks" />
</QBXMLMsgsRs>
</QBXML>"""
    ok, code, message = parse_query_status(response)
    assert ok is True
    assert code == 1
    assert message is not None


def test_empty_query_message_without_warn_severity_is_success() -> None:
    response = """<?xml version="1.0" ?>
<QBXML>
<QBXMLMsgsRs>
<ReceivePaymentQueryRs requestID="3" statusCode="1" statusSeverity="Info"
 statusMessage="A query request did not find a matching object in QuickBooks" />
</QBXMLMsgsRs>
</QBXML>"""
    ok, code, message = parse_query_status(response)
    assert ok is True
    assert code == 1
    assert "matching object" in (message or "")


def test_error_status_is_failure() -> None:
    response = """<?xml version="1.0" ?>
<QBXML>
<QBXMLMsgsRs>
<InvoiceQueryRs requestID="2" statusCode="3120" statusSeverity="Error"
 statusMessage="Object not found" />
</QBXMLMsgsRs>
</QBXML>"""
    ok, code, _message = parse_query_status(response)
    assert ok is False
    assert code == 3120
