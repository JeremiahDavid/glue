"""Admin Config Assistant — Bedrock chat for DNA/reporting governance proposals."""

from meshflow.dna.web.portal.config_assistant.service import (
    approve_proposal,
    deny_proposal,
    get_active_proposal,
    load_base_configs,
    load_proposal_reporting,
    proposal_view,
    run_chat_turn,
    submit_chat_turn,
)

__all__ = [
    "approve_proposal",
    "deny_proposal",
    "get_active_proposal",
    "load_base_configs",
    "load_proposal_reporting",
    "proposal_view",
    "run_chat_turn",
    "submit_chat_turn",
]
