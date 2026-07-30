from meshflow.bc.entities import (
    ENTITY_BUNDLE_SPECS,
    list_entity_bundles,
    resolve_bc_entities_from_ingest_config,
)
from meshflow.project_config import catalog_table_name, iter_catalog_entities


def test_bc_v1_intra_bundle_entities() -> None:
    bundle, specs = resolve_bc_entities_from_ingest_config({"entity_bundle": "v1_intra"})
    assert bundle == "v1_intra"
    names = [spec.output_name for spec in specs]
    assert names == [
        "customers",
        "items",
        "sales_orders",
        "sales_shipments",
        "sales_invoices",
        "customer_payments",
    ]


def test_bc_full_bundle_covers_standard_api_entities() -> None:
    bundle, specs = resolve_bc_entities_from_ingest_config({"entity_bundle": "full"})
    assert bundle == "full"
    names = {spec.output_name for spec in specs}
    assert len(names) == len(specs)
    assert len(specs) >= 70
    assert {
        "customers",
        "vendors",
        "items",
        "sales_orders",
        "sales_invoices",
        "purchase_orders",
        "general_ledger_entries",
        "item_ledger_entries",
        "accounts",
        "projects",
    } <= names


def test_bc_full_bundle_expands_document_lines() -> None:
    _, specs = resolve_bc_entities_from_ingest_config({"entity_bundle": "full"})
    by_name = {spec.output_name: spec for spec in specs}
    assert by_name["sales_invoices"].expand == "salesInvoiceLines"
    assert by_name["purchase_orders"].expand == "purchaseOrderLines"


def test_bc_custom_entity_override() -> None:
    bundle, specs = resolve_bc_entities_from_ingest_config(
        {"entities": {"customers": "customers", "sales_invoices": "salesInvoices"}}
    )
    assert bundle == "custom"
    assert [spec.output_name for spec in specs] == ["customers", "sales_invoices"]


def test_iter_catalog_entities_includes_bc() -> None:
    connectors = [("bc", {"entity_bundle": "v1_accounting"})]
    entities = iter_catalog_entities(connectors)
    names = [entity for _source, entity in entities]
    assert "sales_invoices" in names
    assert "open_sales_invoices" in names
    assert catalog_table_name("silver", "bc", "sales_orders") == "silver_bc_sales_orders"


def test_iter_catalog_entities_includes_full_dbc_bundle() -> None:
    connectors = [("dbc", {"entity_bundle": "full"})]
    entities = iter_catalog_entities(connectors)
    names = {entity for _source, entity in entities}
    assert "item_ledger_entries" in names
    assert "general_ledger_entries" in names
    assert len(names) == len(ENTITY_BUNDLE_SPECS["full"])


def test_bc_entity_bundles_are_listed() -> None:
    assert "v1_intra" in list_entity_bundles()
    assert "full" in list_entity_bundles()
