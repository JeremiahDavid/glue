from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from meshflow.dna.schema import BuildType, DefinitionPack, FormulaType, KpiSpec, OutputSpec
from meshflow.dna.settings import DnaSettings
from meshflow.dna.store import load_pack_from_settings, read_silver_entity, write_staging_output


def _subset_columns(rows: list[dict[str, Any]], columns: list[str]) -> list[dict[str, Any]]:
    if not columns:
        return rows
    result: list[dict[str, Any]] = []
    for row in rows:
        result.append({column: row.get(column) for column in columns if column in row})
    return result


def _join_rows(
    left_rows: list[dict[str, Any]],
    right_rows: list[dict[str, Any]],
    left_key: str,
    right_key: str,
) -> list[dict[str, Any]]:
    right_index: dict[Any, dict[str, Any]] = {}
    for row in right_rows:
        key = row.get(right_key)
        if key is not None:
            right_index[key] = row

    joined: list[dict[str, Any]] = []
    for left in left_rows:
        merged = dict(left)
        match = right_index.get(left.get(left_key))
        if match:
            for key, value in match.items():
                if key in merged and key not in {left_key, right_key}:
                    merged[f"right_{key}"] = value
                elif key not in merged:
                    merged[key] = value
        joined.append(merged)
    return joined


def _coerce_number(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _apply_kpi_formula(kpi: KpiSpec, rows: list[dict[str, Any]]) -> float:
    filtered = rows
    if kpi.filter_column:
        filtered = [
            row
            for row in rows
            if row.get(kpi.filter_column) == kpi.filter_value
        ]

    if kpi.formula_type == FormulaType.SUM.value:
        return sum(_coerce_number(row.get(kpi.value_column)) for row in filtered)
    if kpi.formula_type == FormulaType.COUNT.value:
        return float(len(filtered))
    if kpi.formula_type == FormulaType.COUNT_DISTINCT.value:
        values = {row.get(kpi.value_column) for row in filtered if row.get(kpi.value_column) is not None}
        return float(len(values))
    if kpi.formula_type == FormulaType.AVG.value:
        numbers = [_coerce_number(row.get(kpi.value_column)) for row in filtered]
        return sum(numbers) / len(numbers) if numbers else 0.0
    raise ValueError(f"Unsupported formula type {kpi.formula_type!r} for KPI {kpi.id}")


def _resolve_kpi_rows(
    pack: DefinitionPack,
    kpi: KpiSpec,
    compiled: dict[str, list[dict[str, Any]]],
    settings: DnaSettings,
) -> list[dict[str, Any]]:
    source = kpi.source_output
    if source in compiled:
        return compiled[source]
    try:
        entity = pack.entity_by_id(source)
    except KeyError:
        try:
            output = pack.output_by_id(source)
            return compiled.get(output.id, [])
        except KeyError:
            pass
        entity = None
    if entity is not None:
        return read_silver_entity(settings, entity.silver_entity)
    return read_silver_entity(settings, source)


def _build_output(
    pack: DefinitionPack,
    output: OutputSpec,
    settings: DnaSettings,
    compiled: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    if output.build == BuildType.ENTITY_COPY.value:
        entity = pack.entity_by_id(output.entity_id)
        rows = read_silver_entity(settings, entity.silver_entity)
        return _subset_columns(rows, output.columns)

    if output.build == BuildType.JOIN.value:
        join = pack.join_by_id(output.join_id)
        left_entity = pack.entity_by_id(join.left_entity)
        right_entity = pack.entity_by_id(join.right_entity)
        left_rows = read_silver_entity(settings, left_entity.silver_entity)
        right_rows = read_silver_entity(settings, right_entity.silver_entity)
        joined = _join_rows(left_rows, right_rows, join.left_key, join.right_key)
        return _subset_columns(joined, output.columns)

    if output.build == BuildType.KPI_AGGREGATE.value:
        snapshot_rows: list[dict[str, Any]] = []
        as_of = datetime.now(UTC).isoformat()
        for kpi_id in output.kpi_ids:
            kpi = next(item for item in pack.kpis if item.id == kpi_id)
            source_rows = _resolve_kpi_rows(pack, kpi, compiled, settings)
            value = _apply_kpi_formula(kpi, source_rows)
            snapshot_rows.append(
                {
                    "kpi_id": kpi.id,
                    "kpi_name": kpi.name,
                    "definition": kpi.definition,
                    "value": value,
                    "unit": kpi.unit,
                    "formula_type": kpi.formula_type,
                    "source_output": kpi.source_output,
                    "pack_id": pack.pack_id,
                    "pack_version": pack.version,
                    "as_of": as_of,
                }
            )
        return snapshot_rows

    raise ValueError(f"Unsupported build type {output.build!r} for output {output.id}")


def compile_pack(settings: DnaSettings, pack: DefinitionPack | None = None) -> dict[str, Any]:
    if pack is None:
        pack = load_pack_from_settings(settings)

    if not pack.is_publishable():
        raise ValueError(
            f"Definition pack {pack.pack_id} v{pack.version} is not publishable "
            f"(approval status={pack.approval.status!r})"
        )

    compiled: dict[str, list[dict[str, Any]]] = {}
    manifest_outputs: list[dict[str, Any]] = []

    for output in pack.outputs:
        if output.build == BuildType.KPI_AGGREGATE.value:
            continue
        rows = _build_output(pack, output, settings, compiled)
        path = write_staging_output(settings, output.id, rows)
        compiled[output.id] = rows
        manifest_outputs.append(
            {
                "output_id": output.id,
                "build": output.build,
                "row_count": len(rows),
                "path": path,
            }
        )

    for output in pack.outputs:
        if output.build != BuildType.KPI_AGGREGATE.value:
            continue
        rows = _build_output(pack, output, settings, compiled)
        path = write_staging_output(settings, output.id, rows)
        compiled[output.id] = rows
        manifest_outputs.append(
            {
                "output_id": output.id,
                "build": output.build,
                "row_count": len(rows),
                "path": path,
            }
        )

    compiler_hash = hashlib.sha256(
        json.dumps(pack.to_dict(), sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]

    manifest = {
        "status": "compiled",
        "pack_id": pack.pack_id,
        "pack_version": pack.version,
        "source_system": pack.source_system,
        "compiler_hash": compiler_hash,
        "compiled_at": datetime.now(UTC).isoformat(),
        "outputs": manifest_outputs,
    }
    return manifest
