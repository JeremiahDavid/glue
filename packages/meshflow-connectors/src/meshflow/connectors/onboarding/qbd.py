"""QuickBooks Desktop onboarding helpers."""

from __future__ import annotations

import uuid
from typing import Any

from meshflow.qbd.qwc import build_qwc_xml


def qbd_secret_status(secret_payload: dict[str, Any]) -> dict[str, Any]:
    username = str(secret_payload.get("QBD_QBWC_USERNAME", "")).strip()
    soap_url = str(secret_payload.get("QBWC_SOAP_URL", "")).strip()
    missing = []
    if not username:
        missing.append("QBD_QBWC_USERNAME")
    if not soap_url:
        missing.append("QBWC_SOAP_URL")
    if missing:
        return {
            "ok": False,
            "missing": missing,
            "message": "QBD secret is incomplete — add QBWC username and SOAP URL after ingest deploy.",
        }
    return {"ok": True, "username": username, "soap_url": soap_url}


def generate_qwc_xml(
    *,
    app_name: str,
    soap_url: str,
    username: str,
    owner_id: str = "",
    file_id: str = "",
) -> str:
    resolved_owner = owner_id.strip() or ("{" + str(uuid.uuid4()).upper() + "}")
    resolved_file = file_id.strip() or ("{" + str(uuid.uuid4()).upper() + "}")
    return build_qwc_xml(
        app_name=app_name.strip() or "Meshflow QBD",
        app_url=soap_url.strip(),
        app_support_url=soap_url.strip(),
        username=username.strip(),
        owner_id=resolved_owner,
        file_id=resolved_file,
    )
