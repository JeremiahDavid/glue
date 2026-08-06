from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class PackStatus(str, Enum):
    DRAFT = "draft"
    VALIDATED = "validated"
    PRODUCTION = "production"


class BuildType(str, Enum):
    ENTITY_COPY = "entity_copy"
    JOIN = "join"
    KPI_AGGREGATE = "kpi_aggregate"


class FormulaType(str, Enum):
    SUM = "sum"
    COUNT = "count"
    COUNT_DISTINCT = "count_distinct"
    AVG = "avg"
    RATIO = "ratio"
    PERIOD_COMPARE = "period_compare"


@dataclass
class EntitySpec:
    id: str
    grain: str
    silver_entity: str
    primary_key: str
    description: str = ""


@dataclass
class JoinSpec:
    id: str
    left_entity: str
    right_entity: str
    left_key: str
    right_key: str
    cardinality: str
    description: str = ""


@dataclass
class OutputSpec:
    id: str
    output_type: str
    build: str
    entity_id: str = ""
    join_id: str = ""
    kpi_ids: list[str] = field(default_factory=list)
    columns: list[str] = field(default_factory=list)
    top_n: int | None = None


@dataclass
class CalendarSpec:
    id: str
    type: str
    date_column: str
    period_grain: str = "month"
    fiscal_year_start_month: int = 1
    description: str = ""


@dataclass
class KpiFormatSpec:
    type: str = "number"
    decimal_places: int = 2
    scale: str = "none"

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "decimal_places": self.decimal_places,
            "scale": self.scale,
        }


@dataclass
class KpiTimeSpec:
    calendar_id: str = ""
    window: str = "period"

    def to_dict(self) -> dict[str, Any]:
        return {
            "calendar_id": self.calendar_id,
            "window": self.window,
        }


@dataclass
class KpiSpec:
    id: str
    name: str
    definition: str
    formula_type: str
    source_output: str = ""
    value_column: str = ""
    unit: str = ""
    filter_column: str = ""
    filter_value: Any = None
    doc_citation: str = ""
    group_by: list[str] = field(default_factory=list)
    base_kpi: str = ""
    numerator_kpi: str = ""
    denominator_kpi: str = ""
    compare: str = ""
    result: list[str] = field(default_factory=list)
    time: KpiTimeSpec | None = None
    format: KpiFormatSpec | None = None

    def is_dimensional(self) -> bool:
        return bool(self.group_by) or self.formula_type == FormulaType.PERIOD_COMPARE.value


@dataclass
class TestSpec:
    id: str
    test_type: str
    join_id: str = ""
    output_id: str = ""
    columns: list[str] = field(default_factory=list)
    max_orphan_rate: float = 0.05
    tolerance: float = 0.01
    minimum_rows: int = 0


@dataclass
class ApprovalRecord:
    status: str
    approver: str = ""
    approved_at: str = ""
    notes: str = ""


@dataclass
class DefinitionPack:
    pack_id: str
    version: str
    status: str
    source_system: str
    entities: list[EntitySpec]
    joins: list[JoinSpec]
    outputs: list[OutputSpec]
    kpis: list[KpiSpec]
    tests: list[TestSpec]
    approval: ApprovalRecord
    description: str = ""
    limitations: list[str] = field(default_factory=list)
    source_documents: list[dict[str, str]] = field(default_factory=list)
    dimensions: list[dict[str, str]] = field(default_factory=list)
    changelog: list[dict[str, str]] = field(default_factory=list)
    calendar: CalendarSpec | None = None

    def entity_by_id(self, entity_id: str) -> EntitySpec:
        for entity in self.entities:
            if entity.id == entity_id:
                return entity
        raise KeyError(f"Unknown entity {entity_id!r}")

    def join_by_id(self, join_id: str) -> JoinSpec:
        for join in self.joins:
            if join.id == join_id:
                return join
        raise KeyError(f"Unknown join {join_id!r}")

    def output_by_id(self, output_id: str) -> OutputSpec:
        for output in self.outputs:
            if output.id == output_id:
                return output
        raise KeyError(f"Unknown output {output_id!r}")

    def kpi_by_id(self, kpi_id: str) -> KpiSpec:
        for kpi in self.kpis:
            if kpi.id == kpi_id:
                return kpi
        raise KeyError(f"Unknown KPI {kpi_id!r}")

    def is_publishable(self) -> bool:
        return self.approval.status in {PackStatus.VALIDATED.value, PackStatus.PRODUCTION.value}

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "pack_id": self.pack_id,
            "version": self.version,
            "status": self.status,
            "source_system": self.source_system,
            "description": self.description,
            "limitations": self.limitations,
            "source_documents": self.source_documents,
            "entities": [
                {
                    "id": e.id,
                    "grain": e.grain,
                    "silver_entity": e.silver_entity,
                    "primary_key": e.primary_key,
                    "description": e.description,
                }
                for e in self.entities
            ],
            "joins": [
                {
                    "id": j.id,
                    "left_entity": j.left_entity,
                    "right_entity": j.right_entity,
                    "left_key": j.left_key,
                    "right_key": j.right_key,
                    "cardinality": j.cardinality,
                    "description": j.description,
                }
                for j in self.joins
            ],
            "dimensions": self.dimensions,
            "outputs": [
                {
                    "id": o.id,
                    "output_type": o.output_type,
                    "build": o.build,
                    "entity_id": o.entity_id,
                    "join_id": o.join_id,
                    "kpi_ids": o.kpi_ids,
                    "columns": o.columns,
                    "top_n": o.top_n,
                }
                for o in self.outputs
            ],
            "kpis": [_kpi_to_dict(k) for k in self.kpis],
            "tests": [
                {
                    "id": t.id,
                    "test_type": t.test_type,
                    "join_id": t.join_id,
                    "output_id": t.output_id,
                    "columns": t.columns,
                    "max_orphan_rate": t.max_orphan_rate,
                    "tolerance": t.tolerance,
                    "minimum_rows": t.minimum_rows,
                }
                for t in self.tests
            ],
            "approval": {
                "status": self.approval.status,
                "approver": self.approval.approver,
                "approved_at": self.approval.approved_at,
                "notes": self.approval.notes,
            },
            "changelog": self.changelog,
        }
        if self.calendar is not None:
            payload["calendar"] = {
                "id": self.calendar.id,
                "type": self.calendar.type,
                "date_column": self.calendar.date_column,
                "fiscal_year_start_month": self.calendar.fiscal_year_start_month,
                "period_grain": self.calendar.period_grain,
                "description": self.calendar.description,
            }
        return payload


