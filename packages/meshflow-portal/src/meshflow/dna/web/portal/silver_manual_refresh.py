"""Per-client manual connector (silver) refresh quota, status, and Step Functions trigger."""

from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from meshflow.compat import UTC
from typing import Any, Callable

from meshflow.dna.settings import DnaSettings
from meshflow.dna.source_docs.reference import load_silver_schema_profile
from meshflow.dna.sql_pack import load_sql_pack
from meshflow.dna.store import read_json_artifact, write_json_artifact

DEFAULT_MONTHLY_LIMIT = 10
_EXECUTION_NAME_RE = re.compile(r"[^a-zA-Z0-9_-]")


class SilverManualRefreshQuotaExceeded(Exception):
    """Raised when a client has exhausted their monthly silver refresh allowance."""

    def __init__(self, *, monthly_limit: int, used: int) -> None:
        self.monthly_limit = monthly_limit
        self.used = used
        super().__init__(
            f"Manual silver refresh limit reached ({used} of {monthly_limit} used this month). "
            "Try again next month or contact your administrator."
        )


class SilverManualRefreshInProgress(Exception):
    """Raised when a prior manual silver refresh is still running."""

    def __init__(self, *, execution_arn: str) -> None:
        self.execution_arn = execution_arn
        super().__init__(
            "A connector silver refresh is already in progress. "
            "Wait for it to finish before starting another."
        )


@dataclass(frozen=True)
class SilverManualRefreshQuota:
    client_id: str
    month: str
    used: int
    monthly_limit: int
    remaining: int
    at_limit: bool
    in_progress: bool
    last_execution_arn: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "client_id": self.client_id,
            "month": self.month,
            "used": self.used,
            "monthly_limit": self.monthly_limit,
            "remaining": self.remaining,
            "at_limit": self.at_limit,
            "in_progress": self.in_progress,
            "last_execution_arn": self.last_execution_arn,
        }


@dataclass(frozen=True)
class SilverRefreshStatus:
    pinned_version: str
    applied_version: str
    consolidated_at: str
    source: str
    is_stale: bool
    has_silver_transforms: bool
    has_silver_profile: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "pinned_version": self.pinned_version,
            "applied_version": self.applied_version,
            "consolidated_at": self.consolidated_at,
            "source": self.source,
            "is_stale": self.is_stale,
            "has_silver_transforms": self.has_silver_transforms,
            "has_silver_profile": self.has_silver_profile,
        }


def resolve_monthly_limit(*, monthly_limit: int | None = None) -> int:
    if monthly_limit is not None and monthly_limit > 0:
        return int(monthly_limit)
    raw = os.getenv("MESHFLOW_SILVER_MANUAL_REFRESH_MONTHLY_LIMIT", "").strip()
    if raw:
        try:
            parsed = int(raw)
        except ValueError:
            parsed = 0
        if parsed > 0:
            return parsed
    return DEFAULT_MONTHLY_LIMIT


def current_usage_month(*, now: datetime | None = None) -> str:
    stamped = now or datetime.now(UTC)
    return stamped.strftime("%Y-%m")


def manual_refresh_usage_key(*, client_id: str, month: str) -> str:
    slug = client_id.strip().lower() or "default"
    return f"governance/_usage/manual_silver_refresh/{slug}/{month.strip()}.json"


def load_monthly_usage(
    settings: DnaSettings,
    *,
    client_id: str,
    month: str | None = None,
) -> dict[str, Any]:
    usage_month = month or current_usage_month()
    payload = read_json_artifact(
        settings,
        manual_refresh_usage_key(client_id=client_id, month=usage_month),
    ) or {}
    refreshes = payload.get("refreshes")
    if not isinstance(refreshes, list):
        refreshes = []
    return {
        "client_id": str(payload.get("client_id") or client_id or "").strip(),
        "month": usage_month,
        "count": int(payload.get("count") or len(refreshes)),
        "refreshes": refreshes,
        "updated_at": str(payload.get("updated_at") or ""),
    }


