"""Reporting pack — portal layout contract (web-owned).

Boilerplate: ``web/packs/dbc_reporting_boilerplate.yaml``.
Persisted as ``{company}_reporting_config.yaml`` under governance beside DNA.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from meshflow.dna.settings import DnaSettings
from meshflow.storage.paths import governance_reporting_key

REPORTING_BOILERPLATE_NAME = "dbc_reporting_boilerplate.yaml"
_PACK_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
_STATUS_VALUES = frozenset({"draft", "validated", "production"})


def reporting_pack_schema_path() -> Path:
    return Path(__file__).resolve().parent / "schema" / "reporting-pack.schema.json"


def reporting_boilerplate_path() -> Path:
    return Path(__file__).resolve().parent / "packs" / REPORTING_BOILERPLATE_NAME


def default_reporting_pack(
    *,
    pack_id: str,
    version: str,
    status: str = "draft",
    description: str = "",
) -> dict[str, Any]:
    return {
        "pack_id": pack_id,
        "version": version,
        "status": status,
        "include_chart_catalog": False,
        "description": description
        or "Reporting pack — portal layout bindings to certified gold outputs.",
        "pages": [],
        "changelog": [],
    }


def validate_reporting_pack_schema(payload: dict[str, Any]) -> None:
    """Validate against reporting-pack.schema.json required fields and patterns."""
    if not isinstance(payload, dict):
        raise ValueError("Reporting pack must be a mapping")

    schema_path = reporting_pack_schema_path()
    if schema_path.is_file():
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        required = schema.get("required") or []
        for field in required:
            if field not in payload:
                raise ValueError(f"Reporting pack missing required field {field!r}")

    pack_id = str(payload.get("pack_id", "")).strip()
    version = str(payload.get("version", "")).strip()
    status = str(payload.get("status", "")).strip()
    pages = payload.get("pages")

    if not pack_id or not _PACK_ID_RE.match(pack_id):
        raise ValueError(
            f"Reporting pack pack_id must match {_PACK_ID_RE.pattern!r}, got {pack_id!r}"
        )
    if not version or not _VERSION_RE.match(version):
        raise ValueError(
            f"Reporting pack version must be semver X.Y.Z, got {version!r}"
        )
    if status not in _STATUS_VALUES:
        raise ValueError(
            f"Reporting pack status must be one of {sorted(_STATUS_VALUES)}, got {status!r}"
        )
    if not isinstance(pages, list):
        raise ValueError("Reporting pack field 'pages' must be a list")
    for index, page in enumerate(pages):
        if not isinstance(page, dict):
            raise ValueError(f"Reporting pack pages[{index}] must be an object")
        if not str(page.get("id", "")).strip() or not str(page.get("title", "")).strip():
            raise ValueError(f"Reporting pack pages[{index}] requires id and title")


def load_reporting_pack(payload: dict[str, Any]) -> dict[str, Any]:
    validate_reporting_pack_schema(payload)
    pack_id = str(payload.get("pack_id", "")).strip()
    version = str(payload.get("version", "")).strip()
    pages = payload.get("pages", [])
    return {
        "pack_id": pack_id,
        "version": version,
        "status": str(payload.get("status", "draft")),
        "description": str(payload.get("description", "")),
        "pages": [page for page in pages if isinstance(page, dict)],
        "changelog": [
            entry for entry in payload.get("changelog", []) if isinstance(entry, dict)
        ],
    }


def load_reporting_pack_yaml(text: str) -> dict[str, Any]:
    payload = yaml.safe_load(text)
    if not isinstance(payload, dict):
        raise ValueError("Reporting pack YAML must be a mapping at the top level")
    return load_reporting_pack(payload)


def load_reporting_boilerplate(*, pack_id: str, version: str | None = None) -> dict[str, Any]:
    path = reporting_boilerplate_path()
    if not path.is_file():
        return default_reporting_pack(pack_id=pack_id, version=version or "1.0.0", status="production")
    payload = load_reporting_pack_yaml(path.read_text(encoding="utf-8"))
    payload["pack_id"] = pack_id
    if version:
        payload["version"] = version
    return load_reporting_pack(payload)


def normalize_reporting_identity(
    settings: DnaSettings,
    reporting: dict[str, Any],
    *,
    version: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    """Force company reporting config identity; keep version aligned with DNA when given."""
    payload = dict(reporting)
    payload["pack_id"] = settings.reporting_config_id
    if version:
        payload["version"] = version
    if status:
        payload["status"] = status
    return load_reporting_pack(payload)


def save_reporting_pack(
    settings: DnaSettings,
    *,
    pack_id: str,
    version: str,
    reporting: dict[str, Any] | None = None,
    status: str = "draft",
) -> dict[str, Any]:
    """Write reporting sidecar under the DNA governance pack prefix ``pack_id``."""
    from meshflow.dna.store import write_yaml_artifact

    reporting_id = settings.reporting_config_id
    payload = load_reporting_pack(
        reporting
        if reporting is not None
        else default_reporting_pack(pack_id=reporting_id, version=version, status=status)
    )
    payload = normalize_reporting_identity(
        settings, payload, version=version, status=payload.get("status") or status
    )
    key = governance_reporting_key(pack_id, version, company=settings.company or None)
    path = write_yaml_artifact(settings, key, payload)
    return {"key": key, "path": path, "reporting": payload}


def load_reporting_pack_from_governance(
    settings: DnaSettings,
    pack_id: str,
    version: str,
) -> dict[str, Any]:
    from meshflow.dna.governance import load_governance_reporting_payload

    payload = load_governance_reporting_payload(settings, pack_id, version)
    if payload:
        loaded = load_reporting_pack(payload)
        # Prefer canonical company reporting id when settings know the company.
        if settings.company or settings.pack_id.endswith("_dna_config"):
            loaded["pack_id"] = settings.reporting_config_id
        return loaded
    return default_reporting_pack(pack_id=settings.reporting_config_id, version=version)


def load_production_reporting(settings: DnaSettings) -> dict[str, Any]:
    """Load the pinned company reporting config used for portal layout."""
    from meshflow.dna.governance import load_governance_reporting_payload
    from meshflow.dna.workflow import load_workflow_state

    dna_pack_id = settings.dna_config_id
    reporting_id = settings.reporting_config_id
    state = load_workflow_state(settings, dna_pack_id)
    version = (
        settings.pack_version
        or state.get("active_reporting_version")
        or state.get("active_version")
    )
    if not version:
        raise FileNotFoundError(
            f"Company reporting config {reporting_id!r} has no pinned production version. "
            "Deploy DnaStack (or run meshflow-dna init-client) to seed it from "
            f"{REPORTING_BOILERPLATE_NAME}."
        )

    payload = load_governance_reporting_payload(settings, dna_pack_id, str(version))
    if not payload:
        raise FileNotFoundError(
            f"Company reporting config {reporting_id!r} v{version} not found under "
            f"governance/{dna_pack_id}/. Deploy DnaStack (or run meshflow-dna init-client) "
            f"to seed it from {REPORTING_BOILERPLATE_NAME}."
        )
    return normalize_reporting_identity(settings, payload, version=str(version))
