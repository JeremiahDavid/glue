from __future__ import annotations

from pathlib import Path

import pytest

from meshflow.dna.init_client import init_client_governance
from meshflow.dna.settings import DnaSettings
from meshflow.dna.store import write_json_artifact, write_yaml_artifact
from meshflow.dna.web.portal.config import load_client_portal_config
from meshflow.dna.web.portal.dna_manual_refresh import (
    ManualRefreshInProgress,
    ManualRefreshQuotaExceeded,
    gold_refresh_status,
    quota_summary,
    record_manual_refresh,
    trigger_manual_refresh,
)
from meshflow.dna.web.portal.kpi_generator.render import dna_refresh_status_html


@pytest.fixture
def seeded_settings(tmp_path: Path) -> DnaSettings:
    settings = DnaSettings(source="dbc", data_dir=tmp_path, company="POC")
    init_client_governance(settings, company="POC")
    return settings


def test_gold_refresh_status_stale_when_versions_differ(seeded_settings: DnaSettings) -> None:
    write_json_artifact(
        seeded_settings,
        f"{seeded_settings.gold_dna_prefix}/manifest.json",
        {
            "pack_version": "1.0.0",
            "published_at": "2026-08-01T12:00:00+00:00",
            "outputs": [],
        },
    )

    status = gold_refresh_status(seeded_settings, pinned_version="1.0.1")
    assert status.is_stale is True
    assert status.published_version == "1.0.0"
    assert status.pinned_version == "1.0.1"


def test_gold_refresh_status_current_when_versions_match(seeded_settings: DnaSettings) -> None:
    write_json_artifact(
        seeded_settings,
        f"{seeded_settings.gold_dna_prefix}/manifest.json",
        {
            "pack_version": "1.0.0",
            "published_at": "2026-08-01T12:00:00+00:00",
            "outputs": [],
        },
    )

    status = gold_refresh_status(seeded_settings, pinned_version="1.0.0")
    assert status.is_stale is False


def test_gold_refresh_status_stale_when_silver_pack_version_differs(
    seeded_settings: DnaSettings,
) -> None:
    write_yaml_artifact(
        seeded_settings,
        "governance/poc_dna_config/v1.0.1/sql/manifest.yaml",
        {
            "version": "1.0.1",
            "transforms": [
                {
                    "id": "enhance__customers",
                    "layer": "silver",
                    "mode": "add_columns",
                    "file": "silver/enhance__customers.sql",
                    "sha256": "a" * 64,
                    "target_entity": "customers",
                }
            ],
        },
    )
    write_json_artifact(
        seeded_settings,
        f"{seeded_settings.gold_dna_prefix}/manifest.json",
        {
            "pack_version": "1.0.1",
            "silver_sql_pack_version": "1.0.0",
            "published_at": "2026-08-01T12:00:00+00:00",
            "outputs": [],
        },
    )

    status = gold_refresh_status(seeded_settings, pinned_version="1.0.1")
    assert status.is_stale is True
    assert status.has_silver_transforms is True
    assert status.silver_applied_version == "1.0.0"
    assert status.published_version == "1.0.1"


def test_quota_summary_tracks_monthly_usage(seeded_settings: DnaSettings) -> None:
    record_manual_refresh(
        seeded_settings,
        client_id="poc",
        username="admin@test.com",
        pinned_version="1.0.0",
        execution_arn="arn:aws:states:us-east-2:123:execution:test:one",
        month="2026-08",
    )

    summary = quota_summary(
        seeded_settings,
        client_id="poc",
        monthly_limit=10,
        month="2026-08",
        describe_fn=lambda _arn: {"status": "SUCCEEDED"},
    )
    assert summary.used == 1
    assert summary.remaining == 9
    assert summary.at_limit is False


def test_quota_summary_survives_describe_access_denied(
    seeded_settings: DnaSettings,
) -> None:
    record_manual_refresh(
        seeded_settings,
        client_id="poc",
        username="admin@test.com",
        pinned_version="1.0.0",
        execution_arn=(
            "arn:aws:states:us-east-2:123:execution:"
            "poc-dev-all-gold-dna-refresh:portal-poc-stale"
        ),
        month="2026-08",
    )

    def denied(_arn: str) -> dict[str, str]:
        raise PermissionError(
            "User is not authorized to perform: states:DescribeExecution"
        )

    summary = quota_summary(
        seeded_settings,
        client_id="poc",
        monthly_limit=10,
        month="2026-08",
        describe_fn=denied,
    )
    assert summary.used == 1
    assert summary.in_progress is False
    assert summary.last_execution_arn.endswith(":portal-poc-stale")


