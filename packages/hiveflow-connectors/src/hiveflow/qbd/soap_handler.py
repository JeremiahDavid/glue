from __future__ import annotations

from typing import Any

from hiveflow.qbd.qbwc.server import create_wsgi_app

_soap_wsgi = create_wsgi_app()


def soap_handler(event: dict[str, Any] | None, context: Any) -> dict[str, Any]:
    """Lambda entry point for QuickBooks Web Connector SOAP requests."""
    try:
        import awsgi
    except ImportError as exc:
        raise RuntimeError(
            "aws-wsgi is required for the QBD SOAP Lambda. "
            'Install hiveflow with deploy extras: pip install "hiveflow[qbd-deploy]"'
        ) from exc

    return awsgi.response(_soap_wsgi, event, context)
