from meshflow.storage.paths import (
    gold_dna_entity_prefix,
    gold_dna_prefix,
    gold_dna_staging_prefix,
    gold_prefix,
    governance_dna_key,
    governance_docs_prefix,
    governance_field_semantics_draft_key,
    governance_field_semantics_key,
    governance_field_semantics_manifest_key,
    governance_field_semantics_prefix,
    governance_field_semantics_workflow_key,
    governance_manifest_key,
    governance_pack_prefix,
    governance_prefix,
    governance_reporting_key,
    governance_version_prefix,
    governance_workflow_key,
    raw_source_prefix,
    silver_source_prefix,
)


def test_raw_source_prefix() -> None:
    assert raw_source_prefix("qbd") == "raw/qbd"


def test_silver_source_prefix() -> None:
    assert silver_source_prefix("qbo") == "silver/qbo"


def test_silver_entity_parquet_key() -> None:
    from meshflow.storage.paths import silver_entity_parquet_key, silver_entity_prefix

    assert silver_entity_prefix("qbd", "customers") == "silver/qbd/customers"
    assert silver_entity_parquet_key("qbd", "customers") == "silver/qbd/customers/data.parquet"


def test_gold_prefix() -> None:
    assert gold_prefix() == "gold"


def test_gold_dna_paths() -> None:
    assert gold_dna_prefix() == "gold/dna"
    assert gold_dna_staging_prefix() == "gold/dna/_staging"
    assert gold_dna_entity_prefix("out_kpi_snapshot") == "gold/dna/out_kpi_snapshot"


def test_governance_paths() -> None:
    from meshflow.storage.paths import company_dna_config_id, company_reporting_config_id

    assert company_dna_config_id("POC") == "poc_dna_config"
    assert company_reporting_config_id("POC") == "poc_reporting_config"
    assert governance_prefix() == "governance"
    assert governance_pack_prefix("poc_dna_config") == "governance/poc_dna_config"
    assert (
        governance_version_prefix("poc_dna_config", "1.0.0")
        == "governance/poc_dna_config/v1.0.0"
    )
    assert governance_workflow_key("poc_dna_config") == "governance/poc_dna_config/workflow.json"
    assert (
        governance_dna_key("poc_dna_config", "1.0.0")
        == "governance/poc_dna_config/v1.0.0/poc_dna_config.yaml"
    )
    assert (
        governance_reporting_key("poc_dna_config", "1.0.0", company="POC")
        == "governance/poc_dna_config/v1.0.0/poc_reporting_config.yaml"
    )
    assert (
        governance_reporting_key("poc_dna_config", "1.0.0")
        == "governance/poc_dna_config/v1.0.0/poc_reporting_config.yaml"
    )
    assert (
        governance_reporting_key("test_pack", "0.1.0")
        == "governance/test_pack/v0.1.0/reporting.yaml"
    )
    assert governance_docs_prefix("poc_dna_config", "1.0.0") == "governance/poc_dna_config/v1.0.0/docs"
    assert (
        governance_manifest_key("poc_dna_config", "1.0.0")
        == "governance/poc_dna_config/v1.0.0/manifest.json"
    )
    assert (
        governance_field_semantics_prefix("poc_dna_config")
        == "governance/poc_dna_config/field_semantics"
    )
    assert (
        governance_field_semantics_draft_key("poc_dna_config")
        == "governance/poc_dna_config/field_semantics/draft.yaml"
    )
    assert (
        governance_field_semantics_workflow_key("poc_dna_config")
        == "governance/poc_dna_config/field_semantics/workflow.json"
    )
    assert (
        governance_field_semantics_key("poc_dna_config", "1.0.0")
        == "governance/poc_dna_config/field_semantics/v1.0.0/field_semantics.yaml"
    )
    assert (
        governance_field_semantics_manifest_key("poc_dna_config", "1.0.0")
        == "governance/poc_dna_config/field_semantics/v1.0.0/manifest.json"
    )
    from meshflow.storage.paths import (
        governance_semantic_model_draft_key,
        governance_semantic_model_key,
        governance_semantic_model_prefix,
    )

    assert (
        governance_semantic_model_prefix("poc_dna_config")
        == "governance/poc_dna_config/semantic_model"
    )
    assert (
        governance_semantic_model_draft_key("poc_dna_config")
        == "governance/poc_dna_config/semantic_model/draft.yaml"
    )
    assert (
        governance_semantic_model_key("poc_dna_config", "0.1.0")
        == "governance/poc_dna_config/semantic_model/v0.1.0/semantic_model.yaml"
    )
