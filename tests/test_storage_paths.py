from meshflow.storage.paths import gold_prefix, raw_source_prefix, silver_source_prefix


def test_raw_source_prefix() -> None:
    assert raw_source_prefix("qbd") == "raw/qbd"


def test_silver_source_prefix() -> None:
    assert silver_source_prefix("qbo") == "silver/qbo"


def test_gold_prefix() -> None:
    assert gold_prefix() == "gold"
