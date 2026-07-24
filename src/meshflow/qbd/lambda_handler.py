from __future__ import annotations

from typing import Any


def handler(event: dict[str, Any] | None, _context: Any) -> dict[str, Any]:
    """QBD ingest is driven by QuickBooks Web Connector, not scheduled Lambda."""
    raise RuntimeError(
        "QuickBooks Desktop ingest runs via Web Connector SOAP polling. "
        "Deploy the QBD SOAP Lambda and configure QuickBooks Web Connector with the .qwc file."
    )
