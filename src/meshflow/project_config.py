from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterator

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.yaml"
PROTECTED_ENVIRONMENTS = frozenset({"prod"})
PLACEHOLDER_ACCOUNT_PREFIXES = ("REPLACE", "CHANGEME", "YOUR_")


def cost_allocation_tags(
    company: str,
    environment: str,
    *,
    application: str = "meshflow",
) -> dict[str, str]:
    """Standard AWS resource tags for cost and billing attribution."""
    company_slug = company.strip()
    environment_slug = environment.strip()
    if not company_slug:
        raise ValueError("company is required for cost allocation tags")
    if not environment_slug:
        raise ValueError("environment is required for cost allocation tags")

    return {
        "Company": company_slug,
        "Environment": environment_slug,
        "Application": application.strip() or "meshflow",
    }


def aws_tag_list(tags: dict[str, str]) -> list[dict[str, str]]:
    """Convert a tag mapping to the list format expected by boto3 APIs."""
    return [{"Key": key, "Value": value} for key, value in tags.items()]


def default_config_path() -> Path:
    configured = os.getenv("MESHFLOW_CONFIG_PATH", "").strip()
    if configured:
        return Path(configured)

    meshflow_dir = Path(__file__).resolve().parent
    bundled = meshflow_dir.parent / "config.yaml"
    if bundled.exists():
        return bundled

    return DEFAULT_CONFIG_PATH


@lru_cache(maxsize=1)
def load_project_config(path: Path | None = None) -> dict[str, Any]:
    config_path = path or default_config_path()
    if not config_path.exists():
        return {}

    with config_path.open(encoding="utf-8") as handle:
        payload = yaml.safe_load(handle)

    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise ValueError(f"{config_path} must contain a YAML mapping at the top level")
    return payload


def _available_companies(config: dict[str, Any]) -> list[str]:
    companies = config.get("companies", {})
    if not isinstance(companies, dict):
        return []
    return sorted(companies)


def _available_environments(config: dict[str, Any], company: str) -> list[str]:
    company_cfg = config.get("companies", {}).get(company, {})
    environments = company_cfg.get("environments", {})
    if not isinstance(environments, dict):
        return []
    return sorted(environments)


def resolve_selection(
    company: str | None = None,
    environment: str | None = None,
    *,
    path: Path | None = None,
) -> tuple[str, str]:
    config = load_project_config(path)
    defaults = config.get("default", {})
    if not isinstance(defaults, dict):
        defaults = {}

    selected_company = (
        company
        or os.getenv("MESHFLOW_COMPANY", "").strip()
        or str(defaults.get("company", "")).strip()
    )
    selected_environment = (
        environment
        or os.getenv("MESHFLOW_ENVIRONMENT", "").strip()
        or str(defaults.get("environment", "")).strip()
    )

    if not selected_company or not selected_environment:
        raise ValueError(
            "Company and environment must be set via args, MESHFLOW_COMPANY/MESHFLOW_ENVIRONMENT, "
            "or default.company/default.environment in config.yaml"
        )

    companies = _available_companies(config)
    if selected_company not in companies:
        raise KeyError(
            f"Unknown company {selected_company!r}. Available companies: {', '.join(companies) or '(none)'}"
        )

    environments = _available_environments(config, selected_company)
    if selected_environment not in environments:
        raise KeyError(
            f"Unknown environment {selected_environment!r} for company {selected_company!r}. "
            f"Available environments: {', '.join(environments) or '(none)'}"
        )

    return selected_company, selected_environment


def get_environment_config(
    company: str,
    environment: str,
    *,
    path: Path | None = None,
) -> dict[str, Any]:
    config = load_project_config(path)
    env_config = config["companies"][company]["environments"][environment]
    if not isinstance(env_config, dict):
        raise ValueError(
            f"Environment config for {company}/{environment} must be a mapping"
        )
    return env_config


def get_config_value(
    key_path: str,
    default: Any = None,
    *,
    company: str | None = None,
    environment: str | None = None,
    path: Path | None = None,
) -> Any:
    selected_company, selected_environment = resolve_selection(
        company,
        environment,
        path=path,
    )
    value: Any = get_environment_config(selected_company, selected_environment, path=path)
    for part in key_path.split("."):
        if not isinstance(value, dict) or part not in value:
            return default
        value = value[part]
    return value


