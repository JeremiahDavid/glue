"""Reporting layout cookbook and KPI hints for the Config Assistant."""

from __future__ import annotations

from typing import Any

from meshflow.dna.settings import DnaSettings
from meshflow.dna.workflow import load_production_pack

# Compact, stable reference — derived from reporting-pack.schema.json and dbc_reporting_boilerplate.yaml.
REPORTING_LAYOUT_COOKBOOK = """
Reporting pack structure:
- Top level: pack_id, version, status, pages[], optional include_chart_catalog, changelog
- Page: id, title, path, pillar, description, sections[] OR page-level tables[] / charts[]
- Section: id, title, layout (required), plus layout-specific fields below

Section layouts (use exactly these layout values):
1. kpi_grid — snapshot KPI cards
   - bindings[]: { source_output, kpi_ids[] }
   - Example outputs: out_kpi_snapshot, out_executive_snapshot

2. compare_kpi_grid — YoY compare cards (CY vs PY with delta %)
   - bindings[]: { source_output, filter: { window: mtd|qtd|ytd }, kpi_ids[] }
   - Example output: out_executive_kpis

3. ranked_table — top-N YoY ranking (auto columns: name, CY YTD, PY YTD, delta, %)
   - table: { source_output, limit, dim_join }
   - Do NOT use columns[] for the name — use dim_join to resolve IDs to labels
   - dim_join: { output, id_column, dim_id_column, label_columns[], title_column }
     - id_column: join key on the ranking output (e.g. customerId, itemId)
     - dim_id_column: REQUIRED for out_dim_* — PK on the dimension output is usually `id`
       (not customerId/itemId). Omitting it shows raw IDs instead of names.
     - label_columns: dimension fields shown in the first column (joined with " · ")
     - title_column: header for the first column
   - Example: show customer name only → label_columns: [displayName] + dim_id_column: id
   - Example: name + number → label_columns: [displayName, number] + dim_id_column: id

4. ranked_table_group — side-by-side ranked tables
   - tables[]: each entry has title, source_output, limit, dim_join (same as ranked_table)

5. table — flat fact/detail table
   - table: { source_output, columns[], sort[], limit }
   - columns[]: { key, label, numeric? } — use when the gold output already has display fields

6. chart — bar/line chart section
   - chart: { type: bar|line, title, source_output, dimension, measure, limit, show_summary? }

Page-level tables/charts (no section wrapper):
- pages[].tables[] and pages[].charts[] use the same table/chart objects as sections

Common user requests → correct edit target:
- "Show customer name instead of ID in top customers" → dim_join with dim_id_column: id and label_columns: [displayName] (not columns[])
- "Add a revenue detail page" → page with tables[] and explicit columns from out_fact_revenue_lines
- "Add MTD KPIs" → compare_kpi_grid section with filter.window: mtd and matching kpi_ids
- "Change how many rows" → table.limit
- "Reorder columns on detail table" → reorder columns[] keys

Dimension join reference (BC boilerplate):
- customerId on fact/ranking → out_dim_customers (dim key: id, labels: displayName, number)
- itemId on fact/ranking → out_dim_items (dim key: id, labels: displayName, number)

Preserve on edit:
- pack_id unchanged; bump version only for changed pack
- source_output ids must match certified gold outputs from the binding catalog
- pillar values: summary, executive, sales, operations, finance, inventory, developer
""".strip()


def build_kpi_binding_hints(settings: DnaSettings) -> list[dict[str, Any]]:
    """KPI ids grouped by gold output — helps compare_kpi_grid / kpi_grid bindings."""
    pack = load_production_pack(settings)
    hints: list[dict[str, Any]] = []
    for output in pack.outputs:
        if not output.kpi_ids:
            continue
        kpi_meta: list[dict[str, Any]] = []
        for kpi_id in output.kpi_ids:
            try:
                kpi = pack.kpi_by_id(kpi_id)
            except KeyError:
                kpi_meta.append({"kpi_id": kpi_id})
                continue
            entry: dict[str, Any] = {
                "kpi_id": kpi.id,
                "name": kpi.name,
                "formula_type": kpi.formula_type,
            }
            if kpi.time and kpi.time.window:
                entry["window"] = kpi.time.window
            if kpi.group_by:
                entry["group_by"] = list(kpi.group_by)
            kpi_meta.append(entry)
        hints.append(
            {
                "output_id": output.id,
                "output_type": output.output_type,
                "top_n": output.top_n,
                "kpis": kpi_meta,
            }
        )
    return hints


def build_reporting_assistant_context(settings: DnaSettings) -> dict[str, Any]:
    """Structured reporting knowledge for the Config Assistant system prompt."""
    try:
        kpi_hints = build_kpi_binding_hints(settings)
    except Exception:  # noqa: BLE001 — hints are advisory
        kpi_hints = []
    return {
        "layout_cookbook": REPORTING_LAYOUT_COOKBOOK,
        "kpi_binding_hints": kpi_hints,
    }