def _describe_execution_status(
    execution_arn: str,
    *,
    describe_fn: Callable[[str], dict[str, Any]] | None = None,
) -> str:
    if not execution_arn.strip():
        return ""
    if describe_fn is not None:
        payload = describe_fn(execution_arn)
        return str(payload.get("status") or "").strip().upper()
    if os.getenv("MESHFLOW_CONNECTOR_REFRESH_MOCK", "").strip().lower() in {"1", "true", "yes"}:
        return "SUCCEEDED"
    import boto3

    client = boto3.client("stepfunctions")
    payload = client.describe_execution(executionArn=execution_arn)
    return str(payload.get("status") or "").strip().upper()


def _last_refresh_in_progress(
    usage: dict[str, Any],
    *,
    describe_fn: Callable[[str], dict[str, Any]] | None = None,
) -> tuple[bool, str]:
    refreshes = usage.get("refreshes")
    if not isinstance(refreshes, list) or not refreshes:
        return False, ""
    last = refreshes[-1]
    if not isinstance(last, dict):
        return False, ""
    execution_arn = str(last.get("execution_arn") or "").strip()
    if not execution_arn:
        return False, ""
    status = _describe_execution_status(execution_arn, describe_fn=describe_fn)
    if status in {"RUNNING", "PENDING_REDRIVE"}:
        return True, execution_arn
    return False, execution_arn


def quota_summary(
    settings: DnaSettings,
    *,
    client_id: str,
    monthly_limit: int | None = None,
    month: str | None = None,
    describe_fn: Callable[[str], dict[str, Any]] | None = None,
) -> SilverManualRefreshQuota:
    limit = resolve_monthly_limit(monthly_limit=monthly_limit)
    usage = load_monthly_usage(settings, client_id=client_id, month=month)
    used = int(usage["count"])
    in_progress, last_execution_arn = _last_refresh_in_progress(
        usage,
        describe_fn=describe_fn,
    )
    remaining = max(0, limit - used)
    at_limit = used >= limit
    return SilverManualRefreshQuota(
        client_id=client_id,
        month=str(usage["month"]),
        used=used,
        monthly_limit=limit,
        remaining=remaining,
        at_limit=at_limit,
        in_progress=in_progress,
        last_execution_arn=last_execution_arn,
    )


def silver_refresh_status(
    settings: DnaSettings,
    *,
    pinned_version: str,
    source: str | None = None,
) -> SilverRefreshStatus:
    src = (source or settings.source).strip().lower()
    pinned = str(pinned_version or "").strip()
    pack = load_sql_pack(settings, version=pinned) if pinned else None
    silver_transforms = pack.by_layer("silver") if pack is not None else []
    has_silver_transforms = bool(silver_transforms)

    profile = load_silver_schema_profile(settings, source=src) or {}
    applied_version = str(profile.get("silver_sql_pack_version") or "").strip()
    consolidated_at = str(
        profile.get("consolidated_at") or profile.get("generated_at") or ""
    ).strip()
    has_silver_profile = bool(profile)

    if not has_silver_transforms:
        is_stale = False
    elif not pinned:
        is_stale = False
    elif not applied_version:
        is_stale = True
    else:
        is_stale = applied_version != pinned

    return SilverRefreshStatus(
        pinned_version=pinned,
        applied_version=applied_version,
        consolidated_at=consolidated_at,
        source=src,
        is_stale=is_stale,
        has_silver_transforms=has_silver_transforms,
        has_silver_profile=has_silver_profile,
    )


def _resolve_state_machine_arn(
    *,
    company: str,
    environment: str,
    source: str,
) -> str:
    explicit = os.getenv("MESHFLOW_CONNECTOR_REFRESH_STATE_MACHINE_ARN", "").strip()
    if explicit:
        return explicit
    from meshflow.process_config import Process, step_function_name_for_process

    name = step_function_name_for_process(company, environment, source, Process.REFRESH)
    region = (
        os.getenv("AWS_REGION")
        or os.getenv("AWS_DEFAULT_REGION")
        or os.getenv("MESHFLOW_AWS_REGION")
        or "us-east-2"
    )
    import boto3

    account = boto3.client("sts").get_caller_identity()["Account"]
    return f"arn:aws:states:{region}:{account}:stateMachine:{name}"


def _sanitize_execution_name(*, client_id: str) -> str:
    slug = _EXECUTION_NAME_RE.sub("-", client_id.strip().lower() or "client")
    suffix = uuid.uuid4().hex[:10]
    name = f"portal-silver-{slug}-{suffix}"
    return name[:80]