def iter_deploy_targets(
    *,
    company: str | None = None,
    environment: str | None = None,
    path: Path | None = None,
) -> Iterator[tuple[str, str, dict[str, Any]]]:
    config = load_project_config(path)

    if company or environment:
        selected_company, selected_environment = resolve_selection(
            company,
            environment,
            path=path,
        )
        yield (
            selected_company,
            selected_environment,
            get_environment_config(selected_company, selected_environment, path=path),
        )
        return

    for company_name in _available_companies(config):
        for environment_name in _available_environments(config, company_name):
            yield (
                company_name,
                environment_name,
                get_environment_config(company_name, environment_name, path=path),
            )


def ingest_stack_name(company: str, environment: str) -> str:
    return f"IngestStack-{company}-{environment}"


def ingest_stack_module_name(company: str) -> str:
    """Python module name for a company ingest stack file."""
    return f"ingeststack_{company.strip().lower()}"


CONNECTOR_NAMES = ("qbo", "qbd")


def get_connector_config(
    env_config: dict[str, Any],
    connector: str,
) -> dict[str, Any]:
    """Return per-connector settings from config.yaml."""
    connector = connector.strip().lower()
    cfg = env_config.get(connector, {})
    if isinstance(cfg, dict) and cfg:
        return cfg

    ingest_cfg = env_config.get("ingest", {})
    if isinstance(ingest_cfg, dict) and str(ingest_cfg.get("connector", "")).strip().lower() == connector:
        return ingest_cfg
    return {}


def iter_configured_connectors(
    env_config: dict[str, Any],
) -> Iterator[tuple[str, dict[str, Any]]]:
    """Yield (connector, config) for each connector block under an environment."""
    found = False
    for connector in CONNECTOR_NAMES:
        cfg = env_config.get(connector, {})
        if isinstance(cfg, dict) and cfg:
            found = True
            yield connector, cfg

    if found:
        return

    ingest_cfg = env_config.get("ingest", {})
    if isinstance(ingest_cfg, dict):
        connector = str(ingest_cfg.get("connector", "")).strip().lower()
        if connector:
            yield connector, ingest_cfg


def resolve_qbo_secret_name(
    company: str | None = None,
    environment: str | None = None,
    source: str | None = None,
    *,
    path: Path | None = None,
) -> str:
    """Derive the Secrets Manager name from config.yaml company/source/environment."""
    selected_company, selected_environment = resolve_selection(
        company,
        environment,
        path=path,
    )
    config = load_project_config(path)
    secrets_cfg = config.get("secrets", {})
    if not isinstance(secrets_cfg, dict):
        secrets_cfg = {}

    template = str(
        secrets_cfg.get(
            "secret_name_template",
            secrets_cfg.get("qbo_name_template", "meshflow-{company}-{source}-{environment}"),
        )
    ).strip()
    env_config = get_environment_config(selected_company, selected_environment, path=path)

    resolved_source = (source or os.getenv("MESHFLOW_SOURCE", "")).strip()
    if not resolved_source:
        connectors = list(iter_configured_connectors(env_config))
        if len(connectors) == 1:
            resolved_source = connectors[0][0]
        elif isinstance(env_config.get("ingest"), dict):
            resolved_source = str(env_config["ingest"].get("connector", "")).strip()
    if not resolved_source:
        raise ValueError(
            f"Could not resolve secret source for {selected_company}/{selected_environment}. "
            "Set source in the secrets YAML, MESHFLOW_SOURCE, or ingest.connector in config.yaml."
        )

    company_slug = selected_company.strip().lower()
    source_slug = resolved_source.strip().lower()
    environment_slug = selected_environment.strip().lower()

    return template.format(
        company=company_slug,
        source=source_slug,
        environment=environment_slug,
        tier=environment_slug,
    )


