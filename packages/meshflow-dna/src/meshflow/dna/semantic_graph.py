"""Layout helpers for semantic model ER graph visualization."""

from __future__ import annotations

from typing import Any

_ROLE_ORDER = ("dimension", "reference", "fact", "bridge")
_FACT_CENTER_X = 380
_DIMENSION_X = 80
_REFERENCE_X = 680
_NODE_WIDTH = 110
_NODE_HEIGHT = 36
_Y_GAP = 72
_CLUSTER_GAP = 48


def build_graph_payload(
    model: dict[str, Any],
    *,
    focus_fact: str | None = None,
) -> dict[str, Any]:
    entities = [e for e in model.get("entities") or [] if isinstance(e, dict)]
    relationships = [r for r in model.get("relationships") or [] if isinstance(r, dict)]
    facts = _fact_entities(entities)
    fact_options = [_fact_option(entity) for entity in facts]

    focus = str(focus_fact or "").strip().lower() or None
    if focus and focus not in {str(item["id"]) for item in fact_options}:
        focus = None

    if focus:
        graph = _build_focused_fact_graph(entities, relationships, focus_fact=focus)
        mode = "fact"
    elif facts:
        graph = _build_fact_overview_graph(entities, relationships, facts=facts)
        mode = "overview"
    else:
        graph = _build_role_column_graph(entities, relationships)
        mode = "roles"

    graph["facts"] = fact_options
    graph["focus_fact"] = focus
    graph["mode"] = mode
    return graph


def _fact_entities(entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        [entity for entity in entities if str(entity.get("role") or "").lower() == "fact"],
        key=lambda item: str(item.get("silver_entity") or ""),
    )


def _fact_option(entity: dict[str, Any]) -> dict[str, str]:
    silver = str(entity.get("silver_entity") or "")
    return {
        "id": silver,
        "label": silver.replace("_", " ").title(),
        "status": str(entity.get("status") or "proposed"),
    }


def _entity_lookup(entities: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        str(entity.get("silver_entity") or "").strip().lower(): entity
        for entity in entities
        if str(entity.get("silver_entity") or "").strip()
    }


def _neighborhood_for_fact(
    fact_id: str,
    *,
    entities: list[dict[str, Any]],
    relationships: list[dict[str, Any]],
) -> set[str]:
    related = {fact_id}
    for rel in relationships:
        from_entity = str(rel.get("from_entity") or "").strip().lower()
        to_entity = str(rel.get("to_entity") or "").strip().lower()
        if from_entity == fact_id:
            related.add(to_entity)
        if to_entity == fact_id:
            related.add(from_entity)
    known = set(_entity_lookup(entities))
    return related & known


def _node_from_entity(
    entity: dict[str, Any],
    *,
    node_id: str,
    x: int,
    y: int,
) -> dict[str, Any]:
    silver = str(entity.get("silver_entity") or "")
    return {
        "id": node_id,
        "entity_id": str(entity.get("id") or ""),
        "silver_entity": silver,
        "label": silver.replace("_", " ").title(),
        "role": str(entity.get("role") or "reference").lower(),
        "status": str(entity.get("status") or "proposed"),
        "x": x,
        "y": y,
    }


def _layout_fact_star(
    cluster_entities: list[dict[str, Any]],
    *,
    fact_id: str,
    y_base: int,
    node_id_for: Any,
) -> list[dict[str, Any]]:
    by_silver = _entity_lookup(cluster_entities)
    fact_entity = by_silver.get(fact_id)
    if fact_entity is None:
        return []

    others = [entity for silver, entity in sorted(by_silver.items()) if silver != fact_id]
    dimensions = [entity for entity in others if str(entity.get("role") or "").lower() == "dimension"]
    references = [
        entity
        for entity in others
        if str(entity.get("role") or "").lower() in {"reference", "bridge"}
        or str(entity.get("role") or "").lower() not in {"dimension", "fact"}
    ]

    side_count = max(len(dimensions), len(references), 1)
    fact_y = y_base + ((side_count - 1) * _Y_GAP) // 2
    nodes = [
        _node_from_entity(
            fact_entity,
            node_id=node_id_for(fact_entity, is_fact=True),
            x=_FACT_CENTER_X,
            y=fact_y,
        )
    ]

    for index, entity in enumerate(dimensions):
        nodes.append(
            _node_from_entity(
                entity,
                node_id=node_id_for(entity, is_fact=False),
                x=_DIMENSION_X,
                y=y_base + index * _Y_GAP,
            )
        )
    for index, entity in enumerate(references):
        nodes.append(
            _node_from_entity(
                entity,
                node_id=node_id_for(entity, is_fact=False),
                x=_REFERENCE_X,
                y=y_base + index * _Y_GAP,
            )
        )
    return nodes


