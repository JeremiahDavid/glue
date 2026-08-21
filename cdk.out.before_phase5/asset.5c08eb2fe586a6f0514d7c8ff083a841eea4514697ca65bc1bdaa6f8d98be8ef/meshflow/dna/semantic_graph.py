"""Layout helpers for semantic model ER graph visualization."""

from __future__ import annotations

from typing import Any


_ROLE_ORDER = ("dimension", "reference", "fact", "bridge")
_ROLE_X = {
    "dimension": 80,
    "reference": 280,
    "fact": 480,
    "bridge": 680,
}


def build_graph_payload(model: dict[str, Any]) -> dict[str, Any]:
    entities = [e for e in model.get("entities") or [] if isinstance(e, dict)]
    relationships = [r for r in model.get("relationships") or [] if isinstance(r, dict)]

    role_buckets: dict[str, list[dict[str, Any]]] = {role: [] for role in _ROLE_ORDER}
    other: list[dict[str, Any]] = []
    for entity in entities:
        role = str(entity.get("role") or "reference").lower()
        if role in role_buckets:
            role_buckets[role].append(entity)
        else:
            other.append(entity)
    if other:
        role_buckets.setdefault("reference", []).extend(other)

    nodes: list[dict[str, Any]] = []
    y_gap = 72
    for role in _ROLE_ORDER:
        bucket = role_buckets.get(role) or []
        for index, entity in enumerate(bucket):
            silver = str(entity.get("silver_entity") or "")
            nodes.append(
                {
                    "id": silver,
                    "entity_id": str(entity.get("id") or ""),
                    "label": silver.replace("_", " ").title(),
                    "role": role,
                    "status": str(entity.get("status") or "proposed"),
                    "x": _ROLE_X.get(role, 280),
                    "y": 60 + index * y_gap,
                }
            )

    node_ids = {node["id"] for node in nodes}
    edges: list[dict[str, Any]] = []
    for rel in relationships:
        from_entity = str(rel.get("from_entity") or "")
        to_entity = str(rel.get("to_entity") or "")
        if from_entity not in node_ids or to_entity not in node_ids:
            continue
        edges.append(
            {
                "id": str(rel.get("id") or ""),
                "from": from_entity,
                "to": to_entity,
                "label": str(rel.get("from_column") or ""),
                "status": str(rel.get("status") or "proposed"),
                "cardinality": str(rel.get("cardinality") or ""),
            }
        )

    return {"nodes": nodes, "edges": edges}


def render_graph_svg(graph: dict[str, Any], *, width: int = 760, height: int = 420) -> str:
    nodes = graph.get("nodes") or []
    edges = graph.get("edges") or []
    if not nodes:
        return (
            f'<svg class="semantic-graph-svg" viewBox="0 0 {width} {height}" '
            f'width="100%" height="{height}" xmlns="http://www.w3.org/2000/svg">'
            f'<text x="50%" y="50%" text-anchor="middle" fill="#94a3b8" font-size="14">'
            "No entities to display</text></svg>"
        )

    positions = {str(n["id"]): (int(n.get("x") or 0), int(n.get("y") or 0)) for n in nodes}
    status_stroke = {
        "approved": "#34d399",
        "proposed": "#fbbf24",
        "rejected": "#f87171",
    }

    lines: list[str] = [
        f'<svg class="semantic-graph-svg" viewBox="0 0 {width} {height}" '
        f'width="100%" height="{height}" xmlns="http://www.w3.org/2000/svg">',
        '<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">'
        '<path d="M0,0 L6,3 L0,6 Z" fill="#64748b"/></marker></defs>',
    ]

    for edge in edges:
        start = positions.get(str(edge.get("from") or ""))
        end = positions.get(str(edge.get("to") or ""))
        if not start or not end:
            continue
        x1, y1 = start[0] + 110, start[1] + 18
        x2, y2 = end[0], end[1] + 18
        stroke = status_stroke.get(str(edge.get("status") or ""), "#64748b")
        lines.append(
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{stroke}" '
            f'stroke-width="1.5" marker-end="url(#arrow)" opacity="0.85"/>'
        )

    for node in nodes:
        x, y = int(node.get("x") or 0), int(node.get("y") or 0)
        status = str(node.get("status") or "proposed")
        stroke = status_stroke.get(status, "#64748b")
        role = str(node.get("role") or "")
        label = str(node.get("label") or node.get("id") or "")
        lines.append(
            f'<rect x="{x}" y="{y}" width="110" height="36" rx="6" '
            f'fill="rgba(15,23,42,0.92)" stroke="{stroke}" stroke-width="1.5"/>'
        )
        lines.append(
            f'<text x="{x + 8}" y="{y + 14}" fill="#e2e8f0" font-size="10" font-weight="600">'
            f"{_xml_escape(label[:14])}</text>"
        )
        lines.append(
            f'<text x="{x + 8}" y="{y + 28}" fill="#94a3b8" font-size="9">'
            f"{_xml_escape(role)} · {status}</text>"
        )

    lines.append("</svg>")
    return "\n".join(lines)


def _xml_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
