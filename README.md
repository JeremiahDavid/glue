# meshflow

POC for the Meshflow reconciliation layer. First connector: **QuickBooks Online**.

Deploys to AWS via CDK: raw data lands in S3, ingest runs on a scheduled Lambda.

## Setup (one virtual environment)

From the repo root:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

This installs the Meshflow app, AWS CDK libraries, and local CLI tools into a single `.venv`.

## Configuration

Deployment settings live in **`config.yaml`** at the repo root. The file supports **multiple companies**, each with **multiple environments**:

```yaml
default:
  company: POC
  environment: dev

secrets:
  secret_name_template: meshflow-{company}-{source}-{environment}
  raw_bucket_name_template: raw-{company}-{environment}-{account}-{region}

companies:
  POC:
    environments:
      dev:
        aws:
          region: us-east-2
        qbo:
          tier: sandbox
          entity_bundle: full_accounting
          schedule:
            hour: 6
            minute: 0
        qbd:
          entity_bundle: v1_accounting
      prod:
        aws:
          region: us-east-2
          account: REPLACE_WITH_PROD_ACCOUNT_ID
        qbo:
          tier: production
          entity_bundle: full_accounting
          schedule:
            hour: 6
            minute: 0
```

- **`default`** — used by local scripts when `MESHFLOW_COMPANY` / `MESHFLOW_ENVIRONMENT` are not set
- **`secrets.secret_name_template`** — derives the Secrets Manager name (POC/qbo/dev → `meshflow-poc-qbo-dev`)
- **`secrets.raw_bucket_name_template`** — derives the shared S3 bucket per environment (POC/dev → `raw-poc-dev-749794722426-us-east-2`)
- **`qbo` / `qbd` blocks** — per-connector settings under the same company/environment; connector name is the secret `source` and S3 prefix (`qbo/{timestamp}/...`, `qbd/{timestamp}/...`)
- **`entity_bundle`** — named entity set per connector (`v1_accounting` default for QBD, `full_accounting` for QBO in POC/dev); see [Entity bundles](#entity-bundles)
- **No secret names or credentials stored locally** — app creds and OAuth tokens live in AWS Secrets Manager only
- **`prod` environments** — require explicit `MESHFLOW_ENVIRONMENT=prod` at CDK deploy time and a real `aws.account`
- **Secrets are created locally** before deploy via `python scripts/create_secrets.py --file ...`; CDK only references existing secrets

Copy `config.example.yaml` when onboarding a new company or environment. Keep OAuth secrets in AWS Secrets Manager, not in this file.

**Precedence:** env vars and CDK `-c company=... -c environment=...` override `default`.

## Architecture

```text
Intuit QBO API
      |
      v
 Lambda (poc-dev-qbo-bronze-ingest)  -->  raw-poc-dev-749794722426-us-east-2
      |                              qbo/{timestamp}/
      +-- Secrets Manager            customers.parquet, invoices.parquet, ...
          meshflow-poc-qbo-dev       manifest.json (run metadata)
```

**Raw layer format:** Parquet for entity extracts; JSON for per-run manifests only. See [data lake architecture](docs/internal-execution-scoping/data-lake-architecture.md).

## AWS deployment (CDK)

### Prerequisites

- AWS CLI configured (`aws sts get-caller-identity`)
- Node.js 18+ and AWS CDK CLI: `npm install -g aws-cdk`
- Docker Desktop (required for Lambda bundling during `cdk deploy`)
- Python 3.11+

### 1. Create secrets

Copy the example file, fill in your Intuit app credentials, and create the secret in AWS:

```powershell
Copy-Item secrets.example.yaml secrets/poc-qbo-dev.yaml
# Edit secrets/poc-qbo-dev.yaml with QBO_CLIENT_ID and QBO_CLIENT_SECRET
python scripts/create_secrets.py --file secrets/poc-qbo-dev.yaml
```

The YAML file must include `company`, `source`, and `environment`. `config.yaml` is used to derive the Secrets Manager name and region (`meshflow-poc-qbo-dev` in `us-east-2` for POC/qbo/dev).

To overwrite an existing secret with values from the file:

```powershell
python scripts/create_secrets.py --file secrets/poc-qbo-dev.yaml --update
```

See `secrets.example.yaml` for single-secret and batch (`secrets:` list) formats. CDK deploy expects the secret to already exist.

### 2. Bootstrap and deploy

With `.venv` activated (see Setup above):

```powershell
cdk bootstrap
cdk deploy IngestStack-POC-dev
```

Deploy every non-prod target (prod is excluded by default):

```powershell
cdk deploy --all
```

Deploy only one dev target:

```powershell
cdk deploy -c company=POC -c environment=dev
```

### Production deploy guardrails

`prod` stacks are **not synthesized by default**. To include prod, you must explicitly set deploy-time environment:

```powershell
$env:MESHFLOW_ENVIRONMENT = "prod"
cdk deploy IngestStack-POC-prod
```

Before the first prod deploy:

1. Set `companies.<company>.environments.prod.aws.account` in `config.yaml` to your production AWS account ID.
2. Bootstrap and deploy using credentials for that prod account.

Prod deploys are blocked when:

- `MESHFLOW_ENVIRONMENT=prod` is not set (prod stacks are omitted from synth/deploy).
- The active AWS account does not match the configured `aws.account` for that prod environment.
- `aws.account` is still a placeholder such as `REPLACE_WITH_PROD_ACCOUNT_ID`.

This prevents accidentally deploying prod resources into your dev account.

Note the stack outputs: **RawBucketName**, **QboSecretName**, **QboRefreshStateMachineArn**, **QboBronzeFanoutStateMachineArn**, **AllSilverConsolidateFunctionName**.

Lambda and Step Functions names follow `{company}-{environment}-{connector}-{stage}-{slug}` and are defined in [`process_config.yaml`](process_config.yaml) (loaded by `meshflow.process_config`).

### 3. Configure the QBO secret

If you used placeholder values in step 1, open the secret in AWS Secrets Manager (for POC/qbo/dev: `meshflow-poc-qbo-dev`) and replace them, or rerun create with your filled-in YAML:

```powershell
python scripts/create_secrets.py --file secrets/poc-qbo-dev.yaml --update
```

Required keys:

```json
{
  "QBO_CLIENT_ID": "your-intuit-client-id",
  "QBO_CLIENT_SECRET": "your-intuit-client-secret",
  "QBO_ENVIRONMENT": "sandbox",
  "QBO_REDIRECT_URI": "http://localhost:8080/callback"
}
```

Leave `access_token`, `refresh_token`, and `realm_id` empty until after OAuth.

### 4. Connect QuickBooks locally (one-time OAuth)

OAuth requires a browser callback and cannot run inside Lambda. With `config.yaml` default set to POC/dev:

```powershell
python scripts/qbo_auth.py
```

To target a different company/environment from config:

```powershell
$env:MESHFLOW_COMPANY = "POC"
$env:MESHFLOW_ENVIRONMENT = "dev"
python scripts/qbo_auth.py
```

This writes OAuth tokens back into the derived Secrets Manager secret.

### 5. Run ingest

**On schedule:** Each connector's refresh pipeline runs daily at the time configured in `config.yaml` (`schedule.hour` / `schedule.minute`, default 06:00 UTC). Example state machine: `poc-dev-qbo-pipeline-refresh` (bronze fan-out ingest, then silver consolidate).

**Manual full refresh (bronze + silver):**

```powershell
aws stepfunctions start-execution `
  --state-machine-arn <QboRefreshStateMachineArn> `
  --input '{"full_load": false, "full_rebuild": false}' `
  --region us-east-2
```

Use `"full_load": true` and `"full_rebuild": true` to ignore incremental watermarks and rebuild silver from all bronze runs.

**Bronze fan-out only** (skip silver consolidate):

```powershell
aws stepfunctions start-execution `
  --state-machine-arn <QboBronzeFanoutStateMachineArn> `
  --input '{"full_load": false}' `
  --region us-east-2
```

**Silver consolidate only:**

```powershell
aws lambda invoke `
  --function-name poc-dev-all-silver-consolidate `
  --payload '{"source":"qbo"}' `
  response.json
```

**Single entity:**

```powershell
aws lambda invoke `
  --function-name poc-dev-qbo-bronze-ingest `
  --payload '{"entity":"customers"}' `
  response.json
Get-Content response.json
```

Raw Parquet lands in S3:

```text
s3://{RawBucketName}/qbo/{timestamp}/
  customers.parquet
  invoices.parquet
  open_invoices.parquet
  payments.parquet
  manifest.json
```

Entity files are **Parquet** (Snappy). Nested QBO fields (`Line`, `MetaData`, `CustomerRef`, …) are JSON-encoded strings in Parquet columns so schemas stay stable. Run metadata stays in **`manifest.json`**.

## Local development (without AWS)

### 1. Create an Intuit developer app

1. Go to https://developer.intuit.com and sign in.
2. Create an app and select QuickBooks Online and Payments.
3. Open Keys and credentials and copy the Client ID and Client Secret for Development (sandbox).
4. Under Redirect URIs, add exactly: `http://localhost:8080/callback`
5. Under Scopes, enable Accounting.

### 2. Configure local environment

With `.venv` activated (see Setup above):

```powershell
Copy-Item .env.example .env
# Edit .env and paste QBO_CLIENT_ID and QBO_CLIENT_SECRET
```

### 3. Connect QuickBooks (OAuth)

```powershell
python scripts/qbo_auth.py
```

This opens your browser, asks you to pick a sandbox company, and saves tokens to `.meshflow/qbo_tokens.json`.

### 4. Run a basic ingest

```powershell
python scripts/qbo_ingest.py
```

Raw Parquet lands under:

```text
data/raw/qbo/{timestamp}/
  customers.parquet
  invoices.parquet
  open_invoices.parquet
  payments.parquet
  manifest.json
```

Same format as S3: Parquet entity files plus a JSON manifest. Nested QBO objects are stored as JSON strings inside Parquet columns.

## QuickBooks Desktop (Web Connector)

QBD uses the **same entity bundles and Parquet/manifest contract** as QBO, but pulls data through **QuickBooks Web Connector (QBWC)** over SOAP instead of the QBO API.

```text
QuickBooks Desktop + Web Connector
      |
      v
  SOAP endpoint (local :8080 or API Gateway QbdSoapUrl)
      |
      v
  qbXML queries per entity bundle
      |
      v
  qbd/{timestamp}/          (Parquet + manifest.json)
  qbd/_state/               (sessions + sync watermarks)
```

**Local SOAP server:**

```powershell
$env:MESHFLOW_COMPANY = "POC"
$env:MESHFLOW_ENVIRONMENT = "dev"
$env:MESHFLOW_SOURCE = "qbd"
python scripts/qbd_soap.py
```

**Generate a `.qwc` file for Web Connector:**

```powershell
python scripts/qbd_generate_qwc.py --output meshflow.qwc --soap-url http://localhost:8080/soap
```

Install the `.qwc` in QuickBooks Web Connector and authorize the company file. QBWC polls the SOAP endpoint on its schedule; each successful sync lands Parquet under `qbd/{timestamp}/`.

**Configure QBD** alongside QBO under the same environment in `config.yaml`:

```yaml
dev:
  aws:
    region: us-east-2
  qbo:
    tier: sandbox
    entity_bundle: full_accounting
    schedule:
      hour: 6
      minute: 0
  qbd:
    entity_bundle: v1_accounting
```

Secret name: `meshflow-poc-qbd-dev`. See `secrets.example.qbd.yaml` for QBWC username/password and `.qwc` IDs.

**AWS deploy:** when a `qbd:` block is present, CDK provisions a SOAP Lambda + API Gateway in the same stack as QBO (shared raw bucket). Stack output `QbdSoapUrl` is the production SOAP endpoint — set it as `QBWC_SOAP_URL` in the secret, then regenerate the `.qwc`. Stack output `QbdRefreshStateMachineArn` runs silver consolidate only (ingest is QBWC-driven):

```powershell
aws stepfunctions start-execution `
  --state-machine-arn <QbdRefreshStateMachineArn> `
  --input '{"full_rebuild": false}'
```

## Dynamics 365 Business Central

BC ingest uses **Azure app registration** (client credentials) and the BC **OData API**. Scheduled Step Functions fan-out pulls entities to `raw/dbc/{run_id}/` (same Parquet + manifest contract as QBO).

```text
Entra ID app  -->  BC: Microsoft Entra applications  -->  OData API
                                                          |
                                                          v
                                              raw/dbc/{run_id}/...
```

**Full setup guide:** [docs/business-central-setup.md](docs/business-central-setup.md) (Entra permissions, BC app registration, company ID lookup, secrets, troubleshooting).

**Quick start:**

```yaml
# config.yaml
dbc:
  entity_bundle: v1_intra
  schedule:
    hour: 6
    minute: 0
```

```powershell
# secrets from secrets.example.dbc.yaml
python scripts/create_secrets.py --file secrets/poc-dbc-dev.yaml

$env:MESHFLOW_SOURCE = "dbc"
$env:MESHFLOW_SECRET_ID = "meshflow-poc-dbc-dev"
python scripts/bc_ingest.py
```

Entity bundles: `v1_intra` (SO/ship/invoice for MESH-BC-INTRA) and `v1_accounting` — see [`src/meshflow/bc/entities.py`](src/meshflow/bc/entities.py).

Ingest a single QBO entity:

```powershell
python scripts/qbo_ingest.py --entity customers
```

## Entity bundles

Ingest pulls **one Parquet file per entity** defined in the configured bundle.

| Bundle | Entities | Use |
|---|---|---|
| **`v1_accounting`** (default) | `customers`, `invoices`, `open_invoices`, `payments` | POC / v1 reconciliation playbook |
| **`full_accounting`** | Above plus `vendors`, `items`, `accounts`, `classes`, `departments`, `bills`, `credit_memos`, `deposits`, `sales_receipts`, `estimates` | Broader accounting mirror |

QBO maps bundles to SQL queries in [`src/meshflow/qbo/entities.py`](src/meshflow/qbo/entities.py). QBD uses the same bundle names with qbXML entity queries in [`src/meshflow/qbd/entities.py`](src/meshflow/qbd/entities.py).

Configure per connector in `config.yaml`:

```yaml
qbo:
  entity_bundle: full_accounting
  schedule:
    hour: 6
    minute: 0

qbd:
  entity_bundle: v1_accounting
```

Override with explicit entity definitions (ignores bundle name):

```yaml
qbo:
  entities:
    customers: "SELECT * FROM Customer"
    invoices: "SELECT * FROM Invoice"
```

The manifest records which bundle ran (`entity_bundle` field). Redeploy Lambda after changing `config.yaml` so the bundled config is updated.

## What gets ingested (v1 accounting playbook)

| Entity | QBO query | Purpose |
|--------|-----------|---------|
| `customers` | All customers | Customer identity / matching spine |
| `invoices` | All invoices | Invoice lines, memos, job number hints |
| `open_invoices` | Balance > 0 | AR / past-due exception inputs |
| `payments` | All payments | Cash application context |

## Project layout

```text
meshflow/
  config.yaml            # deployment + local defaults (no secrets)
  infra/                 # AWS CDK app
    app.py
    stacks/ingest_stack.py
  src/meshflow/          # Python package (connectors, ingest, Lambda handler)
    qbo/                 # QuickBooks Online API connector
    qbd/                 # QuickBooks Desktop scheduled-export connector
    ingest/              # Shared Parquet + manifest writers
  scripts/               # Local CLI helpers
  docs/                  # Product and scoping docs
```

## Notes

- Defaults to sandbox. Set `QBO_ENVIRONMENT=production` only when connecting a real company.
- Tokens and raw data are gitignored (`.meshflow/`, `data/`, `cdk.out/`).
- Refresh tokens are handled automatically on 401 during ingest; updated tokens are written back to Secrets Manager in AWS.
- Initial OAuth must be done locally; Lambda only runs ingest with existing tokens.

## Project docs

Product and scoping docs live in [docs/](docs/).

Internal engineering references:

- [Data lake architecture](docs/internal-execution-scoping/data-lake-architecture.md) — multi-connector S3 layout, Glue/Athena, bronze vs curated
- [Reconciliation engine](docs/internal-execution-scoping/reconciliation-engine.md) — parse → publish pipeline
