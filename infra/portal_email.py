"""SES-backed Cognito portal invite email — verified domain + Route 53 DKIM records."""

from __future__ import annotations

from typing import Any

from aws_cdk import aws_cognito as cognito
from aws_cdk import aws_route53 as route53
from aws_cdk import aws_ses as ses
from constructs import Construct


def resolve_portal_email_settings(ui_config: dict[str, Any]) -> dict[str, str] | None:
    """Return SES sender settings when portal email is enabled in config.yaml."""
    portal_cfg = ui_config.get("portal", {})
    if not isinstance(portal_cfg, dict):
        portal_cfg = {}

    email_cfg = portal_cfg.get("email", {})
    if not isinstance(email_cfg, dict):
        email_cfg = {}

    if not email_cfg.get("enabled", False):
        return None

    domain_cfg = ui_config.get("domain", {})
    if not isinstance(domain_cfg, dict):
        domain_cfg = {}

    zone_name = str(domain_cfg.get("zone_name", "")).strip().lower().rstrip(".")
    hosted_zone_id = str(domain_cfg.get("hosted_zone_id", "")).strip()
    if not zone_name or not hosted_zone_id:
        raise ValueError(
            "platform.environments.*.ui.portal.email.enabled requires "
            "domain.zone_name and domain.hosted_zone_id in config.yaml."
        )

    from_address = str(email_cfg.get("from_address", f"noreply@{zone_name}")).strip().lower()
    from_name = str(email_cfg.get("from_name", "HiveFlowAI")).strip() or "HiveFlowAI"
    if "@" not in from_address:
        raise ValueError(f"portal.email.from_address must be a full email address, got {from_address!r}.")
    from_domain = from_address.split("@", 1)[1]
    if from_domain != zone_name and not from_domain.endswith(f".{zone_name}"):
        raise ValueError(
            f"portal.email.from_address domain {from_domain!r} must match zone_name {zone_name!r}."
        )

    return {
        "zone_name": zone_name,
        "hosted_zone_id": hosted_zone_id,
        "from_address": from_address,
        "from_name": from_name,
    }


def configure_portal_user_pool_email(
    scope: Construct,
    *,
    id_prefix: str,
    ui_config: dict[str, Any],
    region: str,
) -> cognito.UserPoolEmail | None:
    """Provision SES domain identity (DKIM in Route 53) and Cognito SES sender config."""
    settings = resolve_portal_email_settings(ui_config)
    if settings is None:
        return None

    hosted_zone = route53.HostedZone.from_hosted_zone_attributes(
        scope,
        f"{id_prefix}PortalSesHostedZone",
        hosted_zone_id=settings["hosted_zone_id"],
        zone_name=settings["zone_name"],
    )

    ses.EmailIdentity(
        scope,
        f"{id_prefix}PortalSesIdentity",
        identity=ses.Identity.public_hosted_zone(hosted_zone),
    )

    return cognito.UserPoolEmail.with_ses(
        from_email=settings["from_address"],
        from_name=settings["from_name"],
        reply_to=settings["from_address"],
        ses_region=region,
        ses_verified_domain=settings["zone_name"],
    )
