from __future__ import annotations

from datetime import datetime
from hiveflow.compat import UTC
from typing import Any

from hiveflow.dna.settings import DnaSettings
from hiveflow.dna.store import read_staging_output, write_json_artifact, write_production_output


def publish_staging(
    settings: DnaSettings,
    *,
    compile_manifest: dict[str, Any],
    validation_result: dict[str, Any],
) -> dict[str, Any]:
    if validation_result.get("status") != "passed":
        raise ValueError("Cannot publish DNA outputs — validation did not pass")

    published: list[dict[str, Any]] = []
    for output in compile_manifest.get("outputs", []):
        output_id = str(output["output_id"])
        rows = read_staging_output(settings, output_id)
        path = write_production_output(settings, output_id, rows)
        published.append(
            {
                "output_id": output_id,
                "row_count": len(rows),
                "path": path,
            }
        )

    manifest = {
        "status": "published",
        "pack_id": compile_manifest.get("pack_id"),
        "pack_version": compile_manifest.get("pack_version"),
        "silver_sql_pack_version": compile_manifest.get("silver_sql_pack_version")
        or compile_manifest.get("pack_version"),
        "compiler_hash": compile_manifest.get("compiler_hash"),
        "compiled_at": compile_manifest.get("compiled_at"),
        "validated_at": validation_result.get("validated_at"),
        "published_at": datetime.now(UTC).isoformat(),
        "validation": validation_result,
        "outputs": published,
        "mode": "python_compile",
    }
    manifest_path = write_json_artifact(settings, f"{settings.gold_dna_prefix}/manifest.json", manifest)
    manifest["manifest_path"] = manifest_path
    return manifest


def write_gold_refresh_manifest(
    settings: DnaSettings,
    *,
    pack_version: str,
    silver_sql_pack_version: str = "",
    mode: str = "athena_sql",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Record DNA silver + gold refresh versions for portal stale detection."""
    manifest: dict[str, Any] = {
        "status": "published",
        "pack_id": settings.dna_config_id,
        "pack_version": pack_version,
        "silver_sql_pack_version": silver_sql_pack_version or pack_version,
        "published_at": datetime.now(UTC).isoformat(),
        "mode": mode,
    }
    if extra:
        manifest.update(extra)
    manifest_path = write_json_artifact(
        settings, f"{settings.gold_dna_prefix}/manifest.json", manifest
    )
    manifest["manifest_path"] = manifest_path
    return manifest
