"""Per-client Config Assistant Bedrock token usage and monthly budget."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from hiveflow.compat import UTC
from typing import Any

from hiveflow.dna.settings import DnaSettings
from hiveflow.dna.store import read_json_artifact, write_json_artifact

# Claude Haiku 4.5 on Bedrock (us/global inference profile).
DEFAULT_BEDROCK_INPUT_USD_PER_M = 1.0
DEFAULT_BEDROCK_OUTPUT_USD_PER_M = 5.0
DEFAULT_MONTHLY_BUDGET_USD = 10.0


class BedrockBudgetExceeded(Exception):
    """Raised when a client has exhausted their monthly Config Assist allowance."""

    def __init__(
        self,
        *,
        monthly_budget_usd: float,
        estimated_cost_usd: float,
        input_tokens: int,
        output_tokens: int,
    ) -> None:
        self.monthly_budget_usd = monthly_budget_usd
        self.estimated_cost_usd = estimated_cost_usd
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        super().__init__(
            "Config Assist monthly allowance reached "
            f"(${estimated_cost_usd:.2f} of ${monthly_budget_usd:.2f}). "
            "Try again next month or contact your administrator."
        )


@dataclass(frozen=True)
class BedrockUsageSummary:
    client_id: str
    month: str
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float
    monthly_budget_usd: float
    usage_percent: float
    at_limit: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "client_id": self.client_id,
            "month": self.month,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "estimated_cost_usd": round(self.estimated_cost_usd, 4),
            "monthly_budget_usd": self.monthly_budget_usd,
            "usage_percent": round(self.usage_percent, 1),
            "at_limit": self.at_limit,
        }


def resolve_monthly_budget_usd(*, monthly_budget_usd: float | None = None) -> float:
    if monthly_budget_usd is not None and monthly_budget_usd > 0:
        return float(monthly_budget_usd)
    raw = os.getenv("HIVEFLOW_CONFIG_ASSISTANT_MONTHLY_BUDGET_USD", "").strip()
    if raw:
        try:
            parsed = float(raw)
        except ValueError:
            parsed = 0.0
        if parsed > 0:
            return parsed
    return DEFAULT_MONTHLY_BUDGET_USD


def current_usage_month(*, now: datetime | None = None) -> str:
    stamped = now or datetime.now(UTC)
    return stamped.strftime("%Y-%m")


def bedrock_usage_key(month: str) -> str:
    return f"governance/_usage/bedrock/{month.strip()}.json"


def estimate_cost_usd(
    *,
    input_tokens: int,
    output_tokens: int,
    input_usd_per_m: float = DEFAULT_BEDROCK_INPUT_USD_PER_M,
    output_usd_per_m: float = DEFAULT_BEDROCK_OUTPUT_USD_PER_M,
) -> float:
    return (max(0, input_tokens) / 1_000_000.0) * input_usd_per_m + (
        max(0, output_tokens) / 1_000_000.0
    ) * output_usd_per_m


def load_monthly_usage(
    settings: DnaSettings,
    *,
    month: str | None = None,
    client_id: str = "",
) -> dict[str, Any]:
    usage_month = month or current_usage_month()
    payload = read_json_artifact(settings, bedrock_usage_key(usage_month)) or {}
    return {
        "client_id": str(payload.get("client_id") or client_id or "").strip(),
        "month": usage_month,
        "input_tokens": int(payload.get("input_tokens") or 0),
        "output_tokens": int(payload.get("output_tokens") or 0),
        "updated_at": str(payload.get("updated_at") or ""),
    }


def record_usage(
    settings: DnaSettings,
    *,
    input_tokens: int,
    output_tokens: int,
    client_id: str = "",
    month: str | None = None,
) -> dict[str, Any]:
    if input_tokens <= 0 and output_tokens <= 0:
        return load_monthly_usage(settings, month=month, client_id=client_id)

    usage_month = month or current_usage_month()
    current = load_monthly_usage(settings, month=usage_month, client_id=client_id)
    payload = {
        "client_id": client_id or current.get("client_id") or "",
        "month": usage_month,
        "input_tokens": int(current["input_tokens"]) + max(0, input_tokens),
        "output_tokens": int(current["output_tokens"]) + max(0, output_tokens),
        "updated_at": datetime.now(UTC).isoformat(),
    }
    write_json_artifact(settings, bedrock_usage_key(usage_month), payload)
    return payload


def usage_summary(
    settings: DnaSettings,
    *,
    client_id: str,
    monthly_budget_usd: float | None = None,
    month: str | None = None,
) -> BedrockUsageSummary:
    budget = resolve_monthly_budget_usd(monthly_budget_usd=monthly_budget_usd)
    usage = load_monthly_usage(settings, month=month, client_id=client_id)
    input_tokens = int(usage["input_tokens"])
    output_tokens = int(usage["output_tokens"])
    cost = estimate_cost_usd(input_tokens=input_tokens, output_tokens=output_tokens)
    if budget <= 0:
        percent = 0.0
        at_limit = False
    else:
        percent = min(100.0, (cost / budget) * 100.0)
        at_limit = cost >= budget
    return BedrockUsageSummary(
        client_id=client_id,
        month=str(usage["month"]),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost_usd=cost,
        monthly_budget_usd=budget,
        usage_percent=percent,
        at_limit=at_limit,
    )


def assert_within_budget(
    settings: DnaSettings,
    *,
    client_id: str,
    monthly_budget_usd: float | None = None,
    month: str | None = None,
) -> BedrockUsageSummary:
    summary = usage_summary(
        settings,
        client_id=client_id,
        monthly_budget_usd=monthly_budget_usd,
        month=month,
    )
    if summary.at_limit:
        raise BedrockBudgetExceeded(
            monthly_budget_usd=summary.monthly_budget_usd,
            estimated_cost_usd=summary.estimated_cost_usd,
            input_tokens=summary.input_tokens,
            output_tokens=summary.output_tokens,
        )
    return summary
