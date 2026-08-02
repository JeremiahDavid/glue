from __future__ import annotations

from typing import Any

from aws_cdk import CfnOutput, Fn, aws_apigateway as apigateway
from aws_cdk import aws_certificatemanager as acm
from aws_cdk import aws_route53 as route53
from aws_cdk import aws_route53_targets as route53_targets
from constructs import Construct

from meshflow.dna.web.domain_names import dns_record_name, expand_hostnames


def _sanitize_id(hostname: str) -> str:
    return hostname.replace(".", "-").replace("*", "star")


def attach_custom_domain(
    scope: Construct,
    *,
    web_api: apigateway.RestApi,
    domain_config: dict[str, Any],
) -> dict[str, Any]:
    """Attach Route53 + ACM + API Gateway custom domain mappings for the UI."""
    zone_name = str(domain_config.get("zone_name", "")).strip().lower().rstrip(".")
    if not zone_name:
        raise ValueError("ui.domain.zone_name is required when ui.domain is configured")

    primary_hostname = str(domain_config.get("primary_hostname", zone_name)).strip().lower().rstrip(".")
    alternate_raw = domain_config.get("alternate_hostnames", ["www"])
    if not isinstance(alternate_raw, list):
        alternate_raw = ["www"]

    hostnames = expand_hostnames(
        zone_name=zone_name,
        primary_hostname=primary_hostname,
        alternate_hostnames=[str(item) for item in alternate_raw],
    )

    hosted_zone_id = str(domain_config.get("hosted_zone_id", "")).strip()
    create_hosted_zone = bool(domain_config.get("create_hosted_zone", not hosted_zone_id))

    if hosted_zone_id:
        hosted_zone = route53.HostedZone.from_hosted_zone_attributes(
            scope,
            "ImportedHostedZone",
            hosted_zone_id=hosted_zone_id,
            zone_name=zone_name,
        )
    elif create_hosted_zone:
        hosted_zone = route53.PublicHostedZone(
            scope,
            "PublicHostedZone",
            zone_name=zone_name,
            comment=f"HiveFlowAI public site and client portal ({zone_name})",
        )
    else:
        raise ValueError(
            "ui.domain requires hosted_zone_id or create_hosted_zone: true "
            "so CDK can manage DNS records and ACM validation"
        )

    certificate = acm.Certificate(
        scope,
        "SiteCertificate",
        domain_name=primary_hostname,
        subject_alternative_names=[name for name in hostnames if name != primary_hostname],
        validation=acm.CertificateValidation.from_dns(hosted_zone),
    )

    custom_urls: list[str] = []
    for index, hostname in enumerate(hostnames):
        domain = apigateway.DomainName(
            scope,
            f"CustomDomain{_sanitize_id(hostname)}",
            domain_name=hostname,
            certificate=certificate,
            endpoint_type=apigateway.EndpointType.REGIONAL,
        )
        apigateway.BasePathMapping(
            scope,
            f"BasePathMapping{_sanitize_id(hostname)}",
            domain_name=domain,
            rest_api=web_api,
            stage=web_api.deployment_stage,
        )
        route53.ARecord(
            scope,
            f"AliasRecord{_sanitize_id(hostname)}",
            zone=hosted_zone,
            record_name=dns_record_name(hostname, zone_name),
            target=route53.RecordTarget.from_alias(route53_targets.ApiGatewayDomain(domain)),
        )
        custom_urls.append(f"https://{hostname}/")

    if create_hosted_zone and not hosted_zone_id:
        CfnOutput(
            scope,
            "Route53NameServers",
            value=Fn.join(", ", hosted_zone.hosted_zone_name_servers),
            description=(
                "Update your Squarespace domain nameservers to these Route 53 values "
                "to delegate DNS for the custom domain"
            ),
        )
        for index in range(4):
            CfnOutput(
                scope,
                f"Route53NameServer{index + 1}",
                value=Fn.select(index, hosted_zone.hosted_zone_name_servers),
                description=f"Route 53 nameserver {index + 1} for Squarespace delegation",
            )

    CfnOutput(
        scope,
        "PrimarySiteUrl",
        value=f"https://{primary_hostname}/",
        description="Primary HiveFlowAI site URL after DNS delegation completes",
    )
    CfnOutput(
        scope,
        "CustomDomainHostnames",
        value=", ".join(hostnames),
        description="Hostnames mapped to the HiveFlowAI UI API",
    )

    return {
        "zone_name": zone_name,
        "primary_hostname": primary_hostname,
        "hostnames": hostnames,
        "custom_urls": custom_urls,
    }
