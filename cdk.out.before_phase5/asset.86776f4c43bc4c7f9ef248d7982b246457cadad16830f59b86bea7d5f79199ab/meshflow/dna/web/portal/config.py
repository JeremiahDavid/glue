from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from meshflow.project_config import get_platform_environment_config, get_ui_config


@dataclass(frozen=True)
class ClientPortalConfig:
    client_id: str
    display_name: str
    welcome_title: str
    welcome_message: str
    reporting_company: str
    pack_id: str | None = None
    accent_color: str | None = None
    max_users: int = 10
    config_assistant_monthly_budget_usd: float = 10.0
    dna_manual_refresh_monthly_limit: int = 10


def load_platform_env_config(environment: str) -> dict[str, Any]:
    try:
        return get_platform_environment_config(environment)
    except KeyError:
        return {}


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

    default_max_users = portal_cfg.get("default_max_users", 10)
    try:
        default_max_users = int(default_max_users)
    except (TypeError, ValueError):
        default_max_users = 10

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
    reporting_company = str(raw.get("reporting_company", "")).strip()
    max_users_raw = raw.get("max_users", default_max_users)
    try:
        max_users = int(max_users_raw)
    except (TypeError, ValueError):
        max_users = default_max_users
    if max_users < 1:
        max_users = default_max_users

    default_assistant_cfg = portal_cfg.get("config_assistant", {})
    if not isinstance(default_assistant_cfg, dict):
        default_assistant_cfg = {}
    assistant_cfg = raw.get("config_assistant", default_assistant_cfg)
    if not isinstance(assistant_cfg, dict):
        assistant_cfg = default_assistant_cfg
    budget_raw = assistant_cfg.get(
        "monthly_budget_usd",
        default_assistant_cfg.get("monthly_budget_usd", 10.0),
    )
    try:
        config_assistant_monthly_budget_usd = float(budget_raw)
    except (TypeError, ValueError):
        config_assistant_monthly_budget_usd = 10.0
    if config_assistant_monthly_budget_usd <= 0:
        config_assistant_monthly_budget_usd = 10.0

    default_refresh_cfg = portal_cfg.get("dna_manual_refresh", {})
    if not isinstance(default_refresh_cfg, dict):
        default_refresh_cfg = {}
    refresh_cfg = raw.get("dna_manual_refresh", default_refresh_cfg)
    if not isinstance(refresh_cfg, dict):
        refresh_cfg = default_refresh_cfg
    refresh_limit_raw = refresh_cfg.get(
        "monthly_limit",
        default_refresh_cfg.get("monthly_limit", 10),
    )
    try:
        dna_manual_refresh_monthly_limit = int(refresh_limit_raw)
    except (TypeError, ValueError):
        dna_manual_refresh_monthly_limit = 10
    if dna_manual_refresh_monthly_limit <= 0:
        dna_manual_refresh_monthly_limit = 10

    return ClientPortalConfig(
        client_id=client_id,
        display_name=display_name,
        welcome_title=welcome_title,
        welcome_message=welcome_message,
        reporting_company=reporting_company,
        pack_id=pack_id,
        accent_color=accent,
        max_users=max_users,
        config_assistant_monthly_budget_usd=config_assistant_monthly_budget_usd,
        dna_manual_refresh_monthly_limit=dna_manual_refresh_monthly_limit,
    )
