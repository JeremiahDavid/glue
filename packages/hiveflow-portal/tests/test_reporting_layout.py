"""Tests for reporting layout helpers."""

from __future__ import annotations

from meshflow.dna.web.portal.reporting_layout import (
    chart_catalog_enabled,
    chart_catalog_page,
    is_chart_catalog_page,
    list_reporting_pages,
    reporting_data_menu,
)


def test_chart_catalog_flag_controls_nav_page() -> None:
    layout = {
        "include_chart_catalog": True,
        "pages": [{"id": "page_summary", "title": "Summary", "path": "/portal"}],
    }

    class Settings:
        reporting_config_id = "x"

    pages = list_reporting_pages(Settings(), override=layout)  # type: ignore[arg-type]
    assert any(page["path"] == "/portal/chart-demo" for page in pages)
    assert is_chart_catalog_page(chart_catalog_page())


def test_chart_catalog_disabled_excludes_page() -> None:
    layout = {
        "include_chart_catalog": False,
        "pages": [{"id": "page_summary", "title": "Summary", "path": "/portal"}],
    }

    class Settings:
        reporting_config_id = "x"

    pages = list_reporting_pages(Settings(), override=layout)  # type: ignore[arg-type]
    assert not any(page["path"] == "/portal/chart-demo" for page in pages)
    assert not chart_catalog_enabled(layout)


def test_reporting_data_menu_nests_under_pillar_hub() -> None:
    layout = {
        "include_chart_catalog": False,
        "pages": [
            {"id": "page_summary", "title": "Summary", "path": "/portal", "pillar": "summary"},
            {
                "id": "page_executive",
                "title": "Executive",
                "path": "/portal/executive",
                "pillar": "executive",
                "sections": [{"layout": "kpi_grid"}],
            },
            {"id": "page_sales", "title": "Sales", "path": "/portal/sales", "pillar": "sales"},
            {
                "id": "page_revenue",
                "title": "Order-to-cash detail",
                "path": "/portal/revenue",
                "pillar": "sales",
                "tables": [{"source_output": "out_fact_revenue_lines"}],
            },
            {
                "id": "page_revenue_trend",
                "title": "Revenue trend",
                "path": "/portal/revenue-trend",
                "pillar": "sales",
                "charts": [{"source_output": "out_fact_revenue_lines"}],
            },
            {
                "id": "page_operations",
                "title": "Operations",
                "path": "/portal/operations",
                "pillar": "operations",
            },
        ],
    }

    class Settings:
        reporting_config_id = "x"

    menu = reporting_data_menu(Settings(), override=layout)  # type: ignore[arg-type]
    assert ("/portal", "Summary") in menu
    assert ("/portal/executive", "Executive") in menu
    assert ("/portal/operations", "Operations") in menu
    assert ("/portal/revenue", "Order-to-cash detail") not in menu
    assert ("/portal/revenue-trend", "Revenue trend") not in menu
    sales = next(item for item in menu if item[0] == "/portal/sales")
    assert sales[1] == "Sales"
    assert sales[2] == (
        ("/portal/revenue", "Order-to-cash detail"),
        ("/portal/revenue-trend", "Revenue trend"),
    )
