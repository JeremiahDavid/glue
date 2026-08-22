"""Suggest reporting table/chart bindings from certified DNA gold outputs."""

from __future__ import annotations

import re
from typing import Any

from hiveflow.dna.schema import DefinitionPack, OutputSpec
from hiveflow.dna.settings import DnaSettings
from hiveflow.dna.workflow import load_production_pack

_DATE_COLUMNS = frozenset(
    {
        "postingDate",
        "orderDate",
        "invoiceDate",
        "dueDate",
        "date",
        "periodStart",
        "periodEnd",
    }
)
_MEASURE_COLUMNS = frozenset(
    {
        "netAmount",
        "grossProfit",
        "lineAmount",
        "backlogAmount",
        "quantity",
        "unitPrice",
        "unitCost",
        "value",
        "value_cy",
        "value_py",
        "delta",
        "amount",
    }
)
_NUMERIC_SUFFIXES = ("Amount", "Cost", "Price", "Qty", "Quantity", "Total", "Balance")
_DIM_JOIN_BY_ID = {
    "customerId": {
        "output": "out_dim_customers",
        "id_column": "customerId",
        "dim_id_column": "id",
        "label_columns": ["displayName", "number"],
        "title_column": "Customer",
    },
    "itemId": {
        "output": "out_dim_items",
        "id_column": "itemId",
        "dim_id_column": "id",
        "label_columns": ["displayName", "number"],
        "title_column": "Item",
    },
}


def _humanize(column: str) -> str:
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", column.replace("_", " "))
    return text[:1].upper() + text[1:] if text else column


def _is_numeric_column(column: str) -> bool:
    if column in _MEASURE_COLUMNS:
        return True
    return any(column.endswith(suffix) for suffix in _NUMERIC_SUFFIXES)


def _find_date_column(columns: list[str]) -> str | None:
    for column in columns:
        if column in _DATE_COLUMNS:
            return column
    for column in columns:
        if "date" in column.lower() or column.lower().endswith("at"):
            return column
    return None


def _find_measure_column(columns: list[str]) -> str | None:
    for column in columns:
        if column in _MEASURE_COLUMNS:
            return column
    for column in columns:
        if _is_numeric_column(column) and column not in _DATE_COLUMNS:
            return column
    return None


def _find_dim_join(columns: list[str]) -> dict[str, Any] | None:
    for id_column, spec in _DIM_JOIN_BY_ID.items():
        if id_column in columns:
            return dict(spec)
    return None


def suggest_table_binding(output: OutputSpec) -> dict[str, Any] | None:
    if output.output_type != "table" or not output.columns:
        return None

    columns = [
        {
            "key": column,
            "label": _humanize(column),
            "numeric": _is_numeric_column(column),
        }
        for column in output.columns
    ]
    binding: dict[str, Any] = {
        "source_output": output.id,
        "columns": columns,
    }

    date_column = _find_date_column(output.columns)
    if date_column:
        binding["sort"] = [{"column": date_column, "direction": "desc"}]

    if output.top_n:
        binding["limit"] = output.top_n
        dim_join = _find_dim_join(output.columns)
        if dim_join:
            binding["dim_join"] = dim_join
    elif output.build == "join":
        binding["limit"] = 500
    else:
        binding["limit"] = 100

    return binding


def suggest_chart_binding(output: OutputSpec) -> dict[str, Any] | None:
    if output.output_type != "table" or output.build != "join" or not output.columns:
        return None
    date_column = _find_date_column(output.columns)
    measure_column = _find_measure_column(output.columns)
    if not date_column or not measure_column:
        return None
    return {
        "type": "bar",
        "title": f"{_humanize(measure_column)} by month",
        "source_output": output.id,
        "dimension": {"column": date_column, "grain": "month"},
        "measure": {"column": measure_column, "aggregation": "sum"},
        "limit": 12,
        "show_summary": True,
    }


def suggest_section_binding(output: OutputSpec, pack: DefinitionPack) -> dict[str, Any] | None:
    if output.output_type != "table":
        return None
    if output.top_n and _find_dim_join(output.columns or []):
        table = suggest_table_binding(output)
        if not table:
            return None
        return {
            "layout": "ranked_table",
            "table": table,
        }
    if output.kpi_ids:
        kpi_ids = list(output.kpi_ids)
        is_compare = False
        for kpi_id in kpi_ids:
            try:
                if pack.kpi_by_id(kpi_id).formula_type == "period_compare":
                    is_compare = True
                    break
            except KeyError:
                continue
        layout = "compare_kpi_grid" if is_compare else "kpi_grid"
        section: dict[str, Any] = {
            "layout": layout,
            "bindings": [{"source_output": output.id, "kpi_ids": kpi_ids}],
        }
        return section
    return None


def catalog_gold_outputs(pack: DefinitionPack) -> list[dict[str, Any]]:
    catalog: list[dict[str, Any]] = []
    for output in pack.outputs:
        entry: dict[str, Any] = {
            "output_id": output.id,
            "output_type": output.output_type,
            "build": output.build,
            "columns": list(output.columns),
            "top_n": output.top_n,
            "kpi_ids": list(output.kpi_ids),
        }
        table = suggest_table_binding(output)
        if table:
            entry["suggested_table"] = table
        chart = suggest_chart_binding(output)
        if chart:
            entry["suggested_chart"] = chart
        section = suggest_section_binding(output, pack)
        if section:
            entry["suggested_section"] = section
        catalog.append(entry)
    return catalog


def build_reporting_binding_catalog(settings: DnaSettings) -> dict[str, Any]:
    pack = load_production_pack(settings)
    return {
        "pack_id": pack.pack_id,
        "pack_version": pack.version,
        "outputs": catalog_gold_outputs(pack),
    }