def _kpi_to_dict(kpi: KpiSpec) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": kpi.id,
        "name": kpi.name,
        "definition": kpi.definition,
        "formula_type": kpi.formula_type,
        "source_output": kpi.source_output,
        "value_column": kpi.value_column,
        "unit": kpi.unit,
        "filter_column": kpi.filter_column,
        "filter_value": kpi.filter_value,
        "doc_citation": kpi.doc_citation,
        "group_by": list(kpi.group_by),
        "base_kpi": kpi.base_kpi,
        "numerator_kpi": kpi.numerator_kpi,
        "denominator_kpi": kpi.denominator_kpi,
        "compare": kpi.compare,
        "result": list(kpi.result),
    }
    if kpi.time is not None:
        payload["time"] = kpi.time.to_dict()
    if kpi.format is not None:
        payload["format"] = kpi.format.to_dict()
    return payload


def _require_mapping(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key, {})
    if not isinstance(value, dict):
        raise ValueError(f"Definition pack field {key!r} must be a mapping")
    return value


def _require_list(payload: dict[str, Any], key: str) -> list[Any]:
    value = payload.get(key, [])
    if not isinstance(value, list):
        raise ValueError(f"Definition pack field {key!r} must be a list")
    return value


def _load_calendar(payload: dict[str, Any]) -> CalendarSpec | None:
    raw = payload.get("calendar")
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError("Definition pack field 'calendar' must be a mapping")
    calendar_type = str(raw.get("type", "calendar_year"))
    start_month = int(raw.get("fiscal_year_start_month") or (1 if calendar_type == "calendar_year" else 1))
    return CalendarSpec(
        id=str(raw["id"]),
        type=calendar_type,
        date_column=str(raw["date_column"]),
        period_grain=str(raw.get("period_grain", "month")),
        fiscal_year_start_month=start_month,
        description=str(raw.get("description", "")),
    )


def _load_kpi_format(raw: Any) -> KpiFormatSpec | None:
    if not isinstance(raw, dict):
        return None
    return KpiFormatSpec(
        type=str(raw.get("type", "number")),
        decimal_places=int(raw.get("decimal_places", 2)),
        scale=str(raw.get("scale", "none")),
    )


def _load_kpi_time(raw: Any) -> KpiTimeSpec | None:
    if not isinstance(raw, dict):
        return None
    return KpiTimeSpec(
        calendar_id=str(raw.get("calendar_id", "")),
        window=str(raw.get("window", "period")),
    )


