"""Tests for connector secret name resolution."""

from __future__ import annotations

from pathlib import Path

import yaml

from meshflow.project_config import resolve_qbo_secret_name


def test_resolve_qbo_secret_name_uses_dna_source_with_multiple_connectors(
    tmp_path: Path,
) -> None:
    config = {
        "default": {"company": "POC", "environment": "dev"},
        "companies": {
            "POC": {
                "environments": {
                    "dev": {
                        "qbo": {"tier": "sandbox"},
                        "qbd": {"entity_bundle": "full_accounting"},
                        "dbc": {"entity_bundle": "full"},
                        "dna": {"enabled": True, "source": "dbc"},
                    }
                }
            }
        },
    }
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")

    secret_name = resolve_qbo_secret_name(path=config_path)

    assert secret_name == "meshflow-poc-dbc-dev"
