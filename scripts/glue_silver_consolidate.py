"""Glue Python Shell entry: silver_stg consolidate for one or all configured connectors.

Deployed as the Glue job script; not intended for local ``python scripts/...`` use.
See ``hiveflow.silver.glue_runner`` for the consolidate implementation.
"""

from __future__ import annotations

import json
import os
import sys

from awsglue.utils import getResolvedOptions  # type: ignore[import-untyped]

_REQUIRED_ARGS = [
    "HIVEFLOW_COMPANY",
    "HIVEFLOW_ENVIRONMENT",
    "HIVEFLOW_S3_BUCKET",
]

_OPTIONAL_DEFAULTS = {
    "HIVEFLOW_SOURCE": "",
    "full_rebuild": "false",
}


def _bootstrap_glue_deps() -> None:
    """Glue downloads extra-py-files but needs extracted libs for boto3/pyarrow imports."""
    import glob
    import tempfile
    import zipfile

    candidates: list[str] = []
    for root in (os.getcwd(), "/tmp"):
        candidates.extend(glob.glob(os.path.join(root, "glue-python-libs-*", "*.zip")))
    for zip_path in sorted(set(candidates)):
        extract_dir = os.path.join(tempfile.gettempdir(), "hiveflow-glue-extra")
        if not os.path.isdir(extract_dir):
            os.makedirs(extract_dir, exist_ok=True)
            with zipfile.ZipFile(zip_path) as archive:
                archive.extractall(extract_dir)
        if extract_dir not in sys.path:
            sys.path.insert(0, extract_dir)


def _apply_job_env(args: dict[str, str]) -> None:
    for key in (
        "HIVEFLOW_COMPANY",
        "HIVEFLOW_ENVIRONMENT",
        "HIVEFLOW_S3_BUCKET",
        "HIVEFLOW_SOURCE",
    ):
        value = str(args.get(key, "")).strip()
        if value:
            os.environ[key] = value


def _arg_value(name: str, *, default: str = "") -> str:
    """Read a Glue-style ``--name value`` argument without exiting when absent."""
    token = f"--{name}"
    for index, arg in enumerate(sys.argv):
        if arg == token and index + 1 < len(sys.argv):
            value = str(sys.argv[index + 1]).strip()
            if value.startswith("--"):
                return default
            return value
        if arg.lower().startswith(f"{token.lower()}="):
            return str(arg.split("=", 1)[1])
    return default


def _resolve_glue_args() -> dict[str, str]:
    """Resolve Glue job args; optional keys use defaults when absent."""
    args = getResolvedOptions(sys.argv, _REQUIRED_ARGS)
    for key, default in _OPTIONAL_DEFAULTS.items():
        args[key] = _arg_value(key, default=default)
    return args


def main() -> None:
    _bootstrap_glue_deps()
    args = _resolve_glue_args()
    _apply_job_env(args)

    from hiveflow.silver.glue_runner import resolve_glue_consolidate_runtime, run_silver_consolidate

    source, full_rebuild = resolve_glue_consolidate_runtime(args)
    result = run_silver_consolidate(
        source=source,
        full_rebuild=full_rebuild,
        bucket=str(args.get("HIVEFLOW_S3_BUCKET") or "").strip(),
    )
    print(json.dumps(result, default=str))


if __name__ == "__main__":
    import traceback

    exit_code = 0
    try:
        main()
    except Exception:
        traceback.print_exc()
        exit_code = 1
    sys.stdout.flush()
    sys.stderr.flush()
    # PyArrow's C++ runtime can abort during interpreter shutdown on Glue Python
    # Shell (exit 134) even after a successful consolidate. Skip native destructors.
    os._exit(exit_code)
