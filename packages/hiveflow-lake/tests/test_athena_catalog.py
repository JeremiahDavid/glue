from hiveflow.project_config import catalog_table_name, iter_catalog_entities


def test_catalog_table_name() -> None:
    assert catalog_table_name("silver", "qbd", "customers") == "silver_qbd_customers"
    assert catalog_table_name("silver_stg", "dbc", "customers") == "silver_stg_dbc_customers"


def test_raw_table_glue_parameters_use_enum_projection() -> None:
    from hiveflow.catalog.glue_schema import raw_table_glue_parameters

    params = raw_table_glue_parameters(
        bucket="hiveflow-poc-123-us-east-2",
        source="qbd",
        entity="invoices",
        run_ids=["20260101T120000Z", "20260102T120000Z"],
    )
    assert params["projection.run_id.type"] == "enum"
    assert "20260101T120000Z" in params["projection.run_id.values"]


def test_iter_catalog_entities_reads_configured_connectors() -> None:
    connectors = [
        (
            "qbd",
            {"entity_bundle": "v1_accounting"},
        )
    ]
    entities = iter_catalog_entities(connectors)
    names = [entity for _source, entity in entities]
    assert names == ["customers", "invoices", "open_invoices", "payments", "invoice_lines"]
