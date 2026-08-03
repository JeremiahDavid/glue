"""Tests for portal invite email (SES) configuration helpers."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

INFRA_DIR = Path(__file__).resolve().parents[1] / "infra"
sys.path.insert(0, str(INFRA_DIR))

from portal_email import resolve_portal_email_settings


def test_resolve_portal_email_settings_disabled_by_default() -> None:
    assert resolve_portal_email_settings({"portal": {}}) is None


def test_resolve_portal_email_settings_when_enabled() -> None:
    settings = resolve_portal_email_settings(
        {
            "portal": {
                "email": {
                    "enabled": True,
                    "from_address": "noreply@hive-flow-ai.com",
                    "from_name": "HiveFlowAI",
                }
            },
            "domain": {
                "zone_name": "hive-flow-ai.com",
                "hosted_zone_id": "Z0833907O664KG7NO3CQ",
            },
        }
    )
    assert settings == {
        "zone_name": "hive-flow-ai.com",
        "hosted_zone_id": "Z0833907O664KG7NO3CQ",
        "from_address": "noreply@hive-flow-ai.com",
        "from_name": "HiveFlowAI",
    }


def test_resolve_portal_email_settings_requires_hosted_zone() -> None:
    with pytest.raises(ValueError, match="hosted_zone_id"):
        resolve_portal_email_settings(
            {
                "portal": {"email": {"enabled": True}},
                "domain": {"zone_name": "hive-flow-ai.com"},
            }
        )


def test_resolve_portal_email_settings_rejects_mismatched_from_domain() -> None:
    with pytest.raises(ValueError, match="must match zone_name"):
        resolve_portal_email_settings(
            {
                "portal": {"email": {"enabled": True, "from_address": "noreply@example.com"}},
                "domain": {
                    "zone_name": "hive-flow-ai.com",
                    "hosted_zone_id": "Z0833907O664KG7NO3CQ",
                },
            }
        )
