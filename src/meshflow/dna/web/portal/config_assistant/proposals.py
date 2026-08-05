"""Governance config proposals — staged DNA/reporting edits before pin."""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from difflib import unified_diff
from typing import Any

import yaml

from meshflow.dna.settings import DnaSettings
from meshflow.dna.store import (
    read_json_artifact,
    read_text_artifact,
    write_json_artifact,
    write_text_artifact,
)
from meshflow.storage.paths import (
    governance_proposal_conversation_key,
    governance_proposal_dna_key,
    governance_proposal_meta_key,
    governance_proposal_reporting_key,
    governance_proposals_prefix,
)

_SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def bump_patch_version(version: str) -> str:
    match = _SEMVER_RE.match(str(version).strip())
    if not match:
        return "1.0.1"
    major, minor, patch = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
    return f"{major}.{minor}.{patch + 1}"


def new_proposal_id() -> str:
    return uuid.uuid4().hex[:12]


def unified_yaml_diff(before: str, after: str, *, from_label: str, to_label: str) -> str:
    before_lines = before.splitlines(keepends=True)
    after_lines = after.splitlines(keepends=True)
    if before_lines and not before_lines[-1].endswith("\n"):
        before_lines[-1] += "\n"
    if after_lines and not after_lines[-1].endswith("\n"):
        after_lines[-1] += "\n"
    return "".join(
        unified_diff(
            before_lines,
            after_lines,
            fromfile=from_label,
            tofile=to_label,
            lineterm="",
        )
    )


def dump_yaml(payload: dict[str, Any]) -> str:
    return yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)


def normalize_yaml_for_compare(text: str) -> str:
    """Canonicalize YAML for equality checks, ignoring the top-level version field."""
    try:
        payload = yaml.safe_load(text) or {}
    except yaml.YAMLError:
        return text.strip()
    if not isinstance(payload, dict):
        return text.strip()
    normalized = dict(payload)
    normalized.pop("version", None)
    return dump_yaml(normalized)


def yaml_content_changed(before: str, after: str) -> bool:
    return normalize_yaml_for_compare(before) != normalize_yaml_for_compare(after)


def load_open_proposal_id(settings: DnaSettings) -> str | None:
    """Return the most recent open proposal id, if any."""
    pack_id = settings.dna_config_id
    prefix = governance_proposals_prefix(pack_id).rstrip("/") + "/"
    candidates: list[tuple[str, str]] = []

    if settings.s3_bucket:
        import boto3

        client = boto3.client("s3")
        paginator = client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=settings.s3_bucket, Prefix=prefix):
            for obj in page.get("Contents") or []:
                key = str(obj.get("Key") or "")
                if not key.endswith("/meta.json"):
                    continue
                proposal_id = key[len(prefix) :].split("/", 1)[0]
                meta = read_json_artifact(settings, key)
                if meta and meta.get("status") in {"open", "running"}:
                    candidates.append((str(meta.get("updated_at") or meta.get("created_at") or ""), proposal_id))
    else:
        from meshflow.storage.paths import prefix_path

        root = prefix_path(settings.data_dir, governance_proposals_prefix(pack_id))
        if root.is_dir():
            for child in root.iterdir():
                if not child.is_dir():
                    continue
                meta = read_json_artifact(
                    settings, governance_proposal_meta_key(pack_id, child.name)
                )
                if meta and meta.get("status") in {"open", "running"}:
                    candidates.append(
                        (str(meta.get("updated_at") or meta.get("created_at") or ""), child.name)
                    )

    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def load_proposal(settings: DnaSettings, proposal_id: str) -> dict[str, Any] | None:
    pack_id = settings.dna_config_id
    meta = read_json_artifact(settings, governance_proposal_meta_key(pack_id, proposal_id))
    if not meta:
        return None
    dna_text = read_text_artifact(settings, governance_proposal_dna_key(pack_id, proposal_id)) or ""
    reporting_text = (
        read_text_artifact(settings, governance_proposal_reporting_key(pack_id, proposal_id)) or ""
    )
    conversation = read_json_artifact(
        settings, governance_proposal_conversation_key(pack_id, proposal_id)
    ) or {"messages": []}
    return {
        "meta": meta,
        "dna_yaml": dna_text,
        "reporting_yaml": reporting_text,
        "conversation": conversation,
    }


def save_proposal(
    settings: DnaSettings,
    *,
    proposal_id: str,
    meta: dict[str, Any],
    dna_yaml: str,
    reporting_yaml: str,
    conversation: dict[str, Any],
) -> dict[str, Any]:
    pack_id = settings.dna_config_id
    now = datetime.now(UTC).isoformat()
    meta = dict(meta)
    meta.setdefault("proposal_id", proposal_id)
    meta.setdefault("created_at", now)
    meta["updated_at"] = now
    meta["pack_id"] = pack_id
    meta["company"] = settings.company

    write_json_artifact(settings, governance_proposal_meta_key(pack_id, proposal_id), meta)
    write_text_artifact(
        settings,
        governance_proposal_dna_key(pack_id, proposal_id),
        dna_yaml,
        content_type="application/yaml; charset=utf-8",
    )
    write_text_artifact(
        settings,
        governance_proposal_reporting_key(pack_id, proposal_id),
        reporting_yaml,
        content_type="application/yaml; charset=utf-8",
    )
    write_json_artifact(
        settings,
        governance_proposal_conversation_key(pack_id, proposal_id),
        conversation,
    )
    return meta


def proposal_diffs(
    *,
    base_dna_yaml: str,
    base_reporting_yaml: str,
    proposed_dna_yaml: str,
    proposed_reporting_yaml: str,
    base_version: str,
    next_version: str,
    dna_base_version: str | None = None,
    dna_next_version: str | None = None,
    reporting_base_version: str | None = None,
    reporting_next_version: str | None = None,
) -> dict[str, str]:
    dna_from = dna_base_version or base_version
    dna_to = dna_next_version or next_version
    reporting_from = reporting_base_version or base_version
    reporting_to = reporting_next_version or next_version
    dna_diff = ""
    reporting_diff = ""
    if yaml_content_changed(base_dna_yaml, proposed_dna_yaml):
        dna_diff = unified_yaml_diff(
            base_dna_yaml,
            proposed_dna_yaml,
            from_label=f"dna@v{dna_from}",
            to_label=f"dna@v{dna_to}",
        )
    if yaml_content_changed(base_reporting_yaml, proposed_reporting_yaml):
        reporting_diff = unified_yaml_diff(
            base_reporting_yaml,
            proposed_reporting_yaml,
            from_label=f"reporting@v{reporting_from}",
            to_label=f"reporting@v{reporting_to}",
        )
    return {"dna": dna_diff, "reporting": reporting_diff}
