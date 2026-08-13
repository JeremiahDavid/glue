from __future__ import annotations

from pathlib import Path

import pytest

from meshflow.dna.init_client import init_client_governance
from meshflow.dna.settings import DnaSettings
from meshflow.dna.store import write_json_artifact, write_yaml_artifact
from meshflow.dna.web.portal.config import load_client_portal_config
from meshflow.dna.web.portal.kpi_generator.render import silver_refresh_status_html
from meshflow.dna.web.portal.silver_manual_refresh import (
    SilverManualRefreshInProgress,
    SilverManualRefreshQuotaExceeded,
    quota_summary,
    record_manual_refresh,
    silver_refresh_status,
    trigger_manual_silver_refresh,
)
from meshflow.storage.paths import governance_source_semantic_latest_profile_key


@pytest.fixture
def seeded_settings(tmp_path: Path) -> DnaSettings:
    settings = DnaSettings(source="dbc", data_dir=tmp_path, company="POC")
    init_client_governance(settings, company="POC")
    return settings


_VALID_SHA = "a" * 64


def _write_silver_manifest(settings: DnaSettings, version: str) -> None:
    write_yaml_artifact(
        settings,
        f"governance/poc_dna_config/v{version}/sql/manifest.yaml",
        {
            "version": version,
            "transforms": [
                {
                    "id": "enhance__customers",
                    "layer": "silver",
                    "mode": "add_columns",
                    "file": "silver/enhance__customers.sql",
                    "sha256": _VALID_SHA,
                    "target_entity": "customers",
                }
            ],
        },
    )


def test_silver_refresh_status_stale_when_versions_differ(seeded_settings: DnaSettings) -> None:
    _write_silver_manifest(seeded_settings, "1.0.1")
    write_yaml_artifact(
        seeded_settings,
        governance_source_semantic_latest_profile_key("dbc"),
        {
            "silver_sql_pack_version": "1.0.0",
            "consolidated_at": "2026-08-01T12:00:00+00:00",
            "tables": [],
        },
    )

    status = silver_refresh_status(seeded_settings, pinned_version="1.0.1")
    assert status.is_stale is True
    assert status.applied_version == "1.0.0"
    assert status.has_silver_transforms is True


def test_silver_refresh_status_current_when_versions_match(seeded_settings: DnaSettings) -> None:
    _write_silver_manifest(seeded_settings, "1.0.0")
    write_yaml_artifact(
        seeded_settings,
        governance_source_semantic_latest_profile_key("dbc"),
        {
            "silver_sql_pack_version": "1.0.0",
            "consolidated_at": "2026-08-01T12:00:00+00:00",
            "tables": [],
        },
    )

    status = silver_refresh_status(seeded_settings, pinned_version="1.0.0")
    assert status.is_stale is False


def test_silver_refresh_status_no_transforms(seeded_settings: DnaSettings) -> None:
    status = silver_refresh_status(seeded_settings, pinned_version="1.0.0")
    assert status.has_silver_transforms is False
    assert status.is_stale is False


def test_quota_summary_tracks_monthly_usage(seeded_settings: DnaSettings) -> None:
    record_manual_refresh(
        seeded_settings,
        client_id="poc",
        username="admin@test.com",
        pinned_version="1.0.0",
        source="dbc",
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


def test_trigger_manual_silver_refresh_records_usage_and_invokes_sfn(
    seeded_settings: DnaSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_silver_manifest(seeded_settings, "1.0.1")
    monkeypatch.setenv("MESHFLOW_CONNECTOR_REFRESH_MOCK", "1")
    calls: list[dict[str, object]] = []

    def fake_start(**kwargs: object) -> dict[str, object]:
        calls.append(kwargs)
        return {"executionArn": "arn:aws:states:us-east-2:123:execution:test:manual"}

    result = trigger_manual_silver_refresh(
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
    assert result["source"] == "dbc"
    assert calls
    payload = calls[0]["input"]
    assert '"full_rebuild": false' in str(payload).lower()
    summary = quota_summary(
        seeded_settings,
        client_id="poc",
        monthly_limit=10,
        month="2026-08",
        describe_fn=lambda _arn: {"status": "SUCCEEDED"},
    )
    assert summary.used == 1
    assert summary.remaining == 9


def test_trigger_manual_silver_refresh_blocks_without_silver_sql(seeded_settings: DnaSettings) -> None:
    with pytest.raises(ValueError, match="no silver column enhancements"):
        trigger_manual_silver_refresh(
            seeded_settings,
            client_id="poc",
            username="admin@test.com",
            pinned_version="1.0.0",
            company="POC",
            environment="dev",
            monthly_limit=10,
            month="2026-08",
            start_fn=lambda **_kwargs: {"executionArn": "arn:unused"},
            describe_fn=lambda _arn: {"status": "SUCCEEDED"},
        )


def test_trigger_manual_silver_refresh_blocks_at_limit(seeded_settings: DnaSettings) -> None:
    _write_silver_manifest(seeded_settings, "1.0.0")
    for idx in range(2):
        record_manual_refresh(
            seeded_settings,
            client_id="poc",
            username="admin@test.com",
            pinned_version="1.0.0",
            source="dbc",
            execution_arn=f"arn:aws:states:us-east-2:123:execution:test:{idx}",
            month="2026-08",
        )

    with pytest.raises(SilverManualRefreshQuotaExceeded, match="limit reached"):
        trigger_manual_silver_refresh(
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


def test_trigger_manual_silver_refresh_blocks_when_running(seeded_settings: DnaSettings) -> None:
    _write_silver_manifest(seeded_settings, "1.0.0")
    record_manual_refresh(
        seeded_settings,
        client_id="poc",
        username="admin@test.com",
        pinned_version="1.0.0",
        source="dbc",
        execution_arn="arn:aws:states:us-east-2:123:execution:test:running",
        month="2026-08",
    )

    with pytest.raises(SilverManualRefreshInProgress, match="already in progress"):
        trigger_manual_silver_refresh(
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


def test_load_client_portal_config_reads_silver_manual_refresh_limit() -> None:
    env_config = {
        "ui": {
            "portal": {
                "clients": {
                    "poc": {
                        "display_name": "POC",
                        "reporting_company": "POC",
                        "silver_manual_refresh": {"monthly_limit": 5},
                    }
                }
            }
        }
    }
    client = load_client_portal_config("poc", env_config, default_pack_id="poc_dna_config")
    assert client.silver_manual_refresh_monthly_limit == 5


def test_silver_refresh_status_html_shows_remaining_quota() -> None:
    html = silver_refresh_status_html(
        form_path="/portal/dna/kpi-generator",
        refresh_status={
            "pinned_version": "1.0.1",
            "applied_version": "1.0.0",
            "consolidated_at": "2026-08-01T12:00:00+00:00",
            "source": "dbc",
            "is_stale": True,
            "has_silver_transforms": True,
            "has_silver_profile": True,
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
    assert 'value="manual_silver_refresh"' in html
    assert "Refresh silver tables" in html
