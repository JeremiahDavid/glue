"""Onboarding wizard business logic for platform admin."""

from __future__ import annotations

import re
from dataclasses import asdict
from typing import Any

from meshflow.client_registry import (
    ClientCreateSpec,
    ClientRegistry,
    ConnectorSchedule,
    ConnectorSpec,
    DnaSpec,
    PortalClientSpec,
    SUPPORTED_CONNECTORS,
    verify_post_deploy,
)
from meshflow.provisioning import get_build_status, start_client_deploy
from meshflow.secrets_manager import ensure_secret_json, get_secret_json, put_secret_json


def list_onboarding_clients(*, environment: str | None = None) -> list[dict[str, Any]]:
    registry = ClientRegistry()
    return [asdict(record) for record in registry.list_clients(environment=environment)]


def company_from_display_name(display_name: str) -> str:
    parts = [part for part in re.split(r"[^A-Za-z0-9]+", display_name.strip()) if part]
    if not parts:
        raise ValueError("Display name must include at least one letter or number")
    camel = parts[0].lower() + "".join(part.capitalize() for part in parts[1:])
    company = camel.upper()
    if not company[0].isalpha():
        company = f"C{company}"
    return company[:63]


_CONNECTOR_DEFAULTS: dict[str, dict[str, str | int]] = {
    "dbc": {"entity_bundle": "full", "schedule_hour": 6, "schedule_minute": 30},
    "qbo": {"entity_bundle": "full_accounting", "schedule_hour": 6, "schedule_minute": 0, "tier": "sandbox"},
    "qbd": {"entity_bundle": "full_accounting"},
}


def _form_enabled(value: str) -> bool:
    return value.strip().lower() in {"on", "true", "1", "yes"}


def parse_connectors_from_form(form: dict[str, str]) -> tuple[ConnectorSpec, ...]:
    connectors: list[ConnectorSpec] = []
    for source in sorted(SUPPORTED_CONNECTORS):
        if not _form_enabled(str(form.get(f"connector_{source}_enabled", ""))):
            continue
        defaults = _CONNECTOR_DEFAULTS[source]
        schedule = None
        if source in {"qbo", "dbc"}:
            schedule = ConnectorSchedule(
                hour=int(form.get(f"connector_{source}_schedule_hour", str(defaults["schedule_hour"])) or 6),
                minute=int(form.get(f"connector_{source}_schedule_minute", str(defaults["schedule_minute"])) or 0),
            )
        tier = None
        if source == "qbo":
            tier = str(form.get("connector_qbo_tier", str(defaults.get("tier", "")))).strip() or None
        connectors.append(
            ConnectorSpec(
                source=source,
                entity_bundle=str(
                    form.get(f"connector_{source}_entity_bundle", str(defaults["entity_bundle"]))
                ).strip(),
                schedule=schedule,
                tier=tier,
            )
        )
    if not connectors:
        raise ValueError("At least one connector must be enabled")
    return tuple(connectors)


def parse_client_create_form(form: dict[str, str]) -> ClientCreateSpec:
    display_name = str(form.get("display_name", "")).strip()
    client_id = str(form.get("client_id", "")).strip().lower()
    connectors = parse_connectors_from_form(form)
    connector_sources = [item.source for item in connectors]
    dna_source = "dbc" if "dbc" in connector_sources else connector_sources[0]
    dna_schedule = None
    return ClientCreateSpec(
        company=company_from_display_name(display_name),
        client_id=client_id,
        environment="dev",
        connectors=connectors,
        dna=DnaSpec(
            enabled=form.get("dna_enabled", "on") in {"on", "true", "1", "yes"},
            source=str(form.get("dna_source", dna_source)).strip().lower(),
            schedule=dna_schedule,
        ),
        portal=PortalClientSpec(
            display_name=display_name,
            reporting_hostname=client_id,
            welcome_title=str(form.get("welcome_title", "")).strip() or "Your operational dashboard",
            welcome_message=str(form.get("welcome_message", "")).strip(),
        ),
        aws_region=str(form.get("aws_region", "us-east-2")).strip() or "us-east-2",
    )


def create_client_from_form(form: dict[str, str]) -> dict[str, Any]:
    spec = parse_client_create_form(form)
    registry = ClientRegistry()
    record = registry.create_client(spec)
    return {"ok": True, "client": asdict(record)}


def save_connector_secret(
    *,
    company: str,
    environment: str,
    source: str,
    credentials: dict[str, str],
    region: str | None = None,
) -> dict[str, Any]:
    registry = ClientRegistry()
    record = registry.get_client(company, environment=environment)
    if record is None:
        raise ValueError(f"No portal client found for company {company!r}")

    secret_id = registry.secret_name(record, source=source)
    payload = {key: str(value).strip() for key, value in credentials.items() if str(value).strip()}
    result = ensure_secret_json(
        secret_id,
        payload,
        region=region,
        source=source,
        company=company,
        environment=environment,
    )
    if result == "exists":
        put_secret_json(secret_id, payload, region=region)
    return {"secret_id": secret_id, "result": result}


def validate_connector(
    *,
    source: str,
    credentials: dict[str, str],
    secret_id: str | None = None,
    region: str | None = None,
) -> dict[str, Any]:
    source_key = source.strip().lower()
    if source_key == "dbc":
        from meshflow.connectors.onboarding.dbc import validate_dbc_credentials

        return validate_dbc_credentials(credentials)

    if source_key == "qbo":
        from meshflow.connectors.onboarding.qbo import qbo_oauth_status

        payload = credentials
        if secret_id:
            try:
                payload = get_secret_json(secret_id, region=region)
            except ValueError:
                pass
        return qbo_oauth_status(payload)

    if source_key == "qbd":
        from meshflow.connectors.onboarding.qbd import qbd_secret_status

        payload = credentials
        if secret_id:
            try:
                payload = get_secret_json(secret_id, region=region)
            except ValueError:
                pass
        return qbd_secret_status(payload)

    return {"ok": False, "error": f"Unsupported connector {source!r}"}


def trigger_deploy(
    *,
    company: str,
    environment: str,
    client_id: str,
    scope: str = "all",
    region: str | None = None,
) -> dict[str, Any]:
    return start_client_deploy(
        company=company,
        environment=environment,
        client_id=client_id,
        scope=scope,
        region=region,
    )


def client_deploy_status(
    *,
    company: str,
    environment: str,
    client_id: str,
    region: str | None = None,
) -> dict[str, Any]:
    registry = ClientRegistry()
    record = registry.get_client(company, environment=environment, client_id=client_id)
    if record is None:
        raise ValueError(f"Client {company}/{client_id} not found")
    status = registry.get_deploy_status(record, region=region)
    verification = verify_post_deploy(record, region=region)
    return {
        "deploy": {
            "company": status.company,
            "client_id": status.client_id,
            "environment": status.environment,
            "stacks": [
                {
                    "stack_name": item.stack_name,
                    "status": item.status.value,
                    "status_reason": item.status_reason,
                    "events": item.events,
                }
                for item in status.stacks
            ],
        },
        "verification": verification,
    }


def generate_qwc_download(
    *,
    soap_url: str,
    username: str,
    app_name: str = "Meshflow QBD",
) -> str:
    from meshflow.connectors.onboarding.qbd import generate_qwc_xml

    return generate_qwc_xml(
        app_name=app_name,
        soap_url=soap_url,
        username=username,
    )


def build_status(build_id: str, *, region: str | None = None) -> dict[str, Any]:
    return get_build_status(build_id, region=region)
