from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from meshflow.dna.settings import DnaSettings
from meshflow.dna.store import read_staging_output, write_json_artifact, write_production_output


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
        "compiler_hash": compile_manifest.get("compiler_hash"),
        "compiled_at": compile_manifest.get("compiled_at"),
        "validated_at": validation_result.get("validated_at"),
        "published_at": datetime.now(UTC).isoformat(),
        "validation": validation_result,
        "outputs": published,
    }
    manifest_path = write_json_artifact(settings, f"{settings.gold_dna_prefix}/manifest.json", manifest)
    manifest["manifest_path"] = manifest_path
    return manifest
