"""Tests for gold-layer chart aggregations."""

from __future__ import annotations

from hiveflow.dna.web.charts.gold import (
    aggregate_revenue_by_item,
    aggregate_revenue_by_month,
    aggregate_stacked_customer_revenue,
    aggregate_top_customers,
    rolling_average,
)


def test_aggregate_top_customers() -> None:
    rows = [
        {"customerId": "c1", "customerName": "Acme", "netAmount": 100.0},
        {"customerId": "c2", "customerName": "Northwind", "netAmount": 40.0},
        {"customerId": "c1", "customerName": "Acme", "netAmount": 25.0},
    ]
    assert aggregate_top_customers(rows) == [("Acme", 125.0), ("Northwind", 40.0)]


def test_aggregate_revenue_by_item_groups_and_labels() -> None:
    rows = [
        {"itemId": "i1", "netAmount": 100.0},
        {"itemId": "i2", "netAmount": 40.0},
        {"itemId": "i1", "netAmount": 25.0},
    ]
    items = [
        {"id": "i1", "displayName": "Widget A"},
        {"id": "i2", "displayName": "Widget B"},
    ]
    assert aggregate_revenue_by_item(rows, items) == [("Widget A", 125.0), ("Widget B", 40.0)]


def test_aggregate_stacked_customer_revenue() -> None:
    rows = [
        {"postingDate": "2026-01-15", "customerId": "c1", "customerName": "Acme", "netAmount": 100.0},
        {"postingDate": "2026-01-20", "customerId": "c2", "customerName": "Northwind", "netAmount": 40.0},
        {"postingDate": "2026-02-01", "customerId": "c1", "customerName": "Acme", "netAmount": 200.0},
    ]
    categories, series = aggregate_stacked_customer_revenue(rows, month_limit=12, customer_limit=2)
    assert categories == ["Jan '26", "Feb '26"]
    assert ("Acme", [100.0, 200.0]) in series
    assert ("Northwind", [40.0, 0.0]) in series


def test_rolling_average() -> None:
    assert rolling_average([100.0, 200.0, 300.0]) == [100.0, 150.0, 200.0]


def test_aggregate_revenue_by_month_respects_limit() -> None:
    rows = [
        {"postingDate": "2025-11-01", "netAmount": 10.0},
        {"postingDate": "2026-01-15", "netAmount": 100.0},
        {"postingDate": "2026-02-01", "netAmount": 200.0},
    ]
    assert aggregate_revenue_by_month(rows, limit=2) == [("2026-01", 100.0), ("2026-02", 200.0)]