def test_trigger_manual_refresh_records_usage_and_invokes_sfn(
    seeded_settings: DnaSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MESHFLOW_DNA_REFRESH_MOCK", "1")
    calls: list[dict[str, object]] = []

    def fake_start(**kwargs: object) -> dict[str, object]:
        calls.append(kwargs)
        return {"executionArn": "arn:aws:states:us-east-2:123:execution:test:manual"}

    result = trigger_manual_refresh(
        seeded_settings,
        client_id="poc",
        username="admin@test.com",
        pinned_version="1.0.1",
        company="POC",
        environment="dev",
        monthly_limit=10,
        month="2026-08",
        start_fn=fake_start,
        describe_fn=lambda _arn: {"status": "SUCCEEDED"},
    )
    assert result["execution_arn"].endswith(":manual")
    assert calls
    summary = quota_summary(
        seeded_settings,
        client_id="poc",
        monthly_limit=10,
        month="2026-08",
        describe_fn=lambda _arn: {"status": "SUCCEEDED"},
    )
    assert summary.used == 1
    assert summary.remaining == 9


def test_trigger_manual_refresh_blocks_at_limit(seeded_settings: DnaSettings) -> None:
    for idx in range(2):
        record_manual_refresh(
            seeded_settings,
            client_id="poc",
            username="admin@test.com",
            pinned_version="1.0.0",
            execution_arn=f"arn:aws:states:us-east-2:123:execution:test:{idx}",
            month="2026-08",
        )

    with pytest.raises(ManualRefreshQuotaExceeded, match="limit reached"):
        trigger_manual_refresh(
            seeded_settings,
            client_id="poc",
            username="admin@test.com",
            pinned_version="1.0.0",
            company="POC",
            environment="dev",
            monthly_limit=2,
            month="2026-08",
            start_fn=lambda **_kwargs: {"executionArn": "arn:unused"},
            describe_fn=lambda _arn: {"status": "SUCCEEDED"},
        )


def test_trigger_manual_refresh_blocks_when_running(seeded_settings: DnaSettings) -> None:
    record_manual_refresh(
        seeded_settings,
        client_id="poc",
        username="admin@test.com",
        pinned_version="1.0.0",
        execution_arn="arn:aws:states:us-east-2:123:execution:test:running",
        month="2026-08",
    )

    with pytest.raises(ManualRefreshInProgress, match="already in progress"):
        trigger_manual_refresh(
            seeded_settings,
            client_id="poc",
            username="admin@test.com",
            pinned_version="1.0.0",
            company="POC",
            environment="dev",
            monthly_limit=10,
            month="2026-08",
            start_fn=lambda **_kwargs: {"executionArn": "arn:unused"},
            describe_fn=lambda _arn: {"status": "RUNNING"},
        )


def test_load_client_portal_config_reads_manual_refresh_limit() -> None:
    env_config = {
        "ui": {
            "portal": {
                "clients": {
                    "poc": {
                        "display_name": "POC",
                        "reporting_company": "poc",
                        "dna_manual_refresh": {"monthly_limit": 7},
                    }
                }
            }
        }
    }
    client = load_client_portal_config("poc", env_config, default_pack_id="poc_dna_config")
    assert client.dna_manual_refresh_monthly_limit == 7


def test_dna_refresh_status_html_shows_remaining_quota() -> None:
    html = dna_refresh_status_html(
        form_path="/portal/dna/kpi-generator",
        refresh_status={
            "pinned_version": "1.0.1",
            "published_version": "1.0.0",
            "published_at": "2026-08-01T12:00:00+00:00",
            "is_stale": True,
            "has_gold_manifest": True,
        },
        quota={
            "month": "2026-08",
            "remaining": 8,
            "monthly_limit": 10,
            "used": 2,
            "at_limit": False,
            "in_progress": False,
        },
    )
    assert "Refresh needed" in html
    assert "Manual refreshes remaining" in html
    assert "<strong>8</strong>" in html
    assert 'value="manual_dna_refresh"' in html
    assert "Refresh DNA tables" in html
