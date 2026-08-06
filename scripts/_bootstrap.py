"""Add package src trees to sys.path so scripts run without pip install -e."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_PACKAGE_SRC = [
    _ROOT / "packages" / "meshflow-platform" / "src",
    _ROOT / "packages" / "meshflow-connectors" / "src",
    _ROOT / "packages" / "meshflow-lake" / "src",
    _ROOT / "packages" / "meshflow-dna" / "src",
    _ROOT / "packages" / "meshflow-portal" / "src",
    _ROOT / "packages" / "meshflow" / "src",
]
for path in reversed(_PACKAGE_SRC):
    if path.is_dir():
        entry = str(path)
        if entry not in sys.path:
            sys.path.insert(0, entry)
