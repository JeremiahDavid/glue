"""Tests for semantic model ER graph layout."""

from __future__ import annotations

from meshflow.dna.semantic_graph import build_graph_payload, render_graph_svg


def test_build_graph_payload_groups_by_role() -> None:
    model = {
        "entities": [
            {"id": "ent_a", "silver_entity": "customers", "role": "dimension", "status": "approved"},
            {"id": "ent_b", "silver_entity": "sales_invoice_lines", "role": "fact", "status": "proposed"},
        ],
        "relationships": [
            {
                "id": "rel_1",
                "from_entity": "sales_invoice_lines",
                "from_column": "customerId",
                "to_entity": "customers",
                "to_column": "id",
                "status": "proposed",
            }
        ],
    }
    graph = build_graph_payload(model)
    assert len(graph["nodes"]) == 2
    assert len(graph["edges"]) == 1
    fact = next(node for node in graph["nodes"] if node["role"] == "fact")
    dimension = next(node for node in graph["nodes"] if node["role"] == "dimension")
    assert fact["x"] > dimension["x"]


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
