"""Platform admin client onboarding wizard."""

from meshflow.dna.web.admin.onboarding.handlers import (
    build_status,
    client_deploy_status,
    create_client_from_form,
    list_onboarding_clients,
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
    "render_client_detail",
    "render_onboarding_home",
    "render_onboarding_wizard",
    "save_connector_secret",
    "trigger_deploy",
    "validate_connector",
]
