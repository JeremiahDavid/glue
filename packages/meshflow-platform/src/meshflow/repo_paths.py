"""Locate the meshflow git/repo root from installed package locations."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def find_project_root(start: Path | None = None) -> Path:
    """Walk parents until ``config.yaml`` + ``packages/`` (or legacy ``src/``) appear."""
    here = (start or Path(__file__)).resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "config.yaml").is_file() and (
            (candidate / "packages").is_dir() or (candidate / "src" / "meshflow").is_dir()
        ):
            return candidate
    # Fallback: packages/<name>/src/meshflow/<module>.py → parents[4]
    return Path(__file__).resolve().parents[4]
