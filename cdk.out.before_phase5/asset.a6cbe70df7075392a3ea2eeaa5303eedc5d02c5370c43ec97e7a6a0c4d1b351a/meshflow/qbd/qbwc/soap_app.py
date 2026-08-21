from __future__ import annotations

from typing import Any, Callable
from xml.sax.saxutils import escape

from lxml import etree

SOAP_ENV = "http://schemas.xmlsoap.org/soap/envelope/"
QBWC_NS = "http://developer.intuit.com/"


def _local(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag


def _find_body_child(root: etree._Element) -> tuple[str, etree._Element] | None:
    body = next(
        (el for el in root.iter() if _local(el.tag) == "Body"),
        None,
    )
    if body is None:
        return None
    for child in body:
        return _local(child.tag), child
    return None


def _text(parent: etree._Element, tag: str) -> str:
    for child in parent:
        if _local(child.tag) == tag:
            return (child.text or "").strip()
    return ""


def _soap_response(method: str, payload_xml: str) -> bytes:
    envelope = f"""<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="{SOAP_ENV}">
  <soap:Body>
    <{method}Response xmlns="{QBWC_NS}">
      {payload_xml}
    </{method}Response>
  </soap:Body>
</soap:Envelope>"""
    return envelope.encode("utf-8")


def _authenticate_result(values: list[str]) -> str:
    items = "".join(f"<string>{value}</string>" for value in values)
    return f"<authenticateResult>{items}</authenticateResult>"


class QBWCSoapApp:
    """Minimal QuickBooks Web Connector SOAP WSGI application."""

    def __init__(self, engine: Any) -> None:
        self.engine = engine
        self._handlers: dict[str, Callable[[etree._Element], bytes]] = {
            "authenticate": self._handle_authenticate,
            "clientVersion": self._handle_client_version,
            "connectionError": self._handle_connection_error,
            "getLastError": self._handle_get_last_error,
            "closeConnection": self._handle_close_connection,
            "receiveResponseXML": self._handle_receive_response_xml,
            "sendRequestXML": self._handle_send_request_xml,
            "serverVersion": self._handle_server_version,
        }

    def __call__(self, environ: dict[str, Any], start_response: Callable) -> list[bytes]:
        path = environ.get("PATH_INFO", "/") or "/"
        if path not in {"/", "/soap"} and not path.endswith("/soap"):
            start_response("404 Not Found", [("Content-Type", "text/plain")])
            return [b"Not Found"]

        method = environ.get("REQUEST_METHOD", "GET").upper()
        if method == "GET":
            start_response("200 OK", [("Content-Type", "text/plain")])
            return [b"Meshflow QuickBooks Web Connector endpoint"]

        try:
            length = int(environ.get("CONTENT_LENGTH") or "0")
        except ValueError:
            length = 0
        body = environ["wsgi.input"].read(length) if length else b""
        if not body:
            start_response("400 Bad Request", [("Content-Type", "text/plain")])
            return [b"Missing SOAP body"]

        try:
            root = etree.fromstring(body)
        except etree.XMLSyntaxError:
            start_response("400 Bad Request", [("Content-Type", "text/plain")])
            return [b"Invalid XML"]

        parsed = _find_body_child(root)
        if parsed is None:
            start_response("400 Bad Request", [("Content-Type", "text/plain")])
            return [b"Missing SOAP body payload"]

        method_name, payload = parsed
        handler = self._handlers.get(method_name)
        if handler is None:
            start_response("400 Bad Request", [("Content-Type", "text/plain")])
            return [f"Unknown method: {method_name}".encode()]

        response_body = handler(payload)
        start_response("200 OK", [("Content-Type", "text/xml; charset=utf-8")])
        return [response_body]

    def _handle_authenticate(self, payload: etree._Element) -> bytes:
        ticket, company_file = self.engine.authenticate(
            _text(payload, "strUserName"),
            _text(payload, "strPassword"),
        )
        inner = _authenticate_result([ticket, company_file])
        return _soap_response("authenticate", inner)

    def _handle_send_request_xml(self, payload: etree._Element) -> bytes:
        ticket = _text(payload, "ticket")
        xml = self.engine.next_request_xml(ticket) or ""
        inner = f"<sendRequestXMLResult>{etree.CDATA(xml) if xml else ''}</sendRequestXMLResult>"
        if not xml:
            inner = "<sendRequestXMLResult></sendRequestXMLResult>"
        else:
            inner = f"<sendRequestXMLResult><![CDATA[{xml}]]></sendRequestXMLResult>"
        return _soap_response("sendRequestXML", inner)

    def _handle_receive_response_xml(self, payload: etree._Element) -> bytes:
        ticket = _text(payload, "ticket")
        response = _text(payload, "response")
        progress = self.engine.process_response(
            ticket,
            response,
            hresult=_text(payload, "hresult"),
            message=_text(payload, "message"),
        )
        inner = f"<receiveResponseXMLResult>{progress}</receiveResponseXMLResult>"
        return _soap_response("receiveResponseXML", inner)

    def _handle_server_version(self, _payload: etree._Element) -> bytes:
        inner = "<serverVersionResult>1.0.0</serverVersionResult>"
        return _soap_response("serverVersion", inner)

    def _handle_client_version(self, _payload: etree._Element) -> bytes:
        # Empty result accepts the QBWC client version.
        inner = "<clientVersionResult></clientVersionResult>"
        return _soap_response("clientVersion", inner)

    def _handle_connection_error(self, payload: etree._Element) -> bytes:
        ticket = _text(payload, "ticket")
        hresult = _text(payload, "hresult")
        message = _text(payload, "message") or hresult
        retry = hresult.lower() in {"0x80040408", "80040408"}
        if not retry:
            self.engine.connection_error(ticket, message)
        result = "" if retry else "done"
        inner = f"<connectionErrorResult>{result}</connectionErrorResult>"
        return _soap_response("connectionError", inner)

    def _handle_get_last_error(self, payload: etree._Element) -> bytes:
        ticket = _text(payload, "ticket")
        error = self.engine.get_last_error(ticket)
        inner = f"<getLastErrorResult>{escape(error)}</getLastErrorResult>"
        return _soap_response("getLastError", inner)

    def _handle_close_connection(self, payload: etree._Element) -> bytes:
        ticket = _text(payload, "ticket")
        self.engine.close_session(ticket)
        inner = "<closeConnectionResult>OK</closeConnectionResult>"
        return _soap_response("closeConnection", inner)
