"""Semantic model API payloads for the Semantic Builder portal."""

from __future__ import annotations

from typing import Any

from meshflow.dna.semantic_graph import build_graph_payload, render_graph_svg
from meshflow.dna.semantic_model import (
    builder_step_summary,
    draft_differs_from_production,
    evaluate_publish_readiness,
    load_production_semantic_model,
    load_semantic_model_draft,
    load_semantic_model_workflow,
    semantic_model_coverage,
    semantic_model_publish_gate,
)
from meshflow.dna.settings import DnaSettings


def builder_ui_payload(settings: DnaSettings, *, is_admin: bool, api_root: str = "") -> dict[str, Any]:
    from meshflow.dna.web.portal.semantics.builder_render import render_semantic_builder_content_html

    return {
        "html": render_semantic_builder_content_html(
            settings=settings,
            is_admin=is_admin,
            api_root=api_root,
        ),
        **builder_payload(settings),
    }


def builder_payload(settings: DnaSettings) -> dict[str, Any]:
    from meshflow.dna.semantic_knowledge_base import knowledge_base_summary
    from meshflow.dna.semantic_source_reference import source_reference_summary

    draft = load_semantic_model_draft(settings)
    production = load_production_semantic_model(settings)
    workflow = load_semantic_model_workflow(settings)
    readiness = evaluate_publish_readiness(draft)
    gate = semantic_model_publish_gate(settings)

    return {
        "draft": draft,
        "production": production,
        "workflow": {
            "active_version": workflow.get("active_version"),
            "draft_updated_at": workflow.get("draft_updated_at"),
            "init_completed": bool(workflow.get("init_completed")),
            "init_at": workflow.get("init_at"),
            "current_step": workflow.get("current_step"),
            "steps_completed": workflow.get("steps_completed") or {},
            "profiling_status": workflow.get("profiling_status") or "idle",
            "profiling_error": workflow.get("profiling_error"),
            "profiling_started_at": workflow.get("profiling_started_at"),
            "profiling_completed_at": workflow.get("profiling_completed_at"),
        },
        "step_summary": builder_step_summary(settings),
        "coverage": semantic_model_coverage(draft),
        "readiness": readiness,
        "gold_gate": gate,
        "draft_differs_from_production": draft_differs_from_production(settings),
        "knowledge_base": knowledge_base_summary(settings),
        "source_reference": source_reference_summary(settings),
    }


def relationships_payload(settings: DnaSettings) -> dict[str, Any]:
    draft = load_semantic_model_draft(settings)
    relationships = draft.get("relationships") or []
    return {
        "relationships": relationships,
        "proposed": [r for r in relationships if str(r.get("status") or "") == "proposed"],
        "approved": [r for r in relationships if str(r.get("status") or "") == "approved"],
    }


def entities_payload(settings: DnaSettings) -> dict[str, Any]:
    draft = load_semantic_model_draft(settings)
    entities = draft.get("entities") or []
    return {
        "entities": entities,
        "by_role": {
            role: [e for e in entities if str(e.get("role") or "") == role]
            for role in ("fact", "dimension", "bridge", "reference")
        },
    }


def graph_view_payload(settings: DnaSettings, *, focus_fact: str | None = None) -> dict[str, Any]:
    draft = load_semantic_model_draft(settings)
    graph = build_graph_payload(draft, focus_fact=focus_fact)
    return {
        "graph": graph,
        "svg": render_graph_svg(graph),
        "facts": graph.get("facts") or [],
        "focus_fact": graph.get("focus_fact"),
        "mode": graph.get("mode"),
    }


def attributes_payload(settings: DnaSettings, *, proposed_only: bool = False) -> dict[str, Any]:
    draft = load_semantic_model_draft(settings)
    attributes = draft.get("attributes") or []
    if proposed_only:
        attributes = [
            item
            for item in attributes
            if isinstance(item, dict) and str(item.get("status") or "") == "proposed"
        ]
    tagged = [item for item in attributes if isinstance(item, dict) and item.get("concepts")]
    return {
        "attributes": attributes[:500],
        "proposed_count": sum(
            1
            for item in draft.get("attributes") or []
            if isinstance(item, dict) and str(item.get("status") or "") == "proposed"
        ),
        "tagged_count": len(tagged),
    }


def questions_payload(settings: DnaSettings) -> dict[str, Any]:
    draft = load_semantic_model_draft(settings)
    questions = draft.get("questions") or []
    return {
        "questions": questions,
        "open": [q for q in questions if str(q.get("status") or "open") == "open"],
        "blocking": [
            q
            for q in questions
            if str(q.get("status") or "open") == "open" and q.get("blocks_publish")
        ],
    }
