"""Tests for semantic model ER graph layout."""

from __future__ import annotations

from meshflow.dna.semantic_graph import build_graph_payload, render_graph_svg

_MODEL = {
    "entities": [
        {"id": "ent_a", "silver_entity": "customers", "role": "dimension", "status": "approved"},
        {"id": "ent_b", "silver_entity": "sales_invoice_lines", "role": "fact", "status": "proposed"},
        {"id": "ent_c", "silver_entity": "sales_order_lines", "role": "fact", "status": "proposed"},
        {"id": "ent_d", "silver_entity": "items", "role": "dimension", "status": "approved"},
    ],
    "relationships": [
        {
            "id": "rel_1",
            "from_entity": "sales_invoice_lines",
            "from_column": "customerId",
            "to_entity": "customers",
            "to_column": "id",
            "status": "proposed",
        },
        {
            "id": "rel_2",
            "from_entity": "sales_order_lines",
            "from_column": "customerId",
            "to_entity": "customers",
            "to_column": "id",
            "status": "proposed",
        },
    ],
}


def test_focused_fact_graph_centers_fact_between_dimensions() -> None:
    graph = build_graph_payload(_MODEL, focus_fact="sales_invoice_lines")
    assert graph["mode"] == "fact"
    fact = next(node for node in graph["nodes"] if node["role"] == "fact")
    dimension = next(node for node in graph["nodes"] if node["role"] == "dimension")
    assert fact["id"] == "sales_invoice_lines"
    assert fact["x"] > dimension["x"]
    assert len(graph["edges"]) == 1


def test_overview_graph_groups_by_fact() -> None:
    graph = build_graph_payload(_MODEL)
    assert graph["mode"] == "overview"
    fact_nodes = [node for node in graph["nodes"] if node["role"] == "fact"]
    assert len(fact_nodes) == 2
    customer_nodes = [node for node in graph["nodes"] if node["silver_entity"] == "customers"]
    assert len(customer_nodes) == 2


def test_render_graph_svg_includes_nodes() -> None:
    graph = build_graph_payload(
        {
            "entities": [
                {"id": "ent_a", "silver_entity": "customers", "role": "dimension", "status": "approved"},
            ],
            "relationships": [],
        }
    )
    svg = render_graph_svg(graph)
    assert "semantic-graph-svg" in svg
    assert "Customers" in svg


def test_render_graph_svg_expands_for_tall_layout() -> None:
    entities = [
        {
            "id": f"ent_{index}",
            "silver_entity": f"entity_{index}",
            "role": "reference",
            "status": "proposed",
        }
        for index in range(12)
    ]
    graph = build_graph_payload({"entities": entities, "relationships": []})
    svg = render_graph_svg(graph)
    assert 'height="' in svg
    assert "Entity 11" in svg
