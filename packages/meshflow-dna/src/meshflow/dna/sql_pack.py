"""Versioned Athena SQL packs pinned under DNA governance semvers.

Layout::

    governance/{company}_dna_config/v{semver}/sql/manifest.yaml
    governance/{company}_dna_config/v{semver}/sql/silver/*.sql
    governance/{company}_dna_config/v{semver}/sql/gold/*.sql

Once approved in the portal, SQL files are immutable for that semver.
Scheduled refreshes replay them verbatim (checksum verified).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from meshflow.dna.settings import DnaSettings
from meshflow.dna.store import read_text_artifact, read_yaml_artifact, write_text_artifact, write_yaml_artifact
from meshflow.storage.paths import (
    governance_sql_file_key,
    governance_sql_manifest_key,
)

SqlLayer = Literal["silver", "gold"]
SqlMode = Literal["add_columns", "fact_table", "kpi"]

_ID_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_\-]{0,127}$")


@dataclass
class SqlTransform:
    id: str
    layer: SqlLayer
    mode: SqlMode
    file: str
    sha256: str
    target_entity: str | None = None
    output_id: str | None = None
    depends_on: list[str] = field(default_factory=list)
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        if not self.depends_on:
            payload.pop("depends_on", None)
        if not self.target_entity:
            payload.pop("target_entity", None)
        if not self.output_id:
            payload.pop("output_id", None)
        if not self.description:
            payload.pop("description", None)
        return payload


@dataclass
class SqlPack:
    version: str
    transforms: list[SqlTransform] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "transforms": [t.to_dict() for t in self.transforms],
        }

    def by_layer(self, layer: SqlLayer) -> list[SqlTransform]:
        return [t for t in self.transforms if t.layer == layer]


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def parse_sql_manifest(payload: dict[str, Any] | None) -> SqlPack | None:
    if not payload or not isinstance(payload, dict):
        return None
    version = str(payload.get("version") or "").strip()
    raw_transforms = payload.get("transforms") or []
    if not isinstance(raw_transforms, list):
        raise ValueError("sql manifest transforms must be a list")
    transforms: list[SqlTransform] = []
    for item in raw_transforms:
        if not isinstance(item, dict):
            raise ValueError("sql transform entries must be mappings")
        transforms.append(_parse_transform(item))
    _validate_pack(transforms)
    return SqlPack(version=version or "0.0.0", transforms=transforms)


def _parse_transform(item: dict[str, Any]) -> SqlTransform:
    tid = str(item.get("id") or "").strip()
    if not _ID_RE.match(tid):
        raise ValueError(f"Invalid sql transform id: {tid!r}")
    layer = str(item.get("layer") or "").strip().lower()
    if layer not in {"silver", "gold"}:
        raise ValueError(f"sql transform {tid}: layer must be silver or gold")
    mode = str(item.get("mode") or "").strip().lower()
    if mode not in {"add_columns", "fact_table", "kpi"}:
        raise ValueError(f"sql transform {tid}: invalid mode {mode!r}")
    file_rel = str(item.get("file") or "").strip().replace("\\", "/")
    if not file_rel or ".." in file_rel.split("/"):
        raise ValueError(f"sql transform {tid}: invalid file path")
    expected_prefix = f"{layer}/"
    if not file_rel.startswith(expected_prefix):
        raise ValueError(f"sql transform {tid}: file must start with {expected_prefix!r}")
    digest = str(item.get("sha256") or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError(f"sql transform {tid}: sha256 must be 64 hex chars")
    target_entity = str(item.get("target_entity") or "").strip() or None
    output_id = str(item.get("output_id") or "").strip() or None
    if layer == "silver":
        if mode != "add_columns":
            raise ValueError(f"sql transform {tid}: silver mode must be add_columns")
        if not target_entity:
            raise ValueError(f"sql transform {tid}: target_entity required for silver")
        if output_id:
            raise ValueError(f"sql transform {tid}: output_id not allowed on silver")
    else:
        if mode == "add_columns":
            raise ValueError(f"sql transform {tid}: add_columns belongs on silver")
        if not output_id:
            raise ValueError(f"sql transform {tid}: output_id required for gold")
        if target_entity:
            raise ValueError(f"sql transform {tid}: target_entity not allowed on gold")
    depends_raw = item.get("depends_on") or []
    if not isinstance(depends_raw, list):
        raise ValueError(f"sql transform {tid}: depends_on must be a list")
    depends = [str(x).strip() for x in depends_raw if str(x).strip()]
    return SqlTransform(
        id=tid,
        layer=layer,  # type: ignore[arg-type]
        mode=mode,  # type: ignore[arg-type]
        file=file_rel,
        sha256=digest,
        target_entity=target_entity,
        output_id=output_id,
        depends_on=depends,
        description=str(item.get("description") or "").strip(),
    )


def _validate_pack(transforms: list[SqlTransform]) -> None:
    seen: set[str] = set()
    for t in transforms:
        if t.id in seen:
            raise ValueError(f"Duplicate sql transform id: {t.id}")
        seen.add(t.id)
    ids = {t.id for t in transforms}
    for t in transforms:
        for dep in t.depends_on:
            if dep not in ids:
                raise ValueError(f"sql transform {t.id}: unknown depends_on {dep!r}")


def load_sql_pack(
    settings: DnaSettings,
    *,
    pack_id: str | None = None,
    version: str | None = None,
) -> SqlPack | None:
    """Load pinned SQL pack for a governance version (or active version)."""
    pid = (pack_id or settings.dna_config_id).strip().lower()
    ver = (version or "").strip()
    if not ver:
        from meshflow.dna.governance import load_governance_workflow

        workflow = load_governance_workflow(settings, pid) or {}
        ver = str(settings.pack_version or workflow.get("active_version") or "").strip()
    if not ver:
        return None
    payload = read_yaml_artifact(settings, governance_sql_manifest_key(pid, ver))
    pack = parse_sql_manifest(payload if isinstance(payload, dict) else None)
    if pack is None:
        return None
    if not pack.version:
        pack.version = ver
    return pack


def load_transform_sql(
    settings: DnaSettings,
    transform: SqlTransform,
    *,
    pack_id: str | None = None,
    version: str | None = None,
    verify_checksum: bool = True,
) -> str:
    """Load exact approved SQL text; optionally verify sha256."""
    pid = (pack_id or settings.dna_config_id).strip().lower()
    ver = (version or "").strip()
    if not ver:
        pack = load_sql_pack(settings, pack_id=pid)
        if pack is None:
            raise FileNotFoundError("No SQL pack pinned for active version")
        ver = pack.version
    key = governance_sql_file_key(pid, ver, transform.file)
    text = read_text_artifact(settings, key)
    if text is None:
        raise FileNotFoundError(f"Missing SQL file: {key}")
    if verify_checksum:
        digest = sha256_text(text)
        if digest != transform.sha256:
            raise ValueError(
                f"SQL checksum mismatch for {transform.id}: "
                f"expected {transform.sha256}, got {digest}"
            )
    return text


def build_sql_pack(
    *,
    version: str,
    transforms: list[dict[str, Any]],
    sql_by_file: dict[str, str],
) -> tuple[SqlPack, dict[str, str]]:
    """Build a SqlPack from file contents; fills sha256 from sql_by_file."""
    filled: list[dict[str, Any]] = []
    for item in transforms:
        entry = dict(item)
        rel = str(entry.get("file") or "").strip().replace("\\", "/")
        if rel not in sql_by_file:
            raise ValueError(f"Missing SQL body for file {rel!r}")
        entry["sha256"] = sha256_text(sql_by_file[rel])
        filled.append(entry)
    pack = parse_sql_manifest({"version": version, "transforms": filled})
    assert pack is not None
    return pack, {rel: sql_by_file[rel] for rel in sql_by_file}


def save_sql_pack(
    settings: DnaSettings,
    pack: SqlPack,
    sql_by_file: dict[str, str],
    *,
    pack_id: str | None = None,
) -> dict[str, Any]:
    """Persist manifest + exact SQL files under the pack version prefix."""
    pid = (pack_id or settings.dna_config_id).strip().lower()
    version = pack.version.strip()
    if not version:
        raise ValueError("sql pack version is required")
    for transform in pack.transforms:
        body = sql_by_file.get(transform.file)
        if body is None:
            raise ValueError(f"Missing SQL body for {transform.file}")
        digest = sha256_text(body)
        if digest != transform.sha256:
            raise ValueError(f"Checksum mismatch before save for {transform.id}")
        write_text_artifact(
            settings,
            governance_sql_file_key(pid, version, transform.file),
            body,
            content_type="application/sql; charset=utf-8",
        )
    manifest_key = governance_sql_manifest_key(pid, version)
    write_yaml_artifact(settings, manifest_key, pack.to_dict())
    return {
        "pack_id": pid,
        "version": version,
        "manifest_key": manifest_key,
        "transform_count": len(pack.transforms),
    }


def ordered_transforms(transforms: list[SqlTransform]) -> list[SqlTransform]:
    """Topological order by depends_on (stable for independent items)."""
    remaining = {t.id: t for t in transforms}
    done: list[SqlTransform] = []
    seen: set[str] = set()
    while remaining:
        ready = [
            tid
            for tid, t in remaining.items()
            if all(dep in seen or dep not in remaining for dep in t.depends_on)
        ]
        if not ready:
            raise ValueError("Cycle detected in sql transform depends_on")
        ready.sort()
        for tid in ready:
            t = remaining.pop(tid)
            done.append(t)
            seen.add(tid)
    return done
