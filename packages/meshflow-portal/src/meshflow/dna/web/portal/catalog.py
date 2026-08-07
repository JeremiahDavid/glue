"""Gold-layer catalog browse — preview rows for every certified table output."""

from __future__ import annotations

import re
from typing import Any

from meshflow.dna.field_semantics import discover_silver_columns, list_silver_entities, preview_silver_entity
from meshflow.dna.schema import DefinitionPack, OutputSpec
from meshflow.dna.settings import DnaSettings
from meshflow.dna.store import load_pack_from_settings
from meshflow.dna.workflow import load_production_pack
from meshflow.dna.web.theme import empty_state, escape

CATALOG_PREVIEW_LIMIT = 5
CATALOG_ROOT = "/portal/catalog"
SILVER_CATALOG_ROOT = f"{CATALOG_ROOT}/silver"
GOLD_CATALOG_ROOT = f"{CATALOG_ROOT}/gold"


def _humanize_column(column: str) -> str:
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", column.replace("_", " "))
    return text[:1].upper() + text[1:] if text else column


def _humanize_output_id(output_id: str) -> str:
    text = output_id.removeprefix("out_").replace("_", " ").strip()
    return text.title() if text else output_id


def load_catalog_pack(settings: DnaSettings) -> DefinitionPack:
    try:
        return load_production_pack(settings)
    except Exception:  # noqa: BLE001 — fall back to bundled pack like governance
        return load_pack_from_settings(settings)


def list_catalog_tables(settings: DnaSettings) -> list[OutputSpec]:
    pack = load_catalog_pack(settings)
    return [output for output in pack.outputs if output.output_type == "table"]


def find_catalog_table(settings: DnaSettings, output_id: str) -> OutputSpec | None:
    wanted = str(output_id or "").strip()
    if not wanted:
        return None
    for output in list_catalog_tables(settings):
        if output.id == wanted:
            return output
    return None


def catalog_table_config(output: OutputSpec) -> dict[str, Any]:
    config: dict[str, Any] = {
        "source_output": output.id,
        "limit": CATALOG_PREVIEW_LIMIT,
    }
    if output.columns:
        config["columns"] = [
            {
                "key": column,
                "label": _humanize_column(column),
                "numeric": False,
            }
            for column in output.columns
        ]
    return config


def catalog_table_label(output: OutputSpec) -> str:
    return _humanize_output_id(output.id)


def find_silver_entity(settings: DnaSettings, entity: str) -> str | None:
    wanted = str(entity or "").strip().lower()
    if not wanted:
        return None
    if wanted in list_silver_entities(settings):
        return wanted
    return None


def silver_entity_label(entity: str) -> str:
    return _humanize_column(entity)


def silver_preview_table_html(
    settings: DnaSettings,
    entity: str,
    *,
    empty_title: str = "No rows yet",
    empty_detail: str = "Ingest and consolidate data to preview this silver entity.",
) -> str:
    columns = discover_silver_columns(settings, entity)
    rows = preview_silver_entity(settings, entity, limit=CATALOG_PREVIEW_LIMIT)
    if not columns:
        return empty_state("No columns found", "This silver entity has no discoverable columns yet.")
    if not rows:
        return empty_state(empty_title, empty_detail)

    headers = "".join(f"<th>{escape(_humanize_column(column))}</th>" for column in columns)
    body_rows = ""
    for row in rows:
        if not isinstance(row, dict):
            continue
        cells = "".join(
            f"<td>{escape(str(row.get(column) if row.get(column) is not None else ''))}</td>"
            for column in columns
        )
        body_rows += f"<tr>{cells}</tr>"
    if not body_rows:
        return empty_state(empty_title, empty_detail)

    return f"""
    <p class="section-title" style="margin-top:0">Showing first {CATALOG_PREVIEW_LIMIT} rows · all columns</p>
    <div class="table-wrap">
      <table>
        <thead><tr>{headers}</tr></thead>
        <tbody>{body_rows}</tbody>
      </table>
    </div>
    """