def resolve_data_bucket_name(
    company: str | None = None,
    environment: str | None = None,
    *,
    account: str | None = None,
    region: str | None = None,
    path: Path | None = None,
) -> str:
    """Derive the shared company data lake S3 bucket name from config.yaml."""
    selected_company, selected_environment = resolve_selection(
        company,
        environment,
        path=path,
    )
    config = load_project_config(path)
    secrets_cfg = config.get("secrets", {})
    if not isinstance(secrets_cfg, dict):
        secrets_cfg = {}

    env_config = get_environment_config(selected_company, selected_environment, path=path)

    resolved_account, resolved_region = resolve_aws_deploy_env(env_config, selected_environment)
    if account:
        resolved_account = account.strip()
    if region:
        resolved_region = region.strip()

    resolved_account = str(resolved_account or "").strip()
    resolved_region = str(resolved_region or "").strip()
    if not resolved_account:
        raise ValueError(
            "Could not resolve AWS account ID for bucket naming. "
            "Set CDK_DEFAULT_ACCOUNT or companies.*.environments.*.aws.account in config.yaml."
        )
    if not resolved_region:
        raise ValueError(
            "Could not resolve AWS region for bucket naming. "
            "Set CDK_DEFAULT_REGION or companies.*.environments.*.aws.region in config.yaml."
        )

    template = str(
        secrets_cfg.get(
            "data_bucket_name_template",
            secrets_cfg.get(
                "raw_bucket_name_template",
                "meshflow-{company}-{account}-{region}",
            ),
        )
    ).strip()
    company_slug = selected_company.strip().lower()
    environment_slug = selected_environment.strip().lower()

    return template.format(
        company=company_slug,
        environment=environment_slug,
        account=resolved_account,
        region=resolved_region.lower(),
        tier=str(env_config.get("qbo", {}).get("tier", environment_slug)).strip().lower()
        if isinstance(env_config.get("qbo"), dict)
        else environment_slug,
    )


def resolve_raw_bucket_name(
    company: str | None = None,
    environment: str | None = None,
    *,
    account: str | None = None,
    region: str | None = None,
    path: Path | None = None,
) -> str:
    """Backward-compatible alias for resolve_data_bucket_name."""
    return resolve_data_bucket_name(
        company,
        environment,
        account=account,
        region=region,
        path=path,
    )


def resolve_ingest_s3_prefix(
    company: str | None = None,
    environment: str | None = None,
    *,
    source: str | None = None,
    path: Path | None = None,
) -> str:
    """Derive the raw-layer prefix for a connector (e.g. raw/qbd)."""
    from meshflow.storage.paths import raw_source_prefix

    selected_company, selected_environment = resolve_selection(
        company,
        environment,
        path=path,
    )
    env_config = get_environment_config(selected_company, selected_environment, path=path)

    resolved_source = (source or os.getenv("MESHFLOW_SOURCE", "")).strip().lower()
    if not resolved_source:
        connectors = list(iter_configured_connectors(env_config))
        if len(connectors) == 1:
            resolved_source = connectors[0][0]

    connector_cfg = get_connector_config(env_config, resolved_source) if resolved_source else {}
    explicit_prefix = str(connector_cfg.get("s3_prefix", "")).strip().strip("/")
    if explicit_prefix:
        return explicit_prefix

    if not resolved_source:
        ingest_cfg = env_config.get("ingest", {})
        if isinstance(ingest_cfg, dict):
            resolved_source = str(ingest_cfg.get("connector", "qbo")).strip().lower()

    if not resolved_source:
        raise ValueError(
            f"Set a connector block (qbo/qbd) or MESHFLOW_SOURCE for "
            f"{selected_company}/{selected_environment} in config.yaml"
        )

    return raw_source_prefix(resolved_source)


def glue_database_name(
    company: str | None = None,
    environment: str | None = None,
    *,
    path: Path | None = None,
) -> str:
    selected_company, selected_environment = resolve_selection(
        company,
        environment,
        path=path,
    )
    return f"meshflow_{selected_company}_{selected_environment}".lower()


def athena_workgroup_name(
    company: str | None = None,
    environment: str | None = None,
    *,
    path: Path | None = None,
) -> str:
    selected_company, selected_environment = resolve_selection(
        company,
        environment,
        path=path,
    )
    return f"meshflow-{selected_company}-{selected_environment}".lower()


def catalog_table_name(layer: str, source: str, entity: str) -> str:
    return f"{layer.strip().lower()}_{source.strip().lower()}_{entity.strip().lower()}"


SILVER_ONLY_CATALOG_ENTITIES: dict[str, frozenset[str]] = {
    "qbd": frozenset({"invoice_lines"}),
}


def is_silver_only_catalog_entity(source: str, entity: str) -> bool:
    return entity.strip().lower() in SILVER_ONLY_CATALOG_ENTITIES.get(source.strip().lower(), frozenset())


