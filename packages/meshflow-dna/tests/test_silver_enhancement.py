"""Tests for silver enhancement guardrails."""

from __future__ import annotations

import pytest

from meshflow.dna.silver_enhancement import (
    assert_preserves_silver_grain,
    assert_unique_gold_grain,
    canonical_enhancement_id,
    try_deterministic_merge,
    validate_gold_grain_columns,
)
from meshflow.dna.sql_pack import parse_sql_manifest, sha256_text


def test_canonical_enhancement_id() -> None:
    assert canonical_enhancement_id("customers") == "enhance__customers"


def test_assert_preserves_silver_grain_rejects_group_by() -> None:
    with pytest.raises(ValueError, match="GROUP BY"):
        assert_preserves_silver_grain(
            "SELECT id, SUM(amount) AS total FROM silver_dbc_sales_orders GROUP BY id"
        )


def test_assert_preserves_silver_grain_rejects_distinct() -> None:
    with pytest.raises(ValueError, match="DISTINCT"):
        assert_preserves_silver_grain("SELECT DISTINCT id FROM silver_dbc_customers")


def test_validate_gold_grain_columns_sorts_and_dedupes() -> None:
    assert validate_gold_grain_columns(["customerId", "period_key", "customerId"]) == [
        "customerId",
        "period_key",
    ]


def test_assert_unique_gold_grain_rejects_duplicate() -> None:
    existing = [
        {
            "id": "kpi_a",
            "layer": "gold",
            "output_id": "out_a",
            "grain_columns": ["customerId"],
        }
    ]
    with pytest.raises(ValueError, match="already used"):
        assert_unique_gold_grain(
            existing,
            output_id="out_b",
            grain_columns=["customerId"],
        )


def test_try_deterministic_merge_single_contribution() -> None:
    sql = "SELECT id, name, isInterco FROM silver_dbc_customers"
    merged = try_deterministic_merge(
        target_entity="customers",
        source="dbc",
        contributions={"add_is_interco": sql},
    )
    assert merged == sql


def test_rewrite_star_select_with_explicit_columns() -> None:
    from meshflow.dna.silver_enhancement import rewrite_star_select_with_explicit_columns

    sql = (
        "SELECT *, CASE WHEN displayName = 'A' THEN true ELSE false END AS isInterco "
        "FROM silver_dbc_customers"
    )
    rewritten = rewrite_star_select_with_explicit_columns(
        sql,
        table_name="silver_dbc_customers",
        column_lookup={
            "id": "id",
            "displayname": "displayname",
            "isinterco": "isinterco",
        },
        replacing_aliases=["isInterco"],
    )
    assert "t.id" in rewritten
    assert "t.displayname" in rewritten
    assert "t.isinterco" not in rewritten
    assert "AS isInterco" in rewritten
    assert "FROM silver_dbc_customers t" in rewritten


def test_rewrite_qualified_star_select_with_subquery() -> None:
    from meshflow.dna.silver_enhancement import rewrite_star_select_with_explicit_columns

    sql = (
        "SELECT\n"
        "  si.*,\n"
        "  COALESCE((SELECT SUM(totalAmountIncludingTax)\n"
        "    FROM silver_dbc_sales_credit_memos scm\n"
        "    WHERE scm.invoiceId = si.id), 0) AS creditMemoAmount\n"
        "FROM silver_dbc_sales_invoices si"
    )
    rewritten = rewrite_star_select_with_explicit_columns(
        sql,
        table_name="silver_dbc_sales_invoices",
        column_lookup={
            "id": "id",
            "number": "number",
            "creditmemoamount": "creditmemoamount",
        },
        replacing_aliases=["creditMemoAmount"],
    )
    assert "si.id" in rewritten
    assert "si.number" in rewritten
    assert "si.creditmemoamount" not in rewritten
    assert "AS creditMemoAmount" in rewritten
    assert "FROM silver_dbc_sales_credit_memos" in rewritten


def test_try_deterministic_merge_combines_simple_columns() -> None:
    merged = try_deterministic_merge(
        target_entity="customers",
        source="dbc",
        contributions={
            "add_a": "SELECT id, col_a AS colA FROM silver_dbc_customers",
            "add_b": "SELECT id, col_b AS colB FROM silver_dbc_customers",
        },
    )
    assert merged is not None
    assert "colA" in merged
    assert "colB" in merged
    assert "t.*" in merged
    assert "silver_dbc_customers" in merged


def test_parse_sql_manifest_strict_silver_uniqueness() -> None:
    digest = sha256_text("SELECT id FROM silver_dbc_customers")
    with pytest.raises(ValueError, match="canonical id"):
        parse_sql_manifest(
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
                        "id": "enhance__customers_extra",
                        "layer": "silver",
                        "mode": "add_columns",
                        "file": "silver/enhance__customers_extra.sql",
                        "sha256": digest,
                        "target_entity": "customers",
                    },
                ],
            },
            strict=True,
        )


def test_parse_sql_manifest_strict_gold_grain_uniqueness() -> None:
    digest = sha256_text("SELECT customerId, SUM(amount) AS value FROM silver_dbc_sales_orders GROUP BY customerId")
    with pytest.raises(ValueError, match="Duplicate gold grain"):
        parse_sql_manifest(
            {
                "version": "1.0.0",
                "transforms": [
                    {
                        "id": "kpi_a",
                        "layer": "gold",
                        "mode": "kpi",
                        "file": "gold/kpi_a.sql",
                        "sha256": digest,
                        "output_id": "out_a",
                        "grain_columns": ["customerId"],
                    },
                    {
                        "id": "kpi_b",
                        "layer": "gold",
                        "mode": "kpi",
                        "file": "gold/kpi_b.sql",
                        "sha256": digest,
                        "output_id": "out_b",
                        "grain_columns": ["customerId"],
                    },
                ],
            },
            strict=True,
        )


def test_parse_sql_manifest_legacy_non_strict() -> None:
    digest = sha256_text("SELECT id FROM silver_dbc_customers")
    pack = parse_sql_manifest(
        {
            "version": "1.0.0",
            "transforms": [
                {
                    "id": "add_is_interco",
                    "layer": "silver",
                    "mode": "add_columns",
                    "file": "silver/add_is_interco.sql",
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
                },
            ],
        },
        strict=False,
    )
    assert pack is not None
    assert len(pack.transforms) == 2
