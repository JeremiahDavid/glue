"""Trigger scoped CDK deploys for client onboarding."""

from __future__ import annotations

import os
from typing import Any


def provisioning_project_name(environment: str) -> str:
    return f"meshflow-client-provision-{environment.strip().lower()}"


def start_client_deploy(
    *,
    company: str,
    environment: str,
    client_id: str,
    scope: str = "all",
    region: str | None = None,
) -> dict[str, Any]:
    """Start a CodeBuild project that runs scoped cdk deploy for one client."""
    import boto3
    from botocore.exceptions import ClientError

    resolved_region = (
        region
        or os.getenv("MESHFLOW_AWS_REGION", "").strip()
        or os.getenv("AWS_REGION", "").strip()
        or os.getenv("AWS_DEFAULT_REGION", "").strip()
        or None
    )
    project = os.getenv("MESHFLOW_PROVISIONING_PROJECT", "").strip() or provisioning_project_name(environment)
    client = boto3.client("codebuild", region_name=resolved_region)

    env_overrides = [
        {"name": "MESHFLOW_COMPANY", "value": company.strip().lower(), "type": "PLAINTEXT"},
        {"name": "MESHFLOW_ENVIRONMENT", "value": environment.strip().lower(), "type": "PLAINTEXT"},
        {"name": "MESHFLOW_PORTAL_CLIENT_ID", "value": client_id.strip().lower(), "type": "PLAINTEXT"},
        {"name": "MESHFLOW_CDK_SCOPE", "value": scope.strip().lower() or "all", "type": "PLAINTEXT"},
    ]

    try:
        response = client.start_build(
            projectName=project,
            environmentVariablesOverride=env_overrides,
        )
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code == "ResourceNotFoundException":
            return {
                "status": "misconfigured",
                "project": project,
                "message": (
                    f"CodeBuild project {project!r} was not found. "
                    "Deploy ProvisioningStack or run cdk deploy locally."
                ),
            }
        raise

    build = response.get("build", {})
    return {
        "status": "started",
        "project": project,
        "build_id": str(build.get("id", "")),
        "build_status": str(build.get("buildStatus", "")),
        "logs_url": str((build.get("logs") or {}).get("deepLink", "")),
    }


def get_build_status(build_id: str, *, region: str | None = None) -> dict[str, Any]:
    import boto3

    resolved_region = (
        region
        or os.getenv("MESHFLOW_AWS_REGION", "").strip()
        or os.getenv("AWS_REGION", "").strip()
        or os.getenv("AWS_DEFAULT_REGION", "").strip()
        or None
    )
    client = boto3.client("codebuild", region_name=resolved_region)
    response = client.batch_get_builds(ids=[build_id])
    builds = response.get("builds", [])
    if not builds:
        return {"build_id": build_id, "status": "unknown"}
    build = builds[0]
    return {
        "build_id": build_id,
        "status": str(build.get("buildStatus", "")),
        "current_phase": str(build.get("currentPhase", "")),
        "logs_url": str((build.get("logs") or {}).get("deepLink", "")),
    }