def iter_catalog_entities(
    connectors: list[tuple[str, dict[str, Any]]],
) -> list[tuple[str, str]]:
    """Return (source, entity) pairs configured for Glue/Athena tables."""
    from meshflow.qbd.entities import resolve_qbd_entities_from_ingest_config
    from meshflow.qbo.entities import resolve_qbo_entities_from_ingest_config

    entities: list[tuple[str, str]] = []
    for connector, connector_cfg in connectors:
        if connector == "qbo":
            _bundle, entity_map = resolve_qbo_entities_from_ingest_config(connector_cfg)
            entities.extend((connector, name) for name in entity_map)
        elif connector == "qbd":
            _bundle, specs = resolve_qbd_entities_from_ingest_config(connector_cfg)
            output_names = [spec.output_name for spec in specs]
            entities.extend((connector, name) for name in output_names)
            if "invoices" in output_names:
                entities.append((connector, "invoice_lines"))
    return entities


def iter_raw_catalog_entities(
    connectors: list[tuple[str, dict[str, Any]]],
) -> list[tuple[str, str]]:
    return [
        (source, entity)
        for source, entity in iter_catalog_entities(connectors)
        if not is_silver_only_catalog_entity(source, entity)
    ]


def resolve_athena_results_bucket_name(
    company: str | None = None,
    environment: str | None = None,
    *,
    account: str | None = None,
    region: str | None = None,
    path: Path | None = None,
) -> str:
    selected_company, selected_environment = resolve_selection(
        company,
        environment,
        path=path,
    )
    config = load_project_config(path)
    secrets_cfg = config.get("secrets", {})
    if not isinstance(secrets_cfg, dict):
        secrets_cfg = {}

    env_config = get_environment_config(selected_company, selected_environment, path=path)
    resolved_account, resolved_region = resolve_aws_deploy_env(env_config, selected_environment)
    if account:
        resolved_account = account.strip()
    if region:
        resolved_region = region.strip()

    resolved_account = str(resolved_account or "").strip()
    resolved_region = str(resolved_region or "").strip()
    if not resolved_account or not resolved_region:
        raise ValueError(
            "Could not resolve AWS account/region for Athena results bucket naming."
        )

    template = str(
        secrets_cfg.get(
            "athena_results_bucket_name_template",
            "athena-results-{company}-{account}-{region}",
        )
    ).strip()
    return template.format(
        company=selected_company.strip().lower(),
        environment=selected_environment.strip().lower(),
        account=resolved_account,
        region=resolved_region.lower(),
    )


def resolve_qbo_ingest_entities(
    company: str | None = None,
    environment: str | None = None,
    *,
    path: Path | None = None,
) -> tuple[str, dict[str, str]]:
    """Resolve QBO entity bundle and queries from config.yaml ingest settings."""
    from meshflow.qbo.entities import resolve_qbo_entities_from_ingest_config

    selected_company, selected_environment = resolve_selection(
        company,
        environment,
        path=path,
    )
    env_config = get_environment_config(selected_company, selected_environment, path=path)
    qbo_cfg = get_connector_config(env_config, "qbo")
    if not qbo_cfg:
        ingest_cfg = env_config.get("ingest", {})
        qbo_cfg = ingest_cfg if isinstance(ingest_cfg, dict) else {}

    return resolve_qbo_entities_from_ingest_config(qbo_cfg)


def resolve_qbd_ingest_entities(
    company: str | None = None,
    environment: str | None = None,
    *,
    path: Path | None = None,
) -> tuple[str, list[Any]]:
    """Resolve QBD entity bundle and export specs from config.yaml ingest settings."""
    from meshflow.qbd.entities import resolve_qbd_entities_from_ingest_config

    selected_company, selected_environment = resolve_selection(
        company,
        environment,
        path=path,
    )
    env_config = get_environment_config(selected_company, selected_environment, path=path)
    qbd_cfg = get_connector_config(env_config, "qbd")
    if not qbd_cfg:
        ingest_cfg = env_config.get("ingest", {})
        qbd_cfg = ingest_cfg if isinstance(ingest_cfg, dict) else {}

    return resolve_qbd_entities_from_ingest_config(qbd_cfg)


