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
        ingest_cfg = env_config.get("ingest", {})
        if isinstance(ingest_cfg, dict):
            resolved_source = str(ingest_cfg.get("connector", "")).strip()
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


def resolve_raw_bucket_name(
    company: str | None = None,
    environment: str | None = None,
    *,
    account: str | None = None,
    region: str | None = None,
    path: Path | None = None,
) -> str:
    """Derive the raw ingest S3 bucket name from config.yaml."""
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
            "raw_bucket_name_template",
            "raw-{company}-{environment}-{account}-{region}",
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


def resolve_ingest_s3_prefix(
    company: str | None = None,
    environment: str | None = None,
    *,
    path: Path | None = None,
) -> str:
    """Derive the connector prefix inside the raw bucket (e.g. qbo/)."""
    selected_company, selected_environment = resolve_selection(
        company,
        environment,
        path=path,
    )
    env_config = get_environment_config(selected_company, selected_environment, path=path)
    ingest_cfg = env_config.get("ingest", {})
    if not isinstance(ingest_cfg, dict):
        ingest_cfg = {}

    explicit_prefix = str(ingest_cfg.get("s3_prefix", "")).strip().strip("/")
    if explicit_prefix:
        return explicit_prefix

    connector = str(ingest_cfg.get("connector", "qbo")).strip().lower()
    if not connector:
        raise ValueError(
            f"Set ingest.connector for {selected_company}/{selected_environment} in config.yaml"
        )
    return connector


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
    ingest_cfg = env_config.get("ingest", {})
    if not isinstance(ingest_cfg, dict):
        ingest_cfg = {}

    return resolve_qbo_entities_from_ingest_config(ingest_cfg)


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

