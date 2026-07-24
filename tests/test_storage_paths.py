from meshflow.storage.paths import gold_prefix, raw_source_prefix, silver_source_prefix


def test_raw_source_prefix() -> None:
    assert raw_source_prefix("qbd") == "raw/qbd"


def test_silver_source_prefix() -> None:
    assert silver_source_prefix("qbo") == "silver/qbo"


def test_silver_entity_parquet_key() -> None:
    from meshflow.storage.paths import silver_entity_parquet_key, silver_entity_prefix

    assert silver_entity_prefix("qbd", "customers") == "silver/qbd/customers"
    assert silver_entity_parquet_key("qbd", "customers") == "silver/qbd/customers/data.parquet"