def _build_focused_fact_graph(
    entities: list[dict[str, Any]],
    relationships: list[dict[str, Any]],
    *,
    focus_fact: str,
) -> dict[str, Any]:
    member_ids = _neighborhood_for_fact(
        focus_fact,
        entities=entities,
        relationships=relationships,
    )
    cluster_entities = [
        entity
        for entity in entities
        if str(entity.get("silver_entity") or "").strip().lower() in member_ids
    ]

    def node_id_for(entity: dict[str, Any], *, is_fact: bool) -> str:
        return str(entity.get("silver_entity") or "")

    nodes = _layout_fact_star(
        cluster_entities,
        fact_id=focus_fact,
        y_base=60,
        node_id_for=node_id_for,
    )
    node_ids = {node["id"] for node in nodes}
    edges = _edges_for_nodes(relationships, node_ids=node_ids, id_key="silver_entity")
    return {"nodes": nodes, "edges": edges}


def _build_fact_overview_graph(
    entities: list[dict[str, Any]],
    relationships: list[dict[str, Any]],
    *,
    facts: list[dict[str, Any]],
) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    y_offset = 60

    for fact_entity in facts:
        fact_id = str(fact_entity.get("silver_entity") or "").strip().lower()
        member_ids = _neighborhood_for_fact(fact_id, entities=entities, relationships=relationships)
        cluster_entities = [
            entity
            for entity in entities
            if str(entity.get("silver_entity") or "").strip().lower() in member_ids
        ]

        def node_id_for(entity: dict[str, Any], *, is_fact: bool, _fact=fact_id) -> str:
            silver = str(entity.get("silver_entity") or "").strip().lower()
            if is_fact:
                return silver
            return f"{silver}__{_fact}"

        cluster_nodes = _layout_fact_star(
            cluster_entities,
            fact_id=fact_id,
            y_base=y_offset,
            node_id_for=node_id_for,
        )
        if not cluster_nodes:
            continue

        silver_to_node_id = {
            str(node.get("silver_entity") or "").strip().lower(): str(node.get("id") or "")
            for node in cluster_nodes
        }
        cluster_node_ids = set(silver_to_node_id.values())
        cluster_edges = []
        for rel in relationships:
            from_silver = str(rel.get("from_entity") or "").strip().lower()
            to_silver = str(rel.get("to_entity") or "").strip().lower()
            if from_silver not in member_ids or to_silver not in member_ids:
                continue
            from_id = silver_to_node_id.get(from_silver)
            to_id = silver_to_node_id.get(to_silver)
            if not from_id or not to_id:
                continue
            cluster_edges.append(_edge_payload(rel, from_id=from_id, to_id=to_id))

        nodes.extend(cluster_nodes)
        edges.extend(cluster_edges)
        max_y = max(int(node.get("y") or 0) for node in cluster_nodes)
        y_offset = max_y + _NODE_HEIGHT + _CLUSTER_GAP

    assigned_silvers: set[str] = set()
    for fact_entity in facts:
        fact_id = str(fact_entity.get("silver_entity") or "").strip().lower()
        assigned_silvers |= _neighborhood_for_fact(
            fact_id,
            entities=entities,
            relationships=relationships,
        )
    orphan_entities = [
        entity
        for entity in entities
        if str(entity.get("silver_entity") or "").strip().lower() not in assigned_silvers
    ]
    if orphan_entities:
        for index, entity in enumerate(orphan_entities):
            silver = str(entity.get("silver_entity") or "").strip().lower()
            nodes.append(
                _node_from_entity(
                    entity,
                    node_id=f"orphan__{silver}",
                    x=_REFERENCE_X,
                    y=y_offset + index * _Y_GAP,
                )
            )
        y_offset += len(orphan_entities) * _Y_GAP

    return {"nodes": nodes, "edges": edges}


