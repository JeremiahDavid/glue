from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_glue_python39_compat_check_passes() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    script = repo_root / "scripts" / "check_glue_py39_compat.py"
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_glue_bronze_import_graph_is_py39_safe() -> None:
    """Smoke-test modules reachable from the BC bronze Glue ingest path."""
    from hiveflow.entity_registry import ensure_connectors_registered
    from hiveflow.ingest.glue_runner import resolve_glue_ingest_runtime, run_bronze_ingest_glue

    ensure_connectors_registered()
    run_id, full_load = resolve_glue_ingest_runtime({"run_id": "test", "full_load": "false"})
    assert run_id == "test"
    assert full_load is False
    assert callable(run_bronze_ingest_glue)


def test_glue_silver_import_graph_is_py39_safe() -> None:
    """Smoke-test modules reachable from the silver consolidate Glue path."""
    from hiveflow.silver.glue_runner import resolve_glue_consolidate_runtime, run_silver_consolidate

    source, full_rebuild = resolve_glue_consolidate_runtime({"source": "qbo", "full_rebuild": "false"})
    assert source == "qbo"
    assert full_rebuild is False
    assert callable(run_silver_consolidate)
