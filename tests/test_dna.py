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
    get_ui_domain_config,
    is_dna_stack_enabled,
    is_ui_domain_enabled,
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


def test_platform_stack_names() -> None:
    from meshflow.project_config import (
        get_platform_environment_config,
        global_dns_stack_name,
        global_ui_stack_name,
        is_platform_ui_enabled,
        reporting_stack_name,
        resolve_reporting_site_url,
    )

    assert global_ui_stack_name("dev") == "GlobalUiStack-dev"
    assert global_dns_stack_name("dev") == "GlobalDnsStack-dev"
    assert reporting_stack_name("poc", "dev") == "ReportingStack-poc-dev"
    from meshflow.project_config import global_ui_web_api_export_name, reporting_web_api_export_name

    assert global_ui_web_api_export_name("dev") == "meshflow-global-ui-dev-web-api-id"
    assert reporting_web_api_export_name("poc", "dev") == "meshflow-reporting-poc-dev-web-api-id"
    platform_env = get_platform_environment_config("dev")
    assert is_platform_ui_enabled(platform_env)
    assert resolve_reporting_site_url(
        {"zone_name": "hive-flow-ai.com"},
        {"reporting_hostname": "poc"},
        "poc",
    ) == "https://poc.hive-flow-ai.com/"


def test_ui_domain_config_from_yaml() -> None:
    full_env = {
        "ui": {
            "domain": {
                "zone_name": "hive-flow-ai.com",
                "primary_hostname": "hive-flow-ai.com",
                "alternate_hostnames": ["www"],
            }
        }
    }
    assert is_ui_domain_enabled(full_env)
    domain_cfg = get_ui_domain_config(full_env)
    assert domain_cfg["zone_name"] == "hive-flow-ai.com"
    assert domain_cfg["alternate_hostnames"] == ["www"]


def test_ui_dns_not_managed_by_default_when_zone_imported() -> None:
    from meshflow.project_config import is_ui_dns_managed, resolve_ui_primary_site_url

    env_config = {
        "ui": {
            "domain": {
                "zone_name": "hive-flow-ai.com",
                "primary_hostname": "hive-flow-ai.com",
                "hosted_zone_id": "Z1234567890ABC",
                "manage_dns": False,
            }
        }
    }
    assert is_ui_dns_managed(env_config) is False
    assert resolve_ui_primary_site_url(env_config) == "https://hive-flow-ai.com/"


def test_ui_dns_managed_only_for_explicit_bootstrap() -> None:
    from meshflow.project_config import is_ui_dns_managed

    assert is_ui_dns_managed({"ui": {"domain": {"manage_dns": True, "zone_name": "hive-flow-ai.com"}}}) is True
    assert is_ui_dns_managed({"ui": {"domain": {"create_hosted_zone": True, "zone_name": "hive-flow-ai.com"}}}) is True
    assert is_ui_dns_managed({"ui": {"domain": {"hosted_zone_id": "Z123", "zone_name": "hive-flow-ai.com"}}}) is False


def test_global_dns_stack_enabled_after_bootstrap() -> None:
    from meshflow.project_config import is_global_dns_stack_enabled, is_ui_dns_managed

    env_config = {
        "ui": {
            "domain": {
                "zone_name": "hive-flow-ai.com",
                "manage_dns": False,
                "hosted_zone_id": "Z0833907O664KG7NO3CQ",
            }
        }
    }
    assert is_ui_dns_managed(env_config) is False
    assert is_global_dns_stack_enabled(env_config) is True


def test_resolve_dna_settings_global_ui_skips_bucket(monkeypatch: pytest.MonkeyPatch) -> None:
    from meshflow.dna.runtime import resolve_dna_settings

    monkeypatch.setenv("MESHFLOW_UI_MODE", "global")
    monkeypatch.setenv("MESHFLOW_ENVIRONMENT", "dev")
    monkeypatch.delenv("MESHFLOW_S3_BUCKET", raising=False)
    monkeypatch.delenv("MESHFLOW_PLATFORM_UI", raising=False)

    settings = resolve_dna_settings()
    assert settings.s3_bucket is None
    assert settings.pack_id == "bc_intra_v1"
