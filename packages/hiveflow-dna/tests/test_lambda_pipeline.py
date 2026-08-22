"""Tests for DNA publish pipeline without semantic-init."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from hiveflow.dna.init_client import init_client_governance
from hiveflow.dna.lambda_handler import run_dna_pipeline
from hiveflow.dna.settings import DnaSettings


@pytest.fixture
def seeded_settings(tmp_path: Path) -> DnaSettings:
    settings = DnaSettings(source="dbc", data_dir=tmp_path, company="POC")
    init_client_governance(settings, company="POC")
    return settings


def test_run_dna_pipeline_athena_sql_path(seeded_settings: DnaSettings) -> None:
    with (
        patch("hiveflow.dna.sql_runtime.has_gold_sql", return_value=True),
        patch(
            "hiveflow.dna.sql_runtime.apply_gold_sql_pack",
            return_value={"status": "applied", "tables": []},
        ) as apply_gold,
    ):
        result = run_dna_pipeline(seeded_settings)
    assert result["status"] == "published"
    assert result["mode"] == "athena_sql"
    assert "semantic_model_gate" not in result
    assert "semantic_init" not in result
    apply_gold.assert_called_once()


def test_handler_rejects_semantic_init_action(seeded_settings: DnaSettings, monkeypatch: pytest.MonkeyPatch) -> None:
    from hiveflow.dna.lambda_handler import handler

    monkeypatch.setattr(
        "hiveflow.dna.runtime.resolve_dna_settings",
        lambda event=None: seeded_settings,
    )
    with pytest.raises(ValueError, match="Unknown DNA action"):
        handler({"action": "semantic-init-auto", "company": "POC", "source": "dbc"}, None)
