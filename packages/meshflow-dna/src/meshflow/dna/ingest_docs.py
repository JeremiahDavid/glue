from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from meshflow.dna.schema import DefinitionPack, load_definition_pack, starter_pack_path


KPI_SECTION = re.compile(r"^#+\s*(?:KPI|Metric)\s*[:\-]?\s*(.+)$", re.IGNORECASE | re.MULTILINE)
JOIN_SECTION = re.compile(r"^#+\s*Join\s*[:\-]?\s*(.+)$", re.IGNORECASE | re.MULTILINE)
DEFINITION_LINE = re.compile(r"^\*\*Definition:\*\*\s*(.+)$", re.MULTILINE)
FORMULA_LINE = re.compile(r"^\*\*Formula:\*\*\s*(.+)$", re.MULTILINE)


def _parse_kpi_blocks(text: str) -> list[dict[str, str]]:
    blocks: list[dict[str, str]] = []
    sections = re.split(r"\n(?=#+\s*(?:KPI|Metric))", text, flags=re.IGNORECASE)
    for section in sections:
        title_match = KPI_SECTION.search(section)
        if not title_match:
            continue
        definition_match = DEFINITION_LINE.search(section)
        formula_match = FORMULA_LINE.search(section)
        blocks.append(
            {
                "name": title_match.group(1).strip(),
                "definition": definition_match.group(1).strip() if definition_match else "",
                "formula": formula_match.group(1).strip() if formula_match else "",
            }
        )
    return blocks


def _infer_formula_type(formula: str) -> str:
    lowered = formula.lower()
    if "distinct" in lowered:
        return "count_distinct"
    if "count" in lowered:
        return "count"
    if "average" in lowered or "avg" in lowered:
        return "avg"
    return "sum"


def _slug_kpi_id(name: str, index: int) -> str:
    slug = re.sub(r"[^A-Z0-9]+", "-", name.upper()).strip("-")
    return f"KPI-CUSTOM-{index:02d}" if not slug else f"KPI-{slug[:24]}"


def draft_pack_from_documents(
    *,
    pack_id: str,
    source_system: str,
    document_texts: list[str],
    base_pack_id: str = "bc_intra_v1",
) -> DefinitionPack:
    """Merge customer documentation into a starter pack draft (rule-based v1)."""
    from meshflow.dna.schema import load_definition_pack_file

    base = load_definition_pack_file(starter_pack_path(base_pack_id))
    payload = deepcopy(base.to_dict())
    payload["pack_id"] = pack_id
    payload["version"] = "0.1.0"
    payload["status"] = "draft"
    payload["source_system"] = source_system
    payload["approval"] = {
        "status": "draft",
        "approver": "",
        "approved_at": "",
        "notes": "AI/rule-assisted draft — requires human validation",
    }

    combined = "\n\n".join(document_texts)
    kpi_blocks = _parse_kpi_blocks(combined)
    if kpi_blocks:
        custom_kpis: list[dict[str, Any]] = []
        for index, block in enumerate(kpi_blocks, start=1):
            kpi_id = _slug_kpi_id(block["name"], index)
            custom_kpis.append(
                {
                    "id": kpi_id,
                    "name": block["name"],
                    "definition": block["definition"] or block["formula"] or block["name"],
                    "formula_type": _infer_formula_type(block["formula"] or block["definition"]),
                    "source_output": "out_fact_revenue_lines",
                    "value_column": "amount",
                    "unit": "",
                    "doc_citation": "Customer documentation",
                }
            )
        payload["kpis"] = custom_kpis[:15]
        kpi_ids = [kpi["id"] for kpi in custom_kpis[:15]]
        for output in payload.get("outputs", []):
            if output.get("build") == "kpi_aggregate" and output.get("output_type") == "kpi_snapshot":
                output["kpi_ids"] = kpi_ids
            elif output.get("build") == "kpi_aggregate":
                # Keep starter dimensional outputs only when their KPIs still exist.
                output["kpi_ids"] = [
                    kpi_id for kpi_id in output.get("kpi_ids", []) if kpi_id in kpi_ids
                ]

    payload["source_documents"] = [
        {"title": f"Customer document {index + 1}", "citation": text[:200]}
        for index, text in enumerate(document_texts)
    ]
    payload["changelog"] = [
        {
            "version": "0.1.0",
            "date": "",
            "summary": "Draft generated from customer documentation",
            "author": "dna-ingest-docs",
        }
    ]
    return load_definition_pack(payload)


def draft_pack_from_files(
    *,
    pack_id: str,
    source_system: str,
    paths: list[str],
    base_pack_id: str = "bc_intra_v1",
) -> DefinitionPack:
    texts: list[str] = []
    for path in paths:
        from pathlib import Path

        file_path = Path(path)
        if file_path.is_file():
            texts.append(file_path.read_text(encoding="utf-8"))
    return draft_pack_from_documents(
        pack_id=pack_id,
        source_system=source_system,
        document_texts=texts,
        base_pack_id=base_pack_id,
    )
