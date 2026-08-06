"""Locate the meshflow git/repo root from installed package locations."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def find_project_root(start: Path | None = None) -> Path:
    """Walk parents until ``config.yaml`` + repo or Lambda bundle markers appear."""
    here = (start or Path(__file__)).resolve()
    for candidate in [here, *here.parents]:
        if not (candidate / "config.yaml").is_file():
            continue
        if (candidate / "packages").is_dir() or (candidate / "src" / "meshflow").is_dir():
            return candidate
        # Lambda/CDK bundle: config.yaml + flat merged meshflow/ at asset root.
        if (candidate / "meshflow").is_dir():
            return candidate
    # Fallback: packages/<name>/src/meshflow/<module>.py → parents[4]
    root = Path(__file__).resolve()
    if len(root.parents) > 4:
        return root.parents[4]
    raise FileNotFoundError(
        "Could not locate meshflow project root (expected config.yaml with packages/, "
        "src/meshflow/, or meshflow/ alongside it)"
    )