def _load_kpi(item: dict[str, Any]) -> KpiSpec:
    formula_type = str(item["formula_type"])
    source_output = str(item.get("source_output", ""))
    value_column = str(item.get("value_column", ""))
    base_kpi = str(item.get("base_kpi", ""))
    numerator_kpi = str(item.get("numerator_kpi", ""))
    denominator_kpi = str(item.get("denominator_kpi", ""))
    compare = str(item.get("compare", ""))

    if formula_type == FormulaType.PERIOD_COMPARE.value:
        if not base_kpi:
            raise ValueError(f"KPI {item.get('id')!r} period_compare requires base_kpi")
        if compare not in {"prior_year", "prior_period"}:
            raise ValueError(f"KPI {item.get('id')!r} period_compare requires compare prior_year|prior_period")
    elif formula_type == FormulaType.RATIO.value:
        if not numerator_kpi or not denominator_kpi:
            raise ValueError(f"KPI {item.get('id')!r} ratio requires numerator_kpi and denominator_kpi")
    elif formula_type != FormulaType.PERIOD_COMPARE.value and (not source_output or not value_column):
        raise ValueError(
            f"KPI {item.get('id')!r} requires source_output and value_column "
            f"for formula_type {formula_type!r}"
        )

    result = [str(value) for value in item.get("result", [])]
    if formula_type == FormulaType.PERIOD_COMPARE.value and not result:
        result = ["current", "prior", "delta", "pct_change"]

    return KpiSpec(
        id=str(item["id"]),
        name=str(item["name"]),
        definition=str(item.get("definition") or item.get("name") or ""),
        formula_type=formula_type,
        source_output=source_output,
        value_column=value_column,
        unit=str(item.get("unit", "")),
        filter_column=str(item.get("filter_column", "")),
        filter_value=item.get("filter_value"),
        doc_citation=str(item.get("doc_citation", "")),
        group_by=[str(column) for column in item.get("group_by", [])],
        base_kpi=base_kpi,
        numerator_kpi=numerator_kpi,
        denominator_kpi=denominator_kpi,
        compare=compare,
        result=result,
        time=_load_kpi_time(item.get("time")),
        format=_load_kpi_format(item.get("format")),
    )


def load_definition_pack(payload: dict[str, Any]) -> DefinitionPack:
    approval_raw = _require_mapping(payload, "approval")
    entities = [
        EntitySpec(
            id=str(item["id"]),
            grain=str(item["grain"]),
            silver_entity=str(item["silver_entity"]),
            primary_key=str(item["primary_key"]),
            description=str(item.get("description", "")),
        )
        for item in _require_list(payload, "entities")
    ]
    joins = [
        JoinSpec(
            id=str(item["id"]),
            left_entity=str(item["left_entity"]),
            right_entity=str(item["right_entity"]),
            left_key=str(item["left_key"]),
            right_key=str(item["right_key"]),
            cardinality=str(item["cardinality"]),
            description=str(item.get("description", "")),
        )
        for item in _require_list(payload, "joins")
    ]
    outputs = [
        OutputSpec(
            id=str(item["id"]),
            output_type=str(item["output_type"]),
            build=str(item["build"]),
            entity_id=str(item.get("entity_id", "")),
            join_id=str(item.get("join_id", "")),
            kpi_ids=[str(k) for k in item.get("kpi_ids", [])],
            columns=[str(c) for c in item.get("columns", [])],
            top_n=int(item["top_n"]) if item.get("top_n") is not None else None,
        )
        for item in _require_list(payload, "outputs")
    ]
    kpis = [_load_kpi(item) for item in _require_list(payload, "kpis") if isinstance(item, dict)]
    tests = [
        TestSpec(
            id=str(item["id"]),
            test_type=str(item["test_type"]),
            join_id=str(item.get("join_id", "")),
            output_id=str(item.get("output_id", "")),
            columns=[str(c) for c in item.get("columns", [])],
            max_orphan_rate=float(item.get("max_orphan_rate", 0.05)),
            tolerance=float(item.get("tolerance", 0.01)),
            minimum_rows=int(item.get("minimum_rows", 0)),
        )
        for item in _require_list(payload, "tests")
    ]
    return DefinitionPack(
        pack_id=str(payload["pack_id"]),
        version=str(payload["version"]),
        status=str(payload.get("status", approval_raw.get("status", "draft"))),
        source_system=str(payload["source_system"]),
        entities=entities,
        joins=joins,
        outputs=outputs,
        kpis=kpis,
        tests=tests,
        approval=ApprovalRecord(
            status=str(approval_raw.get("status", "draft")),
            approver=str(approval_raw.get("approver", "")),
            approved_at=str(approval_raw.get("approved_at", "")),
            notes=str(approval_raw.get("notes", "")),
        ),
        description=str(payload.get("description", "")),
        limitations=[str(item) for item in payload.get("limitations", [])],
        source_documents=[
            item for item in payload.get("source_documents", []) if isinstance(item, dict)
        ],
        dimensions=[item for item in payload.get("dimensions", []) if isinstance(item, dict)],
        changelog=[item for item in payload.get("changelog", []) if isinstance(item, dict)],
        calendar=_load_calendar(payload),
    )


def load_definition_pack_yaml(text: str) -> DefinitionPack:
    import yaml

    payload = yaml.safe_load(text)
    if not isinstance(payload, dict):
        raise ValueError("Definition pack YAML must be a mapping at the top level")
    return load_definition_pack(payload)


def starter_pack_path(pack_id: str = "bc_intra_v1") -> Path:
    return Path(__file__).resolve().parent / "packs" / f"{pack_id}.yaml"


def load_definition_pack_file(path: str | Path) -> DefinitionPack:
    file_path = Path(path)
    return load_definition_pack_yaml(file_path.read_text(encoding="utf-8"))
