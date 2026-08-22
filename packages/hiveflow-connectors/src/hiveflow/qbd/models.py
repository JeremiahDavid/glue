from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from meshflow.compat import UTC


class SyncStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class EntityType(str, enum.Enum):
    COMPANY = "company"
    ACCOUNT = "account"
    CLASS = "class"
    DEPARTMENT = "department"
    CUSTOMER = "customer"
    VENDOR = "vendor"
    ITEM = "item"
    INVOICE = "invoice"
    BILL = "bill"
    SALES_RECEIPT = "sales_receipt"
    CREDIT_MEMO = "credit_memo"
    DEPOSIT = "deposit"
    RECEIVE_PAYMENT = "receive_payment"
    ESTIMATE = "estimate"


def utc_now() -> datetime:
    return datetime.now(UTC)


def dt_to_iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def dt_from_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


@dataclass
class EntitySyncState:
    last_sync_at: datetime | None = None
    last_modified_from: datetime | None = None
    full_sync_completed: bool = False

    def to_dict(self) -> dict:
        return {
            "last_sync_at": dt_to_iso(self.last_sync_at),
            "last_modified_from": dt_to_iso(self.last_modified_from),
            "full_sync_completed": self.full_sync_completed,
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> EntitySyncState:
        if not data:
            return cls()
        return cls(
            last_sync_at=dt_from_iso(data.get("last_sync_at")),
            last_modified_from=dt_from_iso(data.get("last_modified_from")),
            full_sync_completed=bool(data.get("full_sync_completed", False)),
        )


@dataclass
class SyncJob:
    id: uuid.UUID
    entity_type: EntityType
    output_name: str
    sequence: int
    status: SyncStatus = SyncStatus.PENDING
    iterator_id: str | None = None
    iterator_remaining: int | None = None
    records_processed: int = 0
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "entity_type": self.entity_type.value,
            "output_name": self.output_name,
            "sequence": self.sequence,
            "status": self.status.value,
            "iterator_id": self.iterator_id,
            "iterator_remaining": self.iterator_remaining,
            "records_processed": self.records_processed,
            "error_message": self.error_message,
            "started_at": dt_to_iso(self.started_at),
            "completed_at": dt_to_iso(self.completed_at),
        }

    @classmethod
    def from_dict(cls, data: dict) -> SyncJob:
        return cls(
            id=uuid.UUID(data["id"]),
            entity_type=EntityType(data["entity_type"]),
            output_name=data["output_name"],
            sequence=data["sequence"],
            status=SyncStatus(data.get("status", SyncStatus.PENDING.value)),
            iterator_id=data.get("iterator_id"),
            iterator_remaining=data.get("iterator_remaining"),
            records_processed=int(data.get("records_processed", 0)),
            error_message=data.get("error_message"),
            started_at=dt_from_iso(data.get("started_at")),
            completed_at=dt_from_iso(data.get("completed_at")),
        )


@dataclass
class SyncRun:
    id: uuid.UUID
    status: SyncStatus = SyncStatus.PENDING
    entity_bundle: str = "v1_accounting"
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None
    run_path: str | None = None
    manifest_path: str | None = None
    jobs: list[SyncJob] = field(default_factory=list)
    created_at: datetime = field(default_factory=utc_now)

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "status": self.status.value,
            "entity_bundle": self.entity_bundle,
            "started_at": dt_to_iso(self.started_at),
            "completed_at": dt_to_iso(self.completed_at),
            "error_message": self.error_message,
            "run_path": self.run_path,
            "manifest_path": self.manifest_path,
            "jobs": [job.to_dict() for job in self.jobs],
            "created_at": dt_to_iso(self.created_at),
        }

    @classmethod
    def from_dict(cls, data: dict) -> SyncRun:
        return cls(
            id=uuid.UUID(data["id"]),
            status=SyncStatus(data.get("status", SyncStatus.PENDING.value)),
            entity_bundle=data.get("entity_bundle", "v1_accounting"),
            started_at=dt_from_iso(data.get("started_at")),
            completed_at=dt_from_iso(data.get("completed_at")),
            error_message=data.get("error_message"),
            run_path=data.get("run_path"),
            manifest_path=data.get("manifest_path"),
            jobs=[SyncJob.from_dict(job) for job in data.get("jobs", [])],
            created_at=dt_from_iso(data.get("created_at")) or utc_now(),
        )


@dataclass
class ActiveSession:
    ticket: str
    sync_run: SyncRun
    accumulated_records: dict[str, list[dict]] = field(default_factory=dict)
    is_active: bool = True
    created_at: datetime = field(default_factory=utc_now)
    closed_at: datetime | None = None

    def to_dict(self) -> dict:
        return {
            "ticket": self.ticket,
            "sync_run": self.sync_run.to_dict(),
            "accumulated_records": self.accumulated_records,
            "is_active": self.is_active,
            "created_at": dt_to_iso(self.created_at),
            "closed_at": dt_to_iso(self.closed_at),
        }

    @classmethod
    def from_dict(cls, data: dict) -> ActiveSession:
        return cls(
            ticket=data["ticket"],
            sync_run=SyncRun.from_dict(data["sync_run"]),
            accumulated_records={
                str(name): rows
                for name, rows in (data.get("accumulated_records") or {}).items()
            },
            is_active=bool(data.get("is_active", True)),
            created_at=dt_from_iso(data.get("created_at")) or utc_now(),
            closed_at=dt_from_iso(data.get("closed_at")),
        )


@dataclass
class ConnectorState:
    entity_sync_states: dict[str, EntitySyncState] = field(default_factory=dict)
    last_connected_at: datetime | None = None

    def to_dict(self) -> dict:
        return {
            "entity_sync_states": {
                key: state.to_dict() for key, state in self.entity_sync_states.items()
            },
            "last_connected_at": dt_to_iso(self.last_connected_at),
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> ConnectorState:
        if not data:
            return cls()
        return cls(
            entity_sync_states={
                key: EntitySyncState.from_dict(value)
                for key, value in (data.get("entity_sync_states") or {}).items()
            },
            last_connected_at=dt_from_iso(data.get("last_connected_at")),
        )
