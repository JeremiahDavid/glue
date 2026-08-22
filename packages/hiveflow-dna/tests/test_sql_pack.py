"""Tests for Athena SQL pack parsing and checksums."""

from __future__ import annotations

import pytest

from meshflow.dna.sql_pack import (
    build_sql_pack,
    extract_silver_entities_from_sql,
    ordered_transforms,
    parse_sql_manifest,
    sha256_text,
    silver_entities_for_sql_pack,
)
from meshflow.athena import inject_validation_filters


def test_parse_silver_and_gold_transforms() -> None:
    sql = "SELECT *, quantity * unit_cost AS grossProfit FROM silver_dbc_sales_invoice_lines"
    digest = sha256_text(sql)
    pack = parse_sql_manifest(
        {
            "version": "1.2.3",
            "transforms": [
                {
                    "id": "enhance__sales_invoice_lines",
                    "layer": "silver",
                    "mode": "add_columns",
                    "file": "silver/enhance__sales_invoice_lines.sql",
                    "sha256": digest,
                    "target_entity": "sales_invoice_lines",
                },
                {
                    "id": "kpi_rev",
                    "layer": "gold",
                    "mode": "kpi",
                    "file": "gold/kpi_rev.sql",
                    "sha256": digest,
                    "output_id": "out_kpi_snapshot",
                    "grain_columns": ["customerId"],
                    "depends_on": ["enhance__sales_invoice_lines"],
                },
            ],
        }
    )
    assert pack is not None
    assert len(pack.by_layer("silver")) == 1
    assert len(pack.by_layer("gold")) == 1
    ordered = ordered_transforms(pack.transforms)
    assert [t.id for t in ordered] == ["enhance__sales_invoice_lines", "kpi_rev"]


def test_silver_rejects_gold_mode() -> None:
    digest = sha256_text("SELECT 1")
    with pytest.raises(ValueError, match="silver mode"):
        parse_sql_manifest(
            {
                "version": "1.0.0",
                "transforms": [
                    {
                        "id": "bad",
                        "layer": "silver",
                        "mode": "kpi",
                        "file": "silver/bad.sql",
                        "sha256": digest,
                        "target_entity": "customers",
                    }
                ],
            }
        )


def test_build_sql_pack_fills_checksum() -> None:
    body = "SELECT 1 AS value"
    pack, files = build_sql_pack(
        version="1.0.1",
        transforms=[
            {
                "id": "kpi_one",
                "layer": "gold",
                "mode": "kpi",
                "file": "gold/kpi_one.sql",
                "output_id": "out_kpi_one",
                "grain_columns": [],
            }
        ],
        sql_by_file={"gold/kpi_one.sql": body},
    )
    assert pack.transforms[0].sha256 == sha256_text(body)
    assert files["gold/kpi_one.sql"] == body


def test_inject_validation_filters_is_session_wrapper() -> None:
    sql = "SELECT id, amount FROM silver_dbc_sales_invoices"
    wrapped = inject_validation_filters(
        sql,
        [{"field": "id", "value": "INV-1"}, {"field": "customerId", "value": "C1"}],
    )
    assert "SELECT * FROM (" not in wrapped
    assert "WHERE id = 'INV-1'" in wrapped
    assert "customerId = 'C1'" in wrapped
    assert wrapped.startswith("SELECT id, amount FROM silver_dbc_sales_invoices WHERE")


def test_inject_validation_filters_qualifies_fact_before_group_by() -> None:
    sql = (
        "SELECT o.id, SUM(o.amount) AS total "
        "FROM silver_dbc_sales_orders o "
        "JOIN silver_dbc_customers c ON o.customerId = c.id "
        "GROUP BY o.id"
    )
    wrapped = inject_validation_filters(
        sql,
        [{"fact": "sales_orders", "field": "id", "value": "SO-1"}],
    )
    assert "WHERE o.id = 'SO-1' GROUP BY" in wrapped
    assert ".id = 'SO-1'" not in wrapped.replace("o.id = 'SO-1'", "")


def test_inject_validation_filters_ignores_where_inside_subquery() -> None:
    sql = (
        "SELECT customer_id, SUM(amount) AS revenue\n"
        "FROM (\n"
        "  SELECT customer_id, amount\n"
        "  FROM silver_dbc_sales_invoices\n"
        "  WHERE status = 'Posted'\n"
        ") inv\n"
        "GROUP BY customer_id"
    )
    wrapped = inject_validation_filters(
        sql,
        [{"field": "customer_id", "value": "CUST-1"}],
    )
    assert ") inv WHERE customer_id = 'CUST-1' GROUP BY" in wrapped
    assert ") inv AND customer_id" not in wrapped


def test_inject_validation_filters_appends_to_outer_where_before_group_by() -> None:
    sql = (
        "SELECT customer_id, SUM(amount) AS revenue "
        "FROM silver_dbc_sales_invoices "
        "WHERE status = 'Posted' "
        "GROUP BY customer_id"
    )
    wrapped = inject_validation_filters(
        sql,
        [{"field": "customer_id", "value": "CUST-1"}],
    )
    assert "WHERE status = 'Posted' AND customer_id = 'CUST-1' GROUP BY" in wrapped


def test_extract_silver_entities_from_sql() -> None:
    sql = (
        "SELECT c.id, SUM(l.amount) AS revenue "
        "FROM silver_dbc_customers c "
        "JOIN silver.sales_invoice_lines l ON c.id = l.customerId "
        "JOIN meshflow_poc_dev.silver_dbc_items i ON l.itemId = i.id "
        "JOIN dna_out_fact_revenue_lines f ON f.customer_id = c.id"
    )
    assert extract_silver_entities_from_sql(sql, source="dbc") == {
        "customers",
        "sales_invoice_lines",
        "items",
    }


def test_silver_entities_for_sql_pack_includes_targets_and_gold_sources() -> None:
    digest = sha256_text("SELECT 1")
    pack = parse_sql_manifest(
        {
            "version": "1.0.0",
            "transforms": [
                {
                    "id": "enhance__customers",
                    "layer": "silver",
                    "mode": "add_columns",
                    "file": "silver/enhance__customers.sql",
                    "sha256": digest,
                    "target_entity": "customers",
                },
                {
                    "id": "kpi_rev",
                    "layer": "gold",
                    "mode": "kpi",
                    "file": "gold/kpi_rev.sql",
                    "sha256": digest,
                    "output_id": "out_kpi_snapshot",
                    "grain_columns": ["customerId"],
                },
            ],
        }
    )
    assert pack is not None
    entities = silver_entities_for_sql_pack(
        pack,
        source="dbc",
        gold_sql={"gold/kpi_rev.sql": "SELECT SUM(amount) FROM silver_dbc_sales_orders"},
    )
    assert entities == ["customers", "sales_orders"]
