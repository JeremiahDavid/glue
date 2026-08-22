"""KPI Generator proposal artifact key layout."""

from __future__ import annotations

from hiveflow.storage.paths import governance_pack_prefix


def kpi_generator_proposals_prefix(pack_id: str) -> str:
    return f"{governance_pack_prefix(pack_id)}/kpi_generator/proposals/"


def kpi_generator_proposal_key(pack_id: str, proposal_id: str) -> str:
    pid = proposal_id.strip().lower()
    if not pid or ".." in pid or "/" in pid:
        raise ValueError(f"Invalid proposal id: {proposal_id!r}")
    return f"{governance_pack_prefix(pack_id)}/kpi_generator/proposals/{pid}.json"
