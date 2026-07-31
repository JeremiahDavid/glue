from __future__ import annotations

from typing import Any

from meshflow.dna.compile import compile_pack
from meshflow.dna.publish import publish_staging
from meshflow.dna.settings import DnaSettings
from meshflow.dna.validate import run_validation
from meshflow.dna.workflow import load_production_pack


def run_dna_pipeline(settings: DnaSettings) -> dict[str, Any]:
    pack = load_production_pack(settings)
    compile_manifest = compile_pack(settings, pack)
    validation_result = run_validation(settings, pack)
    if validation_result["status"] != "passed":
        return {
            "status": "validation_failed",
            "compile": compile_manifest,
            "validation": validation_result,
        }
    publish_manifest = publish_staging(
        settings,
        compile_manifest=compile_manifest,
        validation_result=validation_result,
    )
    return {
        "status": "published",
        "compile": compile_manifest,
        "validation": validation_result,
        "publish": publish_manifest,
    }


def handler(event: dict[str, Any] | None, _context: Any) -> dict[str, Any]:
    from meshflow.dna.runtime import resolve_dna_settings

    settings = resolve_dna_settings(event=event)
    action = str((event or {}).get("action", "publish")).strip().lower()
    pack = load_production_pack(settings)

    if action == "compile":
        return compile_pack(settings, pack)
    if action == "validate":
        compile_pack(settings, pack)
        return run_validation(settings, pack)
    if action == "publish":
        return run_dna_pipeline(settings)
    raise ValueError(f"Unknown DNA action {action!r}")


def lambda_handler(event: dict[str, Any] | None, context: Any) -> dict[str, Any]:
    return handler(event, context)
