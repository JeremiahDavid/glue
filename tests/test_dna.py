from __future__ import annotations

from pathlib import Path

import pytest

from meshflow.dna.compile import compile_pack
from meshflow.dna.ingest_docs import draft_pack_from_documents
from meshflow.dna.schema import load_definition_pack_file, starter_pack_path
from meshflow.dna.settings import DnaSettings
from meshflow.dna.validate import run_validation
from meshflow.dna.workflow import promote_pack
from meshflow.project_config import (
    dna_catalog_table_name,
    dna_stack_name,
    get_dna_config,
    get_ui_config,
    is_dna_stack_enabled,
    is_ui_stack_enabled,
    iter_dna_catalog_outputs,
    resolve_dna_source,
    ui_stack_name,
)
from meshflow.storage.paths import gold_dna_entity_parquet_key, gold_dna_prefix


def test_starter_pack_loads() -> None:
    pack = load_definition_pack_file(starter_pack_path())
    assert pack.pack_id == "bc_intra_v1"
    assert pack.is_publishable()
    assert len(pack.kpis) >= 5


def test_draft_pack_from_customer_docs() -> None:
    text = """
## KPI: Net revenue by customer

**Definition:** Sum of invoice line amounts by customer for the period.
**Formula:** sum(amount)
"""
    pack = draft_pack_from_documents(
        pack_id="acme_bc",
        source_system="dbc",
        document_texts=[text],
    )
    assert pack.approval.status == "draft"
    assert pack.kpis[0].name == "Net revenue by customer"


def test_compile_validate_empty_silver(tmp_path: Path) -> None:
    settings = DnaSettings(source="dbc", data_dir=tmp_path, pack_id="bc_intra_v1")
    pack = load_definition_pack_file(starter_pack_path())
    manifest = compile_pack(settings, pack)
    assert manifest["status"] == "compiled"
    assert manifest["pack_id"] == "bc_intra_v1"

    validation = run_validation(settings, pack)
    assert validation["status"] == "passed"


def test_promote_workflow(tmp_path: Path) -> None:
    settings = DnaSettings(source="dbc", data_dir=tmp_path, pack_id="test_pack")
    pack = draft_pack_from_documents(
        pack_id="test_pack",
        source_system="dbc",
        document_texts=["## KPI: Test\n**Definition:** count rows"],
    )
    result = promote_pack(settings, pack, target_status="validated", approver="Controller")
    assert result["status"] == "validated"
    assert pack.is_publishable()


def test_dna_catalog_table_naming() -> None:
    assert dna_catalog_table_name("out_fact_revenue_lines") == "dna_out_fact_revenue_lines"
    assert "out_kpi_snapshot" in iter_dna_catalog_outputs()


def test_gold_dna_paths() -> None:
    assert gold_dna_prefix() == "gold/dna"
    assert gold_dna_entity_parquet_key("out_kpi_snapshot") == "gold/dna/out_kpi_snapshot/data.parquet"


def test_dna_stack_gating_from_config() -> None:
    assert is_dna_stack_enabled({"dna": {"enabled": True}})
    assert not is_dna_stack_enabled({"dna": {"enabled": False}})
    assert not is_dna_stack_enabled({})
    assert dna_stack_name("POC", "dev") == "DnaStack-POC-dev"
    assert resolve_dna_source({"dbc": {}, "dna": {}}) == "dbc"


def test_ui_stack_gating_from_config() -> None:
    enabled_env = {"dna": {"enabled": True}, "ui": {"enabled": True}}
    assert is_ui_stack_enabled(enabled_env)
    assert not is_ui_stack_enabled({"dna": {"enabled": True}, "ui": {"enabled": False}})
    assert not is_ui_stack_enabled({"dna": {"enabled": False}, "ui": {"enabled": True}})
    assert ui_stack_name("POC", "dev") == "UiStack-POC-dev"
    assert get_ui_config(enabled_env)["enabled"] is True