def _start_connector_refresh_execution(
    *,
    company: str,
    environment: str,
    source: str,
    client_id: str,
    username: str,
    pinned_version: str,
    start_fn: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    payload = {
        "trigger": "portal_manual",
        "client_id": client_id,
        "username": username,
        "pinned_version": pinned_version,
        "full_load": False,
        "full_rebuild": False,
    }
    if start_fn is not None:
        state_machine_arn = _resolve_state_machine_arn(
            company=company,
            environment=environment,
            source=source,
        )
        execution_name = _sanitize_execution_name(client_id=client_id)
        return start_fn(
            stateMachineArn=state_machine_arn,
            name=execution_name,
            input=json.dumps(payload),
        )

    if os.getenv("MESHFLOW_CONNECTOR_REFRESH_MOCK", "").strip().lower() in {"1", "true", "yes"}:
        return {
            "executionArn": (
                f"arn:aws:states:us-east-2:000000000000:execution:mock-connector-refresh:{uuid.uuid4().hex}"
            ),
            "startDate": datetime.now(UTC),
        }

    state_machine_arn = _resolve_state_machine_arn(
        company=company,
        environment=environment,
        source=source,
    )
    execution_name = _sanitize_execution_name(client_id=client_id)
    import boto3

    client = boto3.client("stepfunctions")
    return client.start_execution(
        stateMachineArn=state_machine_arn,
        name=execution_name,
        input=json.dumps(payload),
    )


def record_manual_refresh(
    settings: DnaSettings,
    *,
    client_id: str,
    username: str,
    pinned_version: str,
    source: str,
    execution_arn: str,
    month: str | None = None,
) -> dict[str, Any]:
    usage_month = month or current_usage_month()
    current = load_monthly_usage(settings, client_id=client_id, month=usage_month)
    refreshes = list(current.get("refreshes") or [])
    refreshes.append(
        {
            "at": datetime.now(UTC).isoformat(),
            "username": username,
            "pinned_version": pinned_version,
            "source": source.strip().lower(),
            "execution_arn": execution_arn,
        }
    )
    payload = {
        "client_id": client_id,
        "month": usage_month,
        "count": len(refreshes),
        "refreshes": refreshes,
        "updated_at": datetime.now(UTC).isoformat(),
    }
    write_json_artifact(
        settings,
        manual_refresh_usage_key(client_id=client_id, month=usage_month),
        payload,
    )
    return payload


def trigger_manual_silver_refresh(
    settings: DnaSettings,
    *,
    client_id: str,
    username: str,
    pinned_version: str,
    company: str,
    environment: str,
    source: str | None = None,
    monthly_limit: int | None = None,
    month: str | None = None,
    start_fn: Callable[..., dict[str, Any]] | None = None,
    describe_fn: Callable[[str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    src = (source or settings.source).strip().lower()
    status = silver_refresh_status(settings, pinned_version=pinned_version, source=src)
    if not status.has_silver_transforms:
        raise ValueError(
            "Pinned DNA has no silver column enhancements. Use gold refresh for new KPI tables."
        )

    quota = quota_summary(
        settings,
        client_id=client_id,
        monthly_limit=monthly_limit,
        month=month,
        describe_fn=describe_fn,
    )
    if quota.in_progress:
        raise SilverManualRefreshInProgress(execution_arn=quota.last_execution_arn)
    if quota.at_limit:
        raise SilverManualRefreshQuotaExceeded(
            monthly_limit=quota.monthly_limit,
            used=quota.used,
        )

    response = _start_connector_refresh_execution(
        company=company,
        environment=environment,
        source=src,
        client_id=client_id,
        username=username,
        pinned_version=pinned_version,
        start_fn=start_fn,
    )
    execution_arn = str(response.get("executionArn") or "").strip()
    if not execution_arn:
        raise RuntimeError("Connector refresh did not return an execution ARN")

    usage = record_manual_refresh(
        settings,
        client_id=client_id,
        username=username,
        pinned_version=pinned_version,
        source=src,
        execution_arn=execution_arn,
        month=month,
    )
    return {
        "execution_arn": execution_arn,
        "source": src,
        "quota": quota_summary(
            settings,
            client_id=client_id,
            monthly_limit=monthly_limit,
            month=month,
            describe_fn=describe_fn,
        ).to_dict(),
        "usage": usage,
    }
