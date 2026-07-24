from meshflow.project_config import catalog_table_name, iter_catalog_entities


def test_catalog_table_name() -> None:
    assert catalog_table_name("silver", "qbd", "customers") == "silver_qbd_customers"


def test_iter_catalog_entities_reads_configured_connectors() -> None:
    connectors = [
        (
            "qbd",
            {"entity_bundle": "v1_accounting"},
        )
    ]
    entities = iter_catalog_entities(connectors)
    names = [entity for _source, entity in entities]
    assert names == ["customers", "invoices", "open_invoices", "payments"]
