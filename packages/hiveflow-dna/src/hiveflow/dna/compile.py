from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import datetime
from hiveflow.compat import UTC
from typing import Any

from hiveflow.dna.calendar import attach_period_columns, period_attrs_for_date
from hiveflow.dna.schema import (
    BuildType,
    DefinitionPack,
    FormulaType,
    KpiSpec,
    OutputSpec,
)
from hiveflow.dna.settings import DnaSettings
from hiveflow.dna.store import load_pack_from_settings, read_silver_entity, write_staging_output


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


def _apply_kpi_formula(
    kpi: KpiSpec,
    rows: list[dict[str, Any]],
    *,
    pack: DefinitionPack | None = None,
) -> float:
    filtered = _filter_rows(kpi, rows)

    if kpi.formula_type == FormulaType.RATIO.value:
        if pack is None:
            raise ValueError(f"Ratio KPI {kpi.id!r} requires pack context")
        numerator = pack.kpi_by_id(kpi.numerator_kpi)
        denominator = pack.kpi_by_id(kpi.denominator_kpi)
        num_val = _apply_kpi_formula(numerator, filtered, pack=pack)
        den_val = _apply_kpi_formula(denominator, filtered, pack=pack)
        return num_val / den_val if den_val else 0.0

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
        numerator_kpi=base.numerator_kpi,
        denominator_kpi=base.denominator_kpi,
        time=kpi.time or base.time,
        format=kpi.format or base.format,
    )


