"""KPI Generator intent + multi-layer draft helpers."""

from __future__ import annotations

import re
from typing import Any

from meshflow.dna.source_docs.reference import normalize_reference_source

VALID_INTENTS = ("clarify", "reuse", "implement")
GENERATION_PENDING = "pending"
GENERATION_ERROR = "error"
GENERATION_COMPLETE = "complete"
_DRAFT_KEYS = (
    "layer",
    "mode",
    "id",
    "target_entity",
    "output_id",
    "grain_columns",
    "file",
    "sql",
    "fields_used",
    "filters_applied",
    "calculation",
    "summary",
)
_WITH_RE = re.compile(r"^\s*WITH\s+", re.IGNORECASE)


def proposal_generation_status(proposal: dict[str, Any] | None) -> str:
    if not proposal:
        return ""
    raw = str(proposal.get("generation_status") or "").strip().lower()
    if raw in {GENERATION_PENDING, GENERATION_ERROR, GENERATION_COMPLETE}:
        return raw
    return ""


def proposal_intent(proposal: dict[str, Any] | None) -> str:
    if not proposal:
        return ""
    raw = str(proposal.get("intent") or "").strip().lower()
    if raw in VALID_INTENTS:
        return raw
    if iter_proposal_drafts(proposal):
        return "implement"
    if proposal.get("questions"):
        return "clarify"
    if proposal.get("reuse"):
        return "reuse"
    return ""


