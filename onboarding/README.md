# Meshflow connector onboarding

Step-by-step guides for standing up each ingest connector for a **new client** (new company/environment in `config.yaml`).

## Shared prerequisites (all connectors)

Before any connector-specific work:

| Requirement | Notes |
|---|---|
| **AWS account** | Client or Meshflow-managed tenant account; CLI configured |
| **`config.yaml` entry** | New `companies.{COMPANY}.environments.{ENV}` block with `aws.region` |
| **Secrets file** | `secrets/{company}-{source}-{environment}.yaml` — never commit real credentials |
| **CDK bootstrap** | One-time per account/region: `cdk bootstrap` from `infra/` |
| **Ingest stack deploy** | `cdk deploy IngestStack-{COMPANY}-{ENV}` provisions shared bucket, Glue/Athena, and all configured connectors |

Secret names follow `meshflow-{company}-{source}-{environment}` (from `secrets.secret_name_template` in `config.yaml`).

Resource names follow `{company}-{environment}-{connector}-{stage}-{slug}` — see [`process_config.yaml`](../process_config.yaml).

## Connector guides

| Connector | Source key | Guide |
|---|---|---|
| QuickBooks Online | `qbo` | [quickbooks-online.md](./quickbooks-online.md) |
| QuickBooks Desktop (Web Connector) | `qbd` | [quickbooks-desktop.md](./quickbooks-desktop.md) |
| Dynamics 365 Business Central | `dbc` | [business-central.md](./business-central.md) |

## After ingest is running

1. Confirm bronze data in S3: `s3://{bucket}/raw/{connector}/.../manifest.json`
2. Confirm silver consolidate ran (scheduled refresh or manual Step Functions execution)
3. Optional: run `meshflow-sync-athena-catalog --source {connector}` or query Glue/Athena
4. Document refresh cadence and named client contacts in the SOW / handoff checklist

## Related docs

- [README — AWS deployment](../README.md)
- [Data lake architecture](../docs/internal-execution-scoping/data-lake-architecture.md)
- [Pre-launch checklist](../docs/business-admin/pre-launch-checklist.md)
