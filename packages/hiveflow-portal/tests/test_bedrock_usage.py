from __future__ import annotations

from pathlib import Path

import pytest

from hiveflow.dna.init_client import init_client_governance
from hiveflow.dna.settings import DnaSettings
from hiveflow.dna.web.portal.config import load_client_portal_config
from hiveflow.dna.web.portal.governance_helpers.bedrock_usage import (
    BedrockBudgetExceeded,
    assert_within_budget,
    estimate_cost_usd,
    record_usage,
    usage_summary,
)


@pytest.fixture
def seeded_settings(tmp_path: Path) -> DnaSettings:
    settings = DnaSettings(source="dbc", data_dir=tmp_path, company="POC")
    init_client_governance(settings, company="POC")
    return settings


def test_estimate_cost_usd_haiku_pricing() -> None:
    # $1/M input + $5/M output
    assert estimate_cost_usd(input_tokens=1_000_000, output_tokens=0) == pytest.approx(1.0)
    assert estimate_cost_usd(input_tokens=0, output_tokens=1_000_000) == pytest.approx(5.0)
    assert estimate_cost_usd(input_tokens=1_000_000, output_tokens=1_000_000) == pytest.approx(6.0)


def test_record_usage_accumulates_per_month(seeded_settings: DnaSettings) -> None:
    record_usage(
        seeded_settings,
        input_tokens=1000,
        output_tokens=200,
        client_id="poc",
        month="2026-08",
    )
    record_usage(
        seeded_settings,
        input_tokens=500,
        output_tokens=100,
        client_id="poc",
        month="2026-08",
    )
    summary = usage_summary(
        seeded_settings,
        client_id="poc",
        monthly_budget_usd=10.0,
        month="2026-08",
    )
    assert summary.input_tokens == 1500
    assert summary.output_tokens == 300
    assert summary.estimated_cost_usd == pytest.approx(0.003)
    assert summary.usage_percent == pytest.approx(0.0, abs=0.1)
    assert not summary.at_limit


def test_assert_within_budget_blocks_at_limit(seeded_settings: DnaSettings) -> None:
    record_usage(
        seeded_settings,
        input_tokens=9_000_000,
        output_tokens=200_000,
        client_id="poc",
        month="2026-08",
    )
    summary = usage_summary(
        seeded_settings,
        client_id="poc",
        monthly_budget_usd=10.0,
        month="2026-08",
    )
    assert summary.at_limit
    with pytest.raises(BedrockBudgetExceeded, match="allowance reached"):
        assert_within_budget(
            seeded_settings,
            client_id="poc",
            monthly_budget_usd=10.0,
            month="2026-08",
        )


def test_load_client_portal_config_reads_assistant_budget() -> None:
    env_config = {
        "ui": {
            "portal": {
                "default_max_users": 10,
                "config_assistant": {"monthly_budget_usd": 10},
                "clients": {
                    "poc": {
                        "display_name": "POC",
                        "reporting_company": "poc",
                        "config_assistant": {"monthly_budget_usd": 25},
                    }
                },
            }
        }
    }
    client = load_client_portal_config("poc", env_config, default_pack_id="poc_dna_config")
    assert client.config_assistant_monthly_budget_usd == 25.0
