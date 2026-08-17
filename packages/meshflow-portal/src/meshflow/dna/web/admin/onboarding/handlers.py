"""Onboarding wizard business logic for platform admin."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from meshflow.client_registry import (
    ClientCreateSpec,
    ClientRegistry,
    ConnectorSchedule,
    ConnectorSpec,
    DnaSpec,
    PortalClientSpec,
    verify_post_deploy,
)
from meshflow.provisioning import get_build_status, start_client_deploy
from meshflow.secrets_manager import ensure_secret_json, get_secret_json, put_secret_json


def list_onboarding_clients(*, environment: str | None = None) -> list[dict[str, Any]]:
    registry = ClientRegistry()
    return [asdict(record) for record in registry.list_clients(environment=environment)]


def parse_client_create_form(form: dict[str, str]) -> ClientCreateSpec:
    connector_source = str(form.get("connector_source", "dbc")).strip().lower()
    schedule = ConnectorSchedule(
        hour=int(form.get("schedule_hour", "6") or 6),
        minute=int(form.get("schedule_minute", "0") or 0),
    )
    dna_schedule = ConnectorSchedule(
        hour=int(form.get("dna_schedule_hour", "7") or 7),
        minute=int(form.get("dna_schedule_minute", "0") or 0),
    )
    return ClientCreateSpec(
        company=str(form.get("company", "")).strip().upper(),
        client_id=str(form.get("client_id", "")).strip().lower(),
        environment=str(form.get("environment", "dev")).strip().lower(),
        connector=ConnectorSpec(
            source=connector_source,
            entity_bundle=str(form.get("entity_bundle", "full")).strip(),
            schedule=schedule if connector_source in {"qbo", "dbc"} else None,
            tier=str(form.get("qbo_tier", "")).strip() or None,
        ),
        dna=DnaSpec(
            enabled=form.get("dna_enabled", "on") in {"on", "true", "1", "yes"},
            source=str(form.get("dna_source", connector_source)).strip().lower(),
            schedule=dna_schedule,
        ),
        portal=PortalClientSpec(
            display_name=str(form.get("display_name", "")).strip(),
            reporting_hostname=str(form.get("reporting_hostname", "")).strip().lower(),
            welcome_title=str(form.get("welcome_title", "")).strip() or "Your operational dashboard",
            welcome_message=str(form.get("welcome_message", "")).strip(),
            accent_color=str(form.get("accent_color", "#14b8a6")).strip() or "#14b8a6",
            max_users=int(form.get("max_users", "10") or 10),
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

    secret_id = registry.secret_name(record)
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
