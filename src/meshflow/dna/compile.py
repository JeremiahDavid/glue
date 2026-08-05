from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from meshflow.dna.calendar import attach_period_columns
from meshflow.dna.schema import (
    BuildType,
    DefinitionPack,
    FormulaType,
    KpiSpec,
    OutputSpec,
)
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


def _maybe_attach_periods(
    pack: DefinitionPack,
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    calendar = pack.calendar
    if calendar is None:
        return rows
    return attach_period_columns(
        rows,
        date_column=calendar.date_column,
        fiscal_year_start_month=calendar.fiscal_year_start_month,
        period_grain=calendar.period_grain,
    )


def _filter_rows(kpi: KpiSpec, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not kpi.filter_column:
        return rows
    return [row for row in rows if row.get(kpi.filter_column) == kpi.filter_value]


def _apply_kpi_formula(kpi: KpiSpec, rows: list[dict[str, Any]]) -> float:
    filtered = _filter_rows(kpi, rows)

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


def _format_payload(kpi: KpiSpec) -> dict[str, Any] | None:
    if kpi.format is None:
        return None
    return kpi.format.to_dict()


def _apply_format_fields(row: dict[str, Any], kpi: KpiSpec, fallback: KpiSpec | None = None) -> None:
    fmt = _format_payload(kpi) or (_format_payload(fallback) if fallback else None)
    if not fmt:
        return
    row["format_type"] = fmt["type"]
    row["format_decimal_places"] = fmt["decimal_places"]
    row["format_scale"] = fmt["scale"]


def _resolve_measure_kpi(pack: DefinitionPack, kpi: KpiSpec) -> KpiSpec:
    if kpi.formula_type != FormulaType.PERIOD_COMPARE.value:
        return kpi
    base = pack.kpi_by_id(kpi.base_kpi)
    return KpiSpec(
        id=base.id,
        name=base.name,
        definition=base.definition,
        formula_type=base.formula_type,
        source_output=base.source_output or kpi.source_output,
        value_column=base.value_column or kpi.value_column,
        unit=base.unit or kpi.unit,
        filter_column=base.filter_column or kpi.filter_column,
        filter_value=base.filter_value if base.filter_column else kpi.filter_value,
        doc_citation=base.doc_citation,
        group_by=list(kpi.group_by or base.group_by),
        time=kpi.time or base.time,
        format=kpi.format or base.format,
    )


def _aggregate_by_grain(
    measure: KpiSpec,
    rows: list[dict[str, Any]],
    *,
    group_by: list[str],
    include_period: bool,
) -> dict[tuple[Any, ...], float]:
    filtered = _filter_rows(measure, rows)
    grain_cols = list(group_by)
    if include_period:
        grain_cols.append("period_key")

    buckets: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in filtered:
        if include_period and row.get("period_key") is None:
            continue
        key = tuple(row.get(column) for column in grain_cols)
        buckets[key].append(row)

    totals: dict[tuple[Any, ...], float] = {}
    for key, bucket_rows in buckets.items():
        totals[key] = _apply_kpi_formula(measure, bucket_rows)
    return totals


def _ytd_totals(
    period_totals: dict[tuple[Any, ...], float],
    *,
    group_by_len: int,
    rows_by_period: dict[str, dict[str, Any]],
) -> dict[tuple[Any, ...], float]:
    """Roll period totals into YTD using fiscal_period order within each fiscal_year."""
    # key = group_by... + period_key
    by_group_year: dict[tuple[Any, ...], list[tuple[int, str, float]]] = defaultdict(list)
    for key, value in period_totals.items():
        group_key = key[:group_by_len]
        period_key = str(key[group_by_len])
        meta = rows_by_period.get(period_key, {})
        fiscal_year = meta.get("fiscal_year")
        fiscal_period = meta.get("fiscal_period")
        if fiscal_year is None or fiscal_period is None:
            continue
        by_group_year[(*group_key, fiscal_year)].append((int(fiscal_period), period_key, value))

    ytd: dict[tuple[Any, ...], float] = {}
    for group_year, periods in by_group_year.items():
        group_key = group_year[:-1]
        running = 0.0
        for _period_num, period_key, value in sorted(periods, key=lambda item: item[0]):
            running += value
            ytd[(*group_key, period_key)] = running
    return ytd


def _period_meta_index(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for row in rows:
        period_key = row.get("period_key")
        if period_key and period_key not in index:
            index[str(period_key)] = {
                "fiscal_year": row.get("fiscal_year"),
                "fiscal_period": row.get("fiscal_period"),
                "prior_year_period_key": row.get("prior_year_period_key"),
            }
    return index


def _build_dimensional_kpi_rows(
    pack: DefinitionPack,
    kpi: KpiSpec,
    source_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    measure = _resolve_measure_kpi(pack, kpi)
    group_by = list(kpi.group_by or measure.group_by)
    window = (kpi.time.window if kpi.time else None) or (
        measure.time.window if measure.time else "period"
    )
    period_meta = _period_meta_index(source_rows)
    period_totals = _aggregate_by_grain(
        measure,
        source_rows,
        group_by=group_by,
        include_period=True,
    )
    if window == "ytd":
        totals = _ytd_totals(period_totals, group_by_len=len(group_by), rows_by_period=period_meta)
    else:
        totals = period_totals

    if kpi.formula_type != FormulaType.PERIOD_COMPARE.value:
        rows: list[dict[str, Any]] = []
        for key, value in sorted(totals.items(), key=lambda item: [str(part) for part in item[0]]):
            period_key = str(key[-1])
            meta = period_meta.get(period_key, {})
            row: dict[str, Any] = {
                "kpi_id": kpi.id,
                "kpi_name": kpi.name,
                "period_key": period_key,
                "fiscal_year": meta.get("fiscal_year"),
                "fiscal_period": meta.get("fiscal_period"),
                "value": value,
                "unit": kpi.unit or measure.unit,
                "pack_id": pack.pack_id,
                "pack_version": pack.version,
            }
            for index, column in enumerate(group_by):
                row[column] = key[index]
            _apply_format_fields(row, kpi, measure)
            rows.append(row)
        return rows

    compare = kpi.compare or "prior_year"
    result_fields = kpi.result or ["current", "prior", "delta", "pct_change"]
    compare_rows: list[dict[str, Any]] = []

    for key, value_cy in sorted(totals.items(), key=lambda item: [str(part) for part in item[0]]):
        period_key = str(key[-1])
        meta = period_meta.get(period_key, {})
        if compare == "prior_year":
            prior_key_period = meta.get("prior_year_period_key")
        else:
            # prior_period: same group, previous fiscal_period within sequence via period_key map
            prior_key_period = None
            fiscal_period = meta.get("fiscal_period")
            fiscal_year = meta.get("fiscal_year")
            if isinstance(fiscal_period, int) and fiscal_period > 1 and fiscal_year is not None:
                # reconstruct prior period_key pattern from current key
                if "-Q" in period_key:
                    prior_key_period = f"FY{fiscal_year}-Q{fiscal_period - 1:02d}"
                else:
                    prior_key_period = f"FY{fiscal_year}-P{fiscal_period - 1:02d}"
            elif isinstance(fiscal_period, int) and fiscal_period == 1 and fiscal_year is not None:
                grain = pack.calendar.period_grain if pack.calendar else "month"
                last_period = 4 if grain == "quarter" else 12
                suffix = "Q" if grain == "quarter" else "P"
                prior_key_period = f"FY{fiscal_year - 1}-{suffix}{last_period:02d}"

        prior_tuple = (*key[:-1], prior_key_period) if prior_key_period else None
        value_py = totals.get(prior_tuple) if prior_tuple else None

        row: dict[str, Any] = {
            "kpi_id": kpi.id,
            "kpi_name": kpi.name,
            "period_key": period_key,
            "fiscal_year": meta.get("fiscal_year"),
            "fiscal_period": meta.get("fiscal_period"),
            "prior_period_key": prior_key_period,
            "unit": kpi.unit or measure.unit,
            "pack_id": pack.pack_id,
            "pack_version": pack.version,
            "compare": compare,
        }
        for index, column in enumerate(group_by):
            row[column] = key[index]

        if "current" in result_fields:
            row["value_cy"] = value_cy
        if "prior" in result_fields:
            row["value_py"] = value_py
        if "delta" in result_fields:
            row["delta"] = None if value_py is None else value_cy - value_py
        if "pct_change" in result_fields:
            if value_py in (None, 0):
                row["pct_change"] = None
            else:
                row["pct_change"] = (value_cy - value_py) / value_py

        _apply_format_fields(row, kpi, measure)
        compare_rows.append(row)

    return compare_rows


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
        joined = _maybe_attach_periods(pack, joined)
        if output.columns:
            # Keep declared columns plus any period attrs when calendar is configured.
            columns = list(output.columns)
            if pack.calendar is not None:
                for period_col in (
                    "fiscal_year",
                    "fiscal_period",
                    "period_key",
                    "prior_year_period_key",
                ):
                    if period_col not in columns:
                        columns.append(period_col)
            return _subset_columns(joined, columns)
        return joined

    if output.build == BuildType.KPI_AGGREGATE.value:
        as_of = datetime.now(UTC).isoformat()
        snapshot_rows: list[dict[str, Any]] = []
        dimensional_rows: list[dict[str, Any]] = []

        for kpi_id in output.kpi_ids:
            kpi = next(item for item in pack.kpis if item.id == kpi_id)
            if kpi.is_dimensional() or kpi.formula_type == FormulaType.PERIOD_COMPARE.value:
                measure = _resolve_measure_kpi(pack, kpi)
                source_rows = _resolve_kpi_rows(pack, measure, compiled, settings)
                dimensional_rows.extend(_build_dimensional_kpi_rows(pack, kpi, source_rows))
                continue

            source_rows = _resolve_kpi_rows(pack, kpi, compiled, settings)
            value = _apply_kpi_formula(kpi, source_rows)
            row: dict[str, Any] = {
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
            _apply_format_fields(row, kpi)
            snapshot_rows.append(row)

        if dimensional_rows and snapshot_rows:
            raise ValueError(
                f"Output {output.id!r} mixes scalar and dimensional KPIs; "
                "split them into separate outputs"
            )
        return dimensional_rows or snapshot_rows

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
