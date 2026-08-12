"""Athena helper tests."""

from __future__ import annotations

from meshflow.athena import normalize_athena_catalog_refs


def test_normalize_athena_catalog_refs_rewrites_silver_database_prefix() -> None:
    sql = "SELECT SUM(amount) FROM silver.sales_invoice_lines"
    normalized = normalize_athena_catalog_refs(
        sql,
        source="dbc",
        database="meshflow_poc_dev",
    )
    assert normalized == "SELECT SUM(amount) FROM silver_dbc_sales_invoice_lines"


def test_normalize_athena_catalog_refs_rewrites_gold_output_prefix() -> None:
    sql = "SELECT revenue_ytd FROM gold.out_executive_kpis"
    normalized = normalize_athena_catalog_refs(sql, source="dbc")
    assert normalized == "SELECT revenue_ytd FROM dna_out_executive_kpis"


def test_normalize_athena_catalog_refs_strips_meshflow_database_prefix() -> None:
    sql = "SELECT 1 FROM meshflow_poc_dev.silver_dbc_sales_orders"
    normalized = normalize_athena_catalog_refs(
        sql,
        source="dbc",
        database="meshflow_poc_dev",
    )
    assert normalized == "SELECT 1 FROM silver_dbc_sales_orders"
