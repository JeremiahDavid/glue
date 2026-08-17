"""Platform admin client onboarding wizard."""

from meshflow.dna.web.admin.onboarding.guides import (
    load_connector_guide_markdown,
    render_connector_guide_html,
)
from meshflow.dna.web.admin.onboarding.handlers import (
    build_status,
    client_deploy_status,
    connectors_ready_for_deploy,
    create_client_from_form,
    get_onboarding_client,
    list_connector_companies,
    list_onboarding_clients,
    load_client_connector_credentials,
    load_connector_credentials,
    save_client_from_form,
    save_connector_secret,
    trigger_deploy,
    validate_connector,
)
from meshflow.dna.web.admin.onboarding.views import (
    render_client_deploy,
    render_client_detail,
    render_connector_credentials,
    render_onboarding_home,
    render_onboarding_wizard,
)

__all__ = [
    "build_status",
    "client_deploy_status",
    "connectors_ready_for_deploy",
    "create_client_from_form",
    "get_onboarding_client",
    "list_connector_companies",
    "list_onboarding_clients",
    "load_client_connector_credentials",
    "load_connector_credentials",
    "load_connector_guide_markdown",
    "render_client_deploy",
    "render_client_detail",
    "render_connector_credentials",
    "render_connector_guide_html",
    "render_onboarding_home",
    "render_onboarding_wizard",
    "save_client_from_form",
    "save_connector_secret",
    "trigger_deploy",
    "validate_connector",
]
