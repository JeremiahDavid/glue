"""Gold-layer catalog browse — preview rows for every certified table output."""

from __future__ import annotations

import re
from typing import Any

from meshflow.dna.schema import DefinitionPack, OutputSpec
from meshflow.dna.settings import DnaSettings
from meshflow.dna.store import load_pack_from_settings
from meshflow.dna.workflow import load_production_pack

CATALOG_PREVIEW_LIMIT = 5
CATALOG_ROOT = "/portal/catalog"


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


def catalog_section_nav(settings: DnaSettings | None) -> tuple[tuple[str, str], ...]:
    if settings is None:
        return ((CATALOG_ROOT, "No tables yet"),)
    items = [
        (f"{CATALOG_ROOT}/{output.id}", _humanize_output_id(output.id))
        for output in list_catalog_tables(settings)
    ]
    return tuple(items) if items else ((CATALOG_ROOT, "No tables yet"),)


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