def iter_proposal_drafts(proposal: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not proposal:
        return []
    drafts = proposal.get("drafts")
    if isinstance(drafts, list) and drafts:
        return [item for item in drafts if isinstance(item, dict) and item]
    draft = proposal.get("draft")
    if isinstance(draft, dict) and draft:
        return [draft]
    return []


def find_draft_by_layer(proposal: dict[str, Any] | None, layer: str) -> dict[str, Any] | None:
    wanted = str(layer or "").strip().lower()
    for draft in iter_proposal_drafts(proposal):
        if str(draft.get("layer") or "").strip().lower() == wanted:
            return draft
    return None


def primary_draft(drafts: list[dict[str, Any]] | None) -> dict[str, Any]:
    items = [item for item in (drafts or []) if isinstance(item, dict) and item]
    for draft in items:
        if str(draft.get("layer") or "").strip().lower() == "gold":
            return draft
    return items[0] if items else {}


def ordered_drafts(drafts: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    items = [item for item in (drafts or []) if isinstance(item, dict) and item]
    silver = [item for item in items if str(item.get("layer") or "").strip().lower() == "silver"]
    gold = [item for item in items if str(item.get("layer") or "").strip().lower() == "gold"]
    other = [
        item
        for item in items
        if str(item.get("layer") or "").strip().lower() not in {"silver", "gold"}
    ]
    return silver + gold + other


def _draft_from_mapping(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: payload[key] for key in _DRAFT_KEYS if key in payload}


def _infer_intent(payload: dict[str, Any]) -> str:
    raw = str(payload.get("intent") or "").strip().lower()
    if raw in VALID_INTENTS:
        return raw
    if raw:
        raise ValueError(f"intent must be one of {', '.join(VALID_INTENTS)}")
    if payload.get("questions"):
        return "clarify"
    if isinstance(payload.get("reuse"), dict):
        return "reuse"
    if payload.get("layer") or payload.get("drafts"):
        return "implement"
    raise ValueError("Model JSON must include intent, drafts, or layer")


def _as_question_list(raw: Any) -> list[str]:
    if isinstance(raw, str):
        text = raw.strip()
        return [text] if text else []
    if not isinstance(raw, list):
        return []
    questions: list[str] = []
    for item in raw:
        text = str(item or "").strip()
        if text:
            questions.append(text)
    return questions


def normalize_generated_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize Bedrock JSON into intent + optional drafts/questions/reuse."""
    if not isinstance(payload, dict):
        raise ValueError("Model JSON must be an object")
    intent = _infer_intent(payload)
    summary = str(payload.get("summary") or payload.get("calculation") or "").strip()
    result: dict[str, Any] = {"intent": intent, "summary": summary}

    if intent == "clarify":
        questions = _as_question_list(payload.get("questions"))
        if not questions:
            raise ValueError("clarify intent requires questions")
        result["questions"] = questions
        result["drafts"] = []
        return result

    if intent == "reuse":
        reuse = payload.get("reuse")
        if not isinstance(reuse, dict):
            reuse = {
                "reason": str(payload.get("reason") or summary).strip(),
                "output_id": str(payload.get("output_id") or "").strip() or None,
                "column": str(payload.get("column") or "").strip() or None,
                "sql": str(payload.get("sql") or "").strip() or None,
            }
        else:
            reuse = dict(reuse)
        reason = str(reuse.get("reason") or summary).strip()
        if not reason:
            raise ValueError("reuse intent requires a reason")
        reuse["reason"] = reason
        sql = str(reuse.get("sql") or "").strip()
        reuse["sql"] = sql or None
        result["reuse"] = reuse
        result["drafts"] = []
        if not result["summary"]:
            result["summary"] = reason
        return result

    raw_drafts = payload.get("drafts")
    drafts: list[dict[str, Any]]
    if isinstance(raw_drafts, list) and raw_drafts:
        drafts = [dict(item) for item in raw_drafts if isinstance(item, dict)]
    else:
        draft = _draft_from_mapping(payload)
        if not draft.get("layer"):
            raise ValueError("implement intent requires drafts or layer")
        drafts = [draft]

    silver_count = 0
    gold_count = 0
    for draft in drafts:
        layer = str(draft.get("layer") or "").strip().lower()
        if layer == "silver":
            silver_count += 1
        elif layer == "gold":
            gold_count += 1
        else:
            raise ValueError("layer must be silver or gold")
    if silver_count > 1 or gold_count > 1:
        raise ValueError("A proposal may include at most one silver draft and one gold draft")
    if silver_count + gold_count == 0:
        raise ValueError("implement intent requires at least one draft")
    ordered = ordered_drafts(drafts)
    result["drafts"] = ordered
    if not result["summary"]:
        primary = primary_draft(ordered)
        result["summary"] = str(
            primary.get("summary") or primary.get("calculation") or ""
        ).strip()
    return result


def assistant_text_from_normalized(normalized: dict[str, Any]) -> str:
    intent = str(normalized.get("intent") or "").strip().lower()
    summary = str(normalized.get("summary") or "").strip()
    if intent == "clarify":
        questions = _as_question_list(normalized.get("questions"))
        if questions:
            numbered = "\n".join(f"{index}. {item}" for index, item in enumerate(questions, start=1))
            lead = summary or "I need a bit more detail before drafting SQL:"
            return f"{lead}\n{numbered}"
        return summary or "I need more detail before drafting SQL."
    if intent == "reuse":
        reuse = normalized.get("reuse") or {}
        reason = str(reuse.get("reason") or summary).strip()
        output_id = str(reuse.get("output_id") or "").strip()
        if output_id and reason:
            return f"Existing DNA output {output_id} already covers this. {reason}"
        return reason or "Existing DNA already covers this request."
    drafts = normalized.get("drafts") or []
    if len(drafts) > 1:
        layers = " + ".join(
            str(draft.get("layer") or "").strip() or "layer" for draft in drafts
        )
        return summary or f"Drafted {layers} SQL — review both updates below."
    primary = primary_draft(drafts)
    text = str(primary.get("summary") or primary.get("calculation") or summary).strip()
    return text or "Draft KPI SQL is ready — review the proposal below."


def dna_silver_table_name(source: str, entity: str) -> str:
    return f"silver_{normalize_reference_source(source)}_{entity.strip().lower()}"


def inline_silver_contribution_for_gold_sql(
    gold_sql: str,
    *,
    source: str,
    target_entity: str,
    contribution_sql: str,
) -> str:
    """Rewrite gold SQL to read a not-yet-materialized silver column via CTE.

    The contribution queries ``silver_stg_*``; gold is rewritten to use a distinct
    CTE instead of DNA ``silver_{source}_{entity}``.
    """
    body = str(gold_sql or "").strip().rstrip(";")
    contrib = str(contribution_sql or "").strip().rstrip(";")
    if not body or not contrib:
        return body
    entity = str(target_entity or "").strip().lower().replace(" ", "_")
    if not entity:
        return body
    dna_table = dna_silver_table_name(source, entity)
    cte_name = f"_kpi_enh_{entity}"
    rewritten = re.sub(rf"\b{re.escape(dna_table)}\b", cte_name, body, flags=re.IGNORECASE)
    cte = f"{cte_name} AS (\n{contrib}\n)"
    with_match = _WITH_RE.match(rewritten)
    if with_match:
        return f"{rewritten[: with_match.end()]}{cte},\n{rewritten[with_match.end() :]}"
    return f"WITH {cte}\n{rewritten}"
