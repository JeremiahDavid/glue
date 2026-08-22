"""Initialize per-client governance from DBC boilerplate packs."""

from __future__ import annotations

from datetime import datetime
from hiveflow.compat import UTC
from pathlib import Path
from typing import Any

from hiveflow.dna.governance import governance_pack_exists, save_governance_version
from hiveflow.dna.schema import load_definition_pack_file
from hiveflow.dna.settings import DnaSettings
from hiveflow.dna.store import write_json_artifact
from hiveflow.dna.reporting import load_reporting_boilerplate
from hiveflow.storage.paths import (
    company_dna_config_id,
    company_reporting_config_id,
    governance_workflow_key,
)

DNA_BOILERPLATE_NAME = "dbc_dna_boilerplate.yaml"


def dna_boilerplate_path() -> Path:
    return Path(__file__).resolve().parent / "packs" / DNA_BOILERPLATE_NAME


def init_client_governance(
    settings: DnaSettings,
    *,
    company: str | None = None,
    pack_id: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Seed ``{company}_dna_config.yaml`` (+ reporting) when that pack is missing.

    Boilerplate template remains ``dbc_dna_boilerplate.yaml`` in-repo; the tenant
    artifact is renamed to the company DNA config id on init.
    """
    company_name = (company or settings.company or "").strip()
    if not company_name:
        raise ValueError("company is required to initialize client governance")

    target_pack_id = (pack_id or company_dna_config_id(company_name)).strip().lower()
    settings.company = company_name
    settings.pack_id = target_pack_id

    if governance_pack_exists(settings, target_pack_id) and not force:
        return {
            "status": "skipped",
            "reason": "governance_pack_exists",
            "company": company_name,
            "pack_id": target_pack_id,
            "dna_config": f"{target_pack_id}.yaml",
        }

    boilerplate = dna_boilerplate_path()
    if not boilerplate.is_file():
        raise FileNotFoundError(f"DNA boilerplate not found: {boilerplate}")

    pack = load_definition_pack_file(boilerplate)
    pack.pack_id = target_pack_id
    pack.status = "production"
    pack.approval.status = "production"
    pack.approval.approver = pack.approval.approver or "HiveFlow boilerplate"
    pack.approval.notes = (
        pack.approval.notes
        or f"Seeded from {DNA_BOILERPLATE_NAME} as {target_pack_id}.yaml on client init"
    )

    from hiveflow.dna.reporting import normalize_reporting_identity

    reporting_id = company_reporting_config_id(company_name)
    reporting = normalize_reporting_identity(
        settings,
        load_reporting_boilerplate(pack_id=reporting_id, version=pack.version),
        version=pack.version,
        status="production",
    )

    saved = save_governance_version(settings, pack=pack, reporting=reporting)
    workflow = {
        "pack_id": target_pack_id,
        "company": company_name,
        "active_version": pack.version,
        "history": [
            {
                "version": pack.version,
                "status": "production",
                "approver": "HiveFlow boilerplate",
                "at": datetime.now(UTC).isoformat(),
                "notes": f"Initialized {target_pack_id}.yaml from DBC DNA boilerplate",
            }
        ],
    }
    workflow_path = write_json_artifact(
        settings,
        governance_workflow_key(target_pack_id),
        workflow,
    )

    return {
        "status": "initialized",
        "company": company_name,
        "pack_id": target_pack_id,
        "version": pack.version,
        "dna_config": f"{target_pack_id}.yaml",
        "reporting_config": f"{reporting_id}.yaml",
        "dna_path": saved["dna_path"],
        "reporting_path": saved["reporting_path"],
        "manifest_path": saved["manifest_path"],
        "workflow_path": workflow_path,
        "dna_boilerplate": str(boilerplate),
        "reporting_boilerplate": "dbc_reporting_boilerplate.yaml",
    }


def ensure_client_governance(settings: DnaSettings) -> dict[str, Any]:
    """Idempotent init — seeds ``{company}_dna_config`` only when that pack is missing."""
    return init_client_governance(
        settings,
        company=settings.company,
        pack_id=settings.dna_config_id,
        force=False,
    )


def ensure_reporting_config(
    settings: DnaSettings,
    *,
    force: bool = False,
) -> dict[str, Any]:
    """Seed ``{company}_reporting_config.yaml`` when missing.

    If DNA governance is absent, runs full client init (DNA + reporting).
    If DNA exists but the reporting sidecar is missing for the pinned version,
    writes only the reporting boilerplate into that version folder.
    """
    from hiveflow.dna.governance import (
        load_governance_manifest,
        load_governance_reporting_payload,
    )
    from hiveflow.dna.store import write_json_artifact, write_yaml_artifact
    from hiveflow.dna.reporting import (
        REPORTING_BOILERPLATE_NAME,
        load_reporting_boilerplate,
        normalize_reporting_identity,
    )
    from hiveflow.dna.workflow import load_workflow_state
    from hiveflow.storage.paths import (
        governance_manifest_key,
        governance_reporting_key,
        governance_workflow_key,
    )

    company_name = (settings.company or "").strip()
    if not company_name:
        raise ValueError("company is required to initialize reporting config")

    dna_id = settings.dna_config_id
    reporting_id = settings.reporting_config_id
    settings.company = company_name
    settings.pack_id = dna_id

    if not governance_pack_exists(settings, dna_id):
        return init_client_governance(
            settings,
            company=company_name,
            pack_id=dna_id,
            force=False,
        )

    state = load_workflow_state(settings, dna_id)
    version = settings.pack_version or state.get("active_version")
    if not version:
        try:
            from hiveflow.dna.store import load_pack_from_settings

            version = load_pack_from_settings(settings).version
        except FileNotFoundError:
            version = "1.0.0"
    version = str(version)

    existing = load_governance_reporting_payload(settings, dna_id, version)
    if existing and not force:
        return {
            "status": "skipped",
            "reason": "reporting_config_exists",
            "company": company_name,
            "pack_id": dna_id,
            "reporting_config": f"{reporting_id}.yaml",
            "version": version,
        }

    reporting = normalize_reporting_identity(
        settings,
        load_reporting_boilerplate(pack_id=reporting_id, version=version),
        version=version,
        status="production",
    )
    reporting_key = governance_reporting_key(dna_id, version, company=company_name)
    reporting_path = write_yaml_artifact(settings, reporting_key, reporting)

    manifest = load_governance_manifest(settings, dna_id, version) or {
        "pack_id": dna_id,
        "version": version,
        "company": company_name,
        "status": "production",
        "artifacts": {},
    }
    artifacts = manifest.setdefault("artifacts", {})
    if not isinstance(artifacts, dict):
        artifacts = {}
        manifest["artifacts"] = artifacts
    artifacts["reporting"] = {"key": reporting_key, "path": reporting_path}
    manifest_path = write_json_artifact(
        settings,
        governance_manifest_key(dna_id, version),
        manifest,
    )

    if not state.get("active_version"):
        state["pack_id"] = dna_id
        state["company"] = company_name
        state["active_version"] = version
        history = state.get("history")
        if not isinstance(history, list):
            history = []
        history.append(
            {
                "version": version,
                "status": "production",
                "approver": "HiveFlow reporting seed",
                "at": datetime.now(UTC).isoformat(),
                "notes": f"Pinned {version} while seeding {reporting_id}.yaml",
            }
        )
        state["history"] = history
        write_json_artifact(settings, governance_workflow_key(dna_id), state)

    return {
        "status": "initialized",
        "company": company_name,
        "pack_id": dna_id,
        "version": version,
        "dna_config": f"{dna_id}.yaml",
        "reporting_config": f"{reporting_id}.yaml",
        "reporting_path": reporting_path,
        "manifest_path": manifest_path,
        "reporting_boilerplate": REPORTING_BOILERPLATE_NAME,
    }