def resolve_ingest_connector(
    company: str | None = None,
    environment: str | None = None,
    *,
    path: Path | None = None,
) -> str:
    explicit = os.getenv("MESHFLOW_SOURCE", "").strip().lower()
    if explicit:
        return explicit

    selected_company, selected_environment = resolve_selection(
        company,
        environment,
        path=path,
    )
    env_config = get_environment_config(selected_company, selected_environment, path=path)
    connectors = list(iter_configured_connectors(env_config))
    if len(connectors) == 1:
        return connectors[0][0]

    connector = get_config_value(
        "ingest.connector",
        company=company,
        environment=environment,
        path=path,
        default="qbo",
    )
    return str(connector).strip().lower() or "qbo"


def is_protected_environment(environment: str) -> bool:
    return environment in PROTECTED_ENVIRONMENTS


def resolve_cdk_deploy_filter(
    *,
    company: str | None = None,
    environment: str | None = None,
) -> tuple[str | None, str | None]:
    """Resolve CDK deploy filters from explicit deploy-time inputs only.

    Unlike resolve_selection(), this ignores config.yaml defaults so prod stacks
    are never synthesized unless MESHFLOW_ENVIRONMENT=prod or `-c environment=prod`.
    """
    selected_company = (company or os.getenv("MESHFLOW_COMPANY", "")).strip() or None
    selected_environment = (environment or os.getenv("MESHFLOW_ENVIRONMENT", "")).strip() or None
    return selected_company, selected_environment


def _is_placeholder_account(account: str) -> bool:
    normalized = account.strip().upper()
    return not normalized or normalized.startswith(PLACEHOLDER_ACCOUNT_PREFIXES)


def resolve_aws_deploy_env(
    env_config: dict[str, Any],
    environment: str,
) -> tuple[str | None, str | None]:
    aws_cfg = env_config.get("aws", {})
    if not isinstance(aws_cfg, dict):
        aws_cfg = {}

    configured_account = str(aws_cfg.get("account", "")).strip()
    configured_region = str(aws_cfg.get("region", "")).strip()
    deploy_account = os.getenv("CDK_DEFAULT_ACCOUNT", "").strip()
    deploy_region = (
        os.getenv("CDK_DEFAULT_REGION", "").strip()
        or os.getenv("AWS_REGION", "").strip()
        or configured_region
        or None
    )

    if is_protected_environment(environment):
        if _is_placeholder_account(configured_account):
            raise ValueError(
                f"Refusing to deploy {environment!r}: set companies.*.environments.{environment}.aws.account "
                "in config.yaml to the production AWS account ID before deploying."
            )
        if deploy_account and configured_account != deploy_account:
            raise ValueError(
                f"Refusing to deploy {environment!r} to AWS account {deploy_account}. "
                f"Config expects account {configured_account}."
            )
        return configured_account, deploy_region

    if configured_account:
        if _is_placeholder_account(configured_account):
            configured_account = ""
        elif deploy_account and configured_account != deploy_account:
            raise ValueError(
                f"Refusing to deploy {environment!r} to AWS account {deploy_account}. "
                f"Config expects account {configured_account}."
            )

    account = configured_account or deploy_account or None
    return account, deploy_region


def iter_cdk_deploy_targets(
    *,
    company: str | None = None,
    environment: str | None = None,
    path: Path | None = None,
) -> Iterator[tuple[str, str, dict[str, Any]]]:
    config = load_project_config(path)
    deploy_company, deploy_environment = resolve_cdk_deploy_filter(
        company=company,
        environment=environment,
    )

    if deploy_company or deploy_environment:
        selected_company, selected_environment = resolve_selection(
            deploy_company,
            deploy_environment,
            path=path,
        )
        if is_protected_environment(selected_environment) and not deploy_environment:
            raise ValueError(
                f"Refusing to synthesize protected environment {selected_environment!r}. "
                "Set MESHFLOW_ENVIRONMENT=prod or pass `-c environment=prod` to deploy it."
            )
        yield (
            selected_company,
            selected_environment,
            get_environment_config(selected_company, selected_environment, path=path),
        )
        return

    for company_name in _available_companies(config):
        for environment_name in _available_environments(config, company_name):
            if is_protected_environment(environment_name):
                continue
            yield (
                company_name,
                environment_name,
                get_environment_config(company_name, environment_name, path=path),
            )

