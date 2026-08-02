from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from meshflow.project_config import get_ui_config


@dataclass(frozen=True)
class ClientPortalConfig:
    client_id: str
    display_name: str
    welcome_title: str
    welcome_message: str
    pack_id: str | None = None
    accent_color: str | None = None


def load_client_portal_config(
    client_id: str,
    env_config: dict[str, Any],
    *,
    default_pack_id: str,
) -> ClientPortalConfig:
    ui_cfg = get_ui_config(env_config)
    portal_cfg = ui_cfg.get("portal", {})
    if not isinstance(portal_cfg, dict):
        portal_cfg = {}

    clients = portal_cfg.get("clients", {})
    if not isinstance(clients, dict):
        clients = {}

    raw = clients.get(client_id, clients.get("default", {}))
    if not isinstance(raw, dict):
        raw = {}

    display_name = str(raw.get("display_name", client_id)).strip() or client_id
    welcome_title = str(raw.get("welcome_title", f"{display_name} portal")).strip()
    welcome_message = str(
        raw.get(
            "welcome_message",
            "Certified metrics from your governed semantic layer — every number traceable to an approved definition.",
        )
    ).strip()
    pack_id = str(raw.get("pack_id", default_pack_id)).strip() or default_pack_id
    accent = str(raw.get("accent_color", "")).strip() or None

    return ClientPortalConfig(
        client_id=client_id,
        display_name=display_name,
        welcome_title=welcome_title,
        welcome_message=welcome_message,
        pack_id=pack_id,
        accent_color=accent,
    )