def _build_role_column_graph(
    entities: list[dict[str, Any]],
    relationships: list[dict[str, Any]],
) -> dict[str, Any]:
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

    role_x = {
        "dimension": _DIMENSION_X,
        "reference": 280,
        "fact": _FACT_CENTER_X,
        "bridge": _REFERENCE_X,
    }

    nodes: list[dict[str, Any]] = []
    for role in _ROLE_ORDER:
        bucket = role_buckets.get(role) or []
        for index, entity in enumerate(bucket):
            silver = str(entity.get("silver_entity") or "")
            nodes.append(
                _node_from_entity(
                    entity,
                    node_id=silver,
                    x=role_x.get(role, 280),
                    y=60 + index * _Y_GAP,
                )
            )

    node_ids = {node["id"] for node in nodes}
    edges = _edges_for_nodes(relationships, node_ids=node_ids, id_key="silver_entity")
    return {"nodes": nodes, "edges": edges}


def _edge_payload(rel: dict[str, Any], *, from_id: str, to_id: str) -> dict[str, Any]:
    return {
        "id": str(rel.get("id") or ""),
        "from": from_id,
        "to": to_id,
        "label": str(rel.get("from_column") or ""),
        "status": str(rel.get("status") or "proposed"),
        "cardinality": str(rel.get("cardinality") or ""),
    }


def _edges_for_nodes(
    relationships: list[dict[str, Any]],
    *,
    node_ids: set[str],
    id_key: str,
) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    for rel in relationships:
        from_entity = str(rel.get("from_entity") or "")
        to_entity = str(rel.get("to_entity") or "")
        if id_key == "silver_entity":
            from_id, to_id = from_entity, to_entity
        else:
            from_id, to_id = from_entity, to_entity
        if from_id not in node_ids or to_id not in node_ids:
            continue
        edges.append(_edge_payload(rel, from_id=from_id, to_id=to_id))
    return edges


def render_graph_svg(graph: dict[str, Any], *, width: int = 760, height: int = 420) -> str:
    nodes = graph.get("nodes") or []
    edges = graph.get("edges") or []
    if not nodes:
        return (
            f'<svg class="semantic-graph-svg" viewBox="0 0 {width} {height}" '
            f'width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">'
            f'<text x="50%" y="50%" text-anchor="middle" fill="#94a3b8" font-size="14">'
            "No entities to display</text></svg>"
        )

    width, height = _graph_dimensions(nodes, width=width, height=height)
    positions = {str(n["id"]): (int(n.get("x") or 0), int(n.get("y") or 0)) for n in nodes}
    status_stroke = {
        "approved": "#34d399",
        "proposed": "#fbbf24",
        "rejected": "#f87171",
    }

    lines: list[str] = [
        f'<svg class="semantic-graph-svg" viewBox="0 0 {width} {height}" '
        f'width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">',
        '<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">'
        '<path d="M0,0 L6,3 L0,6 Z" fill="#64748b"/></marker></defs>',
    ]

    for edge in edges:
        start = positions.get(str(edge.get("from") or ""))
        end = positions.get(str(edge.get("to") or ""))
        if not start or not end:
            continue
        x1, y1 = start[0] + _NODE_WIDTH, start[1] + 18
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
        is_fact = role == "fact"
        fill = "rgba(30, 58, 95, 0.95)" if is_fact else "rgba(15,23,42,0.92)"
        stroke_width = "2" if is_fact else "1.5"
        lines.append(
            f'<rect x="{x}" y="{y}" width="{_NODE_WIDTH}" height="{_NODE_HEIGHT}" rx="6" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="{stroke_width}"/>'
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


def _graph_dimensions(
    nodes: list[dict[str, Any]],
    *,
    width: int,
    height: int,
) -> tuple[int, int]:
    max_x = max((int(node.get("x") or 0) + _NODE_WIDTH for node in nodes), default=0)
    max_y = max((int(node.get("y") or 0) + _NODE_HEIGHT for node in nodes), default=0)
    return max(width, max_x + 40), max(height, max_y + 40)


def _xml_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
