from meshflow.storage.paths import (
    gold_dna_entity_prefix,
    gold_dna_prefix,
    gold_dna_staging_prefix,
    gold_prefix,
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
