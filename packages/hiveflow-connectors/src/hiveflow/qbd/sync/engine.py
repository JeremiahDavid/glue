from __future__ import annotations

import logging
import secrets
import uuid

from meshflow.config import QBDSettings, load_qbd_settings
from meshflow.project_config import resolve_qbd_ingest_entities
from meshflow.qbd.entities import MAX_RETURNED, sync_job_specs
from meshflow.qbd.ingest.finalize import finalize_sync_run
from meshflow.qbd.models import (
    ActiveSession,
    ConnectorState,
    EntitySyncState,
    EntityType,
    SyncJob,
    SyncRun,
    SyncStatus,
    utc_now,
)
from meshflow.qbd.qbxml.parsers import extract_records, parse_iterator_info, parse_query_status
from meshflow.qbd.qbxml.requests import build_entity_query
from meshflow.qbd.storage.state_store import StateStore

logger = logging.getLogger(__name__)


def _verify_qbwc_password(password: str, settings: QBDSettings) -> bool:
    if settings.qbwc_password_hash:
        return secrets.compare_digest(password, settings.qbwc_password_hash)
    if settings.qbwc_password:
        return secrets.compare_digest(password, settings.qbwc_password)
    return False


class SyncEngine:
    def __init__(self, settings: QBDSettings | None = None) -> None:
        self.settings = settings or load_qbd_settings()
        self.store = StateStore(self.settings)
        self._entity_bundle, self._entity_specs = resolve_qbd_ingest_entities()

    def authenticate(self, username: str, password: str) -> tuple[str, str]:
        if username != self.settings.qbwc_username:
            return "nvu", ""
        if not _verify_qbwc_password(password, self.settings):
            return "nvu", ""

        ticket = secrets.token_hex(16)
        sync_run = self._create_sync_run()
        session = ActiveSession(ticket=ticket, sync_run=sync_run)
        connector_state = self._load_connector_state()
        connector_state.last_connected_at = utc_now()
        self._save_connector_state(connector_state)
        self._save_session(session)
        return ticket, self.settings.company_file or ""

    def close_session(self, ticket: str) -> None:
        session = self._get_session(ticket)
        if session is None:
            return
        if session.sync_run.status == SyncStatus.RUNNING:
            session.sync_run.status = SyncStatus.COMPLETED
            session.sync_run.completed_at = utc_now()
        session.is_active = False
        session.closed_at = utc_now()
        self._save_session(session)
        self.store.put_json(
            self.store.sync_run_key(str(session.sync_run.id)),
            session.sync_run.to_dict(),
        )

    def next_request_xml(self, ticket: str) -> str:
        session = self._get_session(ticket)
        if session is None or not session.is_active:
            return ""

        sync_run = session.sync_run
        job = self._current_job(sync_run)
        if job is None:
            return ""

        connector_state = self._load_connector_state()
        sync_state = connector_state.entity_sync_states.get(job.entity_type.value)
        from_modified = None
        if sync_state and sync_state.full_sync_completed and sync_state.last_modified_from:
            from_modified = sync_state.last_modified_from
        if job.iterator_id:
            xml = build_entity_query(
                job.entity_type,
                qbxml_version=self.settings.qbxml_version,
                from_modified_date=from_modified,
                iterator="Continue",
                iterator_id=job.iterator_id,
                max_returned=MAX_RETURNED,
                request_id=str(job.sequence),
            )
        else:
            xml = build_entity_query(
                job.entity_type,
                qbxml_version=self.settings.qbxml_version,
                from_modified_date=from_modified,
                max_returned=MAX_RETURNED,
                request_id=str(job.sequence),
            )

        job.status = SyncStatus.RUNNING
        job.started_at = job.started_at or utc_now()
        if sync_run.status == SyncStatus.PENDING:
            sync_run.status = SyncStatus.RUNNING
            sync_run.started_at = utc_now()
        self._save_session(session)
        return xml

    def process_response(
        self,
        ticket: str,
        response_xml: str,
        *,
        hresult: str = "",
        message: str = "",
    ) -> int:
        session = self._get_session(ticket)
        if session is None or not session.is_active:
            return 100

        sync_run = session.sync_run
        job = self._current_job(sync_run)
        if job is None:
            return 100

        if hresult.strip() or not response_xml.strip():
            error = message.strip() or hresult.strip() or "Empty QuickBooks response"
            job.status = SyncStatus.FAILED
            job.error_message = error
            sync_run.status = SyncStatus.FAILED
            sync_run.error_message = error
            sync_run.completed_at = utc_now()
            self._save_session(session)
            self.store.put_json(self.store.sync_run_key(str(sync_run.id)), sync_run.to_dict())
            logger.error("QBD sync failed for ticket %s: %s", ticket, error)
            return -1

        status_ok, status_code, status_message = parse_query_status(response_xml)
        if not status_ok:
            job.status = SyncStatus.FAILED
            job.error_message = status_message or f"QuickBooks status {status_code}"
            sync_run.status = SyncStatus.FAILED
            sync_run.error_message = job.error_message
            sync_run.completed_at = utc_now()
            self._save_session(session)
            self.store.put_json(self.store.sync_run_key(str(sync_run.id)), sync_run.to_dict())
            return -1

        records = extract_records(response_xml, job.entity_type)
        bucket = session.accumulated_records.setdefault(job.output_name, [])
        bucket.extend(records)
        job.records_processed += len(records)

        iterator_id, iterator_remaining = parse_iterator_info(response_xml)
        if iterator_id and iterator_remaining and iterator_remaining > 0:
            job.iterator_id = iterator_id
            job.iterator_remaining = iterator_remaining
            self._save_session(session)
            return self._progress(sync_run)

        self._complete_job(job)
        next_job = self._advance_to_next_job(sync_run, job)
        if next_job is None:
            sync_run.status = SyncStatus.COMPLETED
            sync_run.completed_at = utc_now()
            manifest = finalize_sync_run(
                self.settings,
                sync_run,
                session.accumulated_records,
                company_name=self.settings.company_name,
                company_file=self.settings.company_file,
            )
            sync_run.run_path = manifest.get("run_path")
            sync_run.manifest_path = manifest.get("manifest_path")
            self._save_connector_state(self._load_connector_state())
            self._save_session(session)
            self.store.put_json(self.store.sync_run_key(str(sync_run.id)), sync_run.to_dict())
            logger.info("QBD sync complete: %s", manifest.get("manifest_path"))
            return 100

        self._save_session(session)
        return self._progress(sync_run)

    def get_last_error(self, ticket: str) -> str:
        payload = self.store.get_json(self.store.session_key(ticket))
        if not isinstance(payload, dict):
            return ""
        session = ActiveSession.from_dict(payload)
        return session.sync_run.error_message or ""

    def connection_error(self, ticket: str, message: str) -> None:
        session = self._get_session(ticket)
        if session is None:
            return
        session.sync_run.status = SyncStatus.FAILED
        session.sync_run.error_message = message
        session.sync_run.completed_at = utc_now()
        self._save_session(session)
        self.store.put_json(
            self.store.sync_run_key(str(session.sync_run.id)),
            session.sync_run.to_dict(),
        )

    def _create_sync_run(self) -> SyncRun:
        jobs = [
            SyncJob(
                id=uuid.uuid4(),
                entity_type=spec.entity_type,
                output_name=spec.output_name,
                sequence=index,
            )
            for index, spec in enumerate(sync_job_specs(self._entity_bundle), start=1)
        ]
        return SyncRun(id=uuid.uuid4(), entity_bundle=self._entity_bundle, jobs=jobs)

    def _load_connector_state(self) -> ConnectorState:
        payload = self.store.get_json(self.store.connector_state_key())
        return ConnectorState.from_dict(payload)

    def _save_connector_state(self, state: ConnectorState) -> None:
        self.store.put_json(self.store.connector_state_key(), state.to_dict())

    def _get_session(self, ticket: str) -> ActiveSession | None:
        payload = self.store.get_json(self.store.session_key(ticket))
        if not isinstance(payload, dict):
            return None
        session = ActiveSession.from_dict(payload)
        return session if session.is_active else None

    def _save_session(self, session: ActiveSession) -> None:
        self.store.put_json(self.store.session_key(session.ticket), session.to_dict())

    def _current_job(self, sync_run: SyncRun) -> SyncJob | None:
        for job in sorted(sync_run.jobs, key=lambda item: item.sequence):
            if job.status in (SyncStatus.PENDING, SyncStatus.RUNNING):
                return job
        return None

    def _advance_to_next_job(self, sync_run: SyncRun, completed_job: SyncJob) -> SyncJob | None:
        completed_job.status = SyncStatus.COMPLETED
        completed_job.completed_at = utc_now()
        completed_job.iterator_id = None
        completed_job.iterator_remaining = None
        for job in sorted(sync_run.jobs, key=lambda item: item.sequence):
            if job.sequence > completed_job.sequence and job.status == SyncStatus.PENDING:
                return job
        return None

    def _complete_job(self, job: SyncJob) -> None:
        state = self._load_connector_state()
        entity_state = state.entity_sync_states.get(job.entity_type.value)
        if entity_state is None:
            entity_state = EntitySyncState()
            state.entity_sync_states[job.entity_type.value] = entity_state
        entity_state.last_sync_at = utc_now()
        entity_state.last_modified_from = utc_now()
        entity_state.full_sync_completed = True
        self._save_connector_state(state)

    def _progress(self, sync_run: SyncRun) -> int:
        total = len(sync_run.jobs)
        done = sum(1 for job in sync_run.jobs if job.status == SyncStatus.COMPLETED)
        current = next((job for job in sync_run.jobs if job.status == SyncStatus.RUNNING), None)
        if current and current.iterator_remaining:
            base = int((done / total) * 100)
            return min(base + 5, 99)
        return int((done / total) * 100) if total else 100
