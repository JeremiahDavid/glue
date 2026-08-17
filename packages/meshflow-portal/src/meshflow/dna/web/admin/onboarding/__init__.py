"""Platform admin client onboarding wizard."""

from meshflow.dna.web.admin.onboarding.guides import (
    load_connector_guide_markdown,
    render_connector_guide_html,
)
from meshflow.dna.web.admin.onboarding.handlers import (
    build_status,
    client_deploy_status,
    create_client_from_form,
    list_onboarding_clients,
    save_client_from_form,
    save_connector_secret,
    trigger_deploy,
    validate_connector,
)
from meshflow.dna.web.admin.onboarding.views import (
    render_client_detail,
    render_onboarding_home,
    render_onboarding_wizard,
)

__all__ = [
    "build_status",
    "client_deploy_status",
    "create_client_from_form",
    "list_onboarding_clients",
    "load_connector_guide_markdown",
    "render_client_detail",
    "render_connector_guide_html",
    "render_onboarding_home",
    "render_onboarding_wizard",
    "save_client_from_form",
    "save_connector_secret",
    "trigger_deploy",
    "validate_connector",
]