def _aggregate_by_grain(
    measure: KpiSpec,
    rows: list[dict[str, Any]],
    *,
    group_by: list[str],
    include_period: bool,
    pack: DefinitionPack | None = None,
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
        totals[key] = _apply_kpi_formula(measure, bucket_rows, pack=pack)
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


def _fiscal_quarter(fiscal_period: int) -> int:
    return (int(fiscal_period) - 1) // 3 + 1


def _qtd_totals(
    period_totals: dict[tuple[Any, ...], float],
    *,
    group_by_len: int,
    rows_by_period: dict[str, dict[str, Any]],
) -> dict[tuple[Any, ...], float]:
    """Roll monthly period totals into QTD through each month in the quarter."""
    by_group_year_quarter: dict[tuple[Any, ...], list[tuple[int, str, float]]] = defaultdict(list)
    for key, value in period_totals.items():
        group_key = key[:group_by_len]
        period_key = str(key[group_by_len])
        meta = rows_by_period.get(period_key, {})
        fiscal_year = meta.get("fiscal_year")
        fiscal_period = meta.get("fiscal_period")
        if fiscal_year is None or fiscal_period is None:
            continue
        quarter = _fiscal_quarter(int(fiscal_period))
        by_group_year_quarter[(*group_key, fiscal_year, quarter)].append(
            (int(fiscal_period), period_key, value)
        )

    qtd: dict[tuple[Any, ...], float] = {}
    for group_year_quarter, periods in by_group_year_quarter.items():
        group_key = group_year_quarter[:-2]
        running = 0.0
        for _period_num, period_key, value in sorted(periods, key=lambda item: item[0]):
            running += value
            qtd[(*group_key, period_key)] = running
    return qtd


def _current_period_key(pack: DefinitionPack, as_of: datetime) -> str:
    calendar = pack.calendar
    if calendar is None:
        raise ValueError("Pack calendar required for mtd/qtd/ytd executive windows")
    attrs = period_attrs_for_date(
        as_of.date(),
        fiscal_year_start_month=calendar.fiscal_year_start_month,
        period_grain=calendar.period_grain,
    )
    return attrs.period_key


def _ensure_period_meta(
    pack: DefinitionPack,
    period_meta: dict[str, dict[str, Any]],
    period_key: str,
    as_of: datetime,
) -> dict[str, Any]:
    existing = period_meta.get(period_key)
    if existing is not None:
        return existing
    calendar = pack.calendar
    if calendar is None:
        return {}
    attrs = period_attrs_for_date(
        as_of.date(),
        fiscal_year_start_month=calendar.fiscal_year_start_month,
        period_grain=calendar.period_grain,
    )
    if attrs.period_key != period_key:
        # as_of only synthesizes the current period; other keys stay unknown
        return {}
    meta = {
        "fiscal_year": attrs.fiscal_year,
        "fiscal_period": attrs.fiscal_period,
        "prior_year_period_key": attrs.prior_year_period_key,
    }
    period_meta[period_key] = meta
    prior_key = attrs.prior_year_period_key
    if prior_key and prior_key not in period_meta:
        period_meta[prior_key] = {
            "fiscal_year": attrs.fiscal_year - 1,
            "fiscal_period": attrs.fiscal_period,
            "prior_year_period_key": (
                f"FY{attrs.fiscal_year - 2}-"
                f"{'Q' if calendar.period_grain == 'quarter' else 'P'}"
                f"{attrs.fiscal_period:02d}"
            ),
        }
    return meta


def _value_at_period(
    totals: dict[tuple[Any, ...], float],
    *,
    group_key: tuple[Any, ...],
    period_key: str,
    window: str,
    period_meta: dict[str, dict[str, Any]],
) -> float:
    """Resolve a windowed total for period_key, carrying forward through quiet months.

    MTD with no activity in the target month is 0. YTD/QTD reuse the latest
    rolled-up total in the same year (and quarter for QTD) at or before the
    target fiscal period so as-of gaps do not blank the executive dashboard.
    """
    direct = totals.get((*group_key, period_key))
    if direct is not None:
        return direct
    if window == "mtd":
        return 0.0

    target = period_meta.get(period_key) or {}
    target_year = target.get("fiscal_year")
    target_period = target.get("fiscal_period")
    if target_year is None or target_period is None:
        return 0.0
    target_period_num = int(target_period)
    target_quarter = _fiscal_quarter(target_period_num)

    best_period = -1
    best_value = 0.0
    for key, value in totals.items():
        if key[: len(group_key)] != group_key:
            continue
        candidate_period = str(key[len(group_key)])
        meta = period_meta.get(candidate_period) or {}
        if meta.get("fiscal_year") != target_year:
            continue
        fiscal_period = meta.get("fiscal_period")
        if fiscal_period is None:
            continue
        period_num = int(fiscal_period)
        if period_num <= 0 or period_num > target_period_num:
            continue
        if window == "qtd" and _fiscal_quarter(period_num) != target_quarter:
            continue
        if period_num > best_period:
            best_period = period_num
            best_value = value
    return best_value


def _group_keys_for_current_period(
    totals: dict[tuple[Any, ...], float],
    *,
    group_by_len: int,
    window: str,
    current_period: str,
    period_meta: dict[str, dict[str, Any]],
) -> list[tuple[Any, ...]]:
    if group_by_len == 0:
        return [()]

    current = period_meta.get(current_period) or {}
    current_year = current.get("fiscal_year")
    current_period_num = current.get("fiscal_period")
    current_quarter = (
        _fiscal_quarter(int(current_period_num)) if current_period_num is not None else None
    )

    keys: set[tuple[Any, ...]] = set()
    for key in totals:
        group_key = key[:group_by_len]
        period_key = str(key[group_by_len])
        if window == "mtd":
            if period_key == current_period:
                keys.add(group_key)
            continue
        meta = period_meta.get(period_key) or {}
        if meta.get("fiscal_year") != current_year:
            continue
        fiscal_period = meta.get("fiscal_period")
        if fiscal_period is None or current_period_num is None:
            continue
        if int(fiscal_period) > int(current_period_num):
            continue
        if window == "qtd" and _fiscal_quarter(int(fiscal_period)) != current_quarter:
            continue
        keys.add(group_key)
    return sorted(keys, key=lambda item: [str(part) for part in item])


def _apply_time_window(
    period_totals: dict[tuple[Any, ...], float],
    *,
    window: str,
    group_by_len: int,
    rows_by_period: dict[str, dict[str, Any]],
) -> dict[tuple[Any, ...], float]:
    if window == "ytd":
        return _ytd_totals(
            period_totals,
            group_by_len=group_by_len,
            rows_by_period=rows_by_period,
        )
    if window == "qtd":
        return _qtd_totals(
            period_totals,
            group_by_len=group_by_len,
            rows_by_period=rows_by_period,
        )
    return period_totals


def _enrich_revenue_fact_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        quantity = _coerce_number(item.get("quantity"))
        unit_cost = _coerce_number(item.get("unitCost"))
        net_amount = _coerce_number(item.get("netAmount"))
        cost_amount = quantity * unit_cost
        item["costAmount"] = cost_amount
        item["grossProfit"] = net_amount - cost_amount
        enriched.append(item)
    return enriched


def _enrich_order_fact_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        quantity = _coerce_number(item.get("quantity"))
        unit_price = _coerce_number(item.get("unitPrice"))
        line_amount = _coerce_number(item.get("lineAmount"))
        if line_amount == 0.0 and quantity and unit_price:
            line_amount = quantity * unit_price
        outstanding = _coerce_number(item.get("outstandingQuantity"))
        if outstanding == 0.0:
            outstanding = quantity
        item["lineAmount"] = line_amount
        item["outstandingQuantity"] = outstanding
        item["backlogAmount"] = outstanding * unit_price if unit_price else line_amount
        enriched.append(item)
    return enriched


def _attach_periods_for_column(
    pack: DefinitionPack,
    rows: list[dict[str, Any]],
    date_column: str,
) -> list[dict[str, Any]]:
    calendar = pack.calendar
    if calendar is None:
        return rows
    return attach_period_columns(
        rows,
        date_column=date_column,
        fiscal_year_start_month=calendar.fiscal_year_start_month,
        period_grain=calendar.period_grain,
    )


def _limit_ranked_rows(rows: list[dict[str, Any]], top_n: int | None) -> list[dict[str, Any]]:
    if not top_n or top_n <= 0:
        return rows
    ranked = sorted(
        rows,
        key=lambda row: _coerce_number(row.get("value_cy", row.get("value"))),
        reverse=True,
    )
    return ranked[:top_n]


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
    *,
    as_of: datetime | None = None,
    top_n: int | None = None,
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
        pack=pack,
    )
    totals = _apply_time_window(
        period_totals,
        window=window,
        group_by_len=len(group_by),
        rows_by_period=period_meta,
    )

    as_of_dt = as_of or datetime.now(UTC)
    current_period: str | None = None
    if window in {"mtd", "qtd", "ytd"} and pack.calendar is not None:
        current_period = _current_period_key(pack, as_of_dt)
        _ensure_period_meta(pack, period_meta, current_period, as_of_dt)

    def _emit_scalar_row(group_key: tuple[Any, ...], period_key: str, value: float) -> dict[str, Any]:
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
            "window": window,
        }
        for index, column in enumerate(group_by):
            row[column] = group_key[index]
        _apply_format_fields(row, kpi, measure)
        return row

    if kpi.formula_type != FormulaType.PERIOD_COMPARE.value:
        rows: list[dict[str, Any]] = []
        if current_period:
            group_keys = _group_keys_for_current_period(
                totals,
                group_by_len=len(group_by),
                window=window,
                current_period=current_period,
                period_meta=period_meta,
            )
            for group_key in group_keys:
                value = _value_at_period(
                    totals,
                    group_key=group_key,
                    period_key=current_period,
                    window=window,
                    period_meta=period_meta,
                )
                if group_by and window == "mtd" and value == 0.0:
                    continue
                rows.append(_emit_scalar_row(group_key, current_period, value))
        else:
            for key, value in sorted(totals.items(), key=lambda item: [str(part) for part in item[0]]):
                period_key = str(key[-1])
                rows.append(_emit_scalar_row(key[:-1], period_key, value))
        return _limit_ranked_rows(rows, top_n)

    compare = kpi.compare or "prior_year"
    result_fields = kpi.result or ["current", "prior", "delta", "pct_change"]
    compare_rows: list[dict[str, Any]] = []

    def _prior_period_key(period_key: str, meta: dict[str, Any]) -> str | None:
        if compare == "prior_year":
            return meta.get("prior_year_period_key")
        fiscal_period = meta.get("fiscal_period")
        fiscal_year = meta.get("fiscal_year")
        if isinstance(fiscal_period, int) and fiscal_period > 1 and fiscal_year is not None:
            if "-Q" in period_key:
                return f"FY{fiscal_year}-Q{fiscal_period - 1:02d}"
            return f"FY{fiscal_year}-P{fiscal_period - 1:02d}"
        if isinstance(fiscal_period, int) and fiscal_period == 1 and fiscal_year is not None:
            grain = pack.calendar.period_grain if pack.calendar else "month"
            last_period = 4 if grain == "quarter" else 12
            suffix = "Q" if grain == "quarter" else "P"
            return f"FY{fiscal_year - 1}-{suffix}{last_period:02d}"
        return None

    def _emit_compare_row(group_key: tuple[Any, ...], period_key: str, value_cy: float) -> dict[str, Any]:
        meta = period_meta.get(period_key, {})
        prior_key_period = _prior_period_key(period_key, meta)
        value_py: float | None = None
        if prior_key_period:
            if compare == "prior_year" and window in {"mtd", "qtd", "ytd"}:
                value_py = _value_at_period(
                    totals,
                    group_key=group_key,
                    period_key=prior_key_period,
                    window=window,
                    period_meta=period_meta,
                )
                # Carry-forward returns 0 when PY has no activity in-scope; treat
                # that as a real zero for YoY math on executive windows.
            else:
                value_py = totals.get((*group_key, prior_key_period))

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
            "window": window,
        }
        for index, column in enumerate(group_by):
            row[column] = group_key[index]

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
        return row

    if current_period:
        group_keys = _group_keys_for_current_period(
            totals,
            group_by_len=len(group_by),
            window=window,
            current_period=current_period,
            period_meta=period_meta,
        )
        for group_key in group_keys:
            value_cy = _value_at_period(
                totals,
                group_key=group_key,
                period_key=current_period,
                window=window,
                period_meta=period_meta,
            )
            if group_by and window == "mtd" and value_cy == 0.0:
                continue
            compare_rows.append(_emit_compare_row(group_key, current_period, value_cy))
    else:
        for key, value_cy in sorted(totals.items(), key=lambda item: [str(part) for part in item[0]]):
            period_key = str(key[-1])
            compare_rows.append(_emit_compare_row(key[:-1], period_key, value_cy))

    return _limit_ranked_rows(compare_rows, top_n)


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
        if output.id == "out_fact_order_lines":
            joined = _attach_periods_for_column(pack, joined, "orderDate")
        else:
            joined = _maybe_attach_periods(pack, joined)
        if output.id == "out_fact_revenue_lines":
            joined = _enrich_revenue_fact_rows(joined)
        elif output.id == "out_fact_order_lines":
            joined = _enrich_order_fact_rows(joined)
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
                dimensional_rows.extend(
                    _build_dimensional_kpi_rows(
                        pack,
                        kpi,
                        source_rows,
                        as_of=datetime.fromisoformat(as_of.replace("Z", "+00:00")),
                        top_n=output.top_n,
                    )
                )
                continue

            source_rows = _resolve_kpi_rows(pack, kpi, compiled, settings)
            value = _apply_kpi_formula(kpi, source_rows, pack=pack)
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
