"""Field semantics context for the Config Assistant."""

from __future__ import annotations

from typing import Any

from meshflow.dna.field_semantics import build_assistant_field_semantics_context
from meshflow.dna.settings import DnaSettings


def build_field_semantics_assistant_context(settings: DnaSettings) -> dict[str, Any]:
    return build_assistant_field_semantics_context(settings)
