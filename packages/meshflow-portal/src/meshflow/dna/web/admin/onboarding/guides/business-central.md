# Onboarding — Dynamics 365 Business Central (`dbc`)

**Mesh node:** `SYS-BC` · **Sample mesh:** `MESH-BC-INTRA` · **Auth:** Azure Entra app (client credentials) · **Ingest:** Scheduled refresh pipeline (bronze fan-out → silver consolidate)

BC is typically the **system of record** for a BC-native deployment — operational documents, inventory, and full accounting live in BC. Meshflow does not require QuickBooks for these customers. Optional adjunct sources (Excel forecasts, CRM exports) can be added later and joined on item/customer/period keys.

---

<!-- credentials-guide-start -->

## What the client needs to provide

| Role / access | Used for |
|---|---|
| **Global Administrator** or **Cloud Application Administrator** | Grant API permissions in Entra ID; BC **Grant Consent** |
| **Dynamics 365 Administrator** or BC admin | BC Admin Center; enable app in **Microsoft Entra applications** |
| BC **environment name** and target **company** | `BC_ENVIRONMENT_NAME` and `BC_COMPANY_ID` below |

## Register an app in Microsoft Entra ID

1. [Entra ID → App registrations](https://entra.microsoft.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade) → **New registration**.
2. Name: e.g. `Meshflow BC Ingest - {Client}`.
3. **Single tenant** (typical).
4. **Redirect URI** — in **Authentication** → **Add a platform** → **Web**, add `https://businesscentral.dynamics.com/OAuthLanding.htm` for BC Online (required before **Grant Consent** in BC). For on-premises, use your web client URL + `/OAuthLanding.htm` (must match the browser address exactly). Leave **Access tokens** and **ID tokens** (implicit grant) **unchecked** — Meshflow uses client credentials, not implicit or OpenID redirect tokens.
5. Copy **Application (client) ID** → **Entra client id** <!-- credential-field:BC_CLIENT_ID -->
6. Copy **Directory (tenant) ID** → **Entra tenant id** <!-- credential-field:BC_TENANT_ID -->
7. **Certificates & secrets** → **New client secret** → copy the **Value** (not Secret ID) → **Entra client secret** <!-- credential-field:BC_CLIENT_SECRET -->

## API permissions (Entra ID)

1. **API permissions** → **Add a permission** → **Dynamics 365 Business Central**.
2. **Application permissions** → **API.ReadWrite.All** (or **API.Read.All** for read-only POC).
3. **Grant admin consent for [tenant]** — green check required.

## Register the app in Business Central

> Admin Center → **Authorized Microsoft Entra Apps** is for the **administration API**, not company data. Registration **inside BC** is required.

1. Open Business Central for the target environment.
2. Search (**Alt+Q**) → **Microsoft Entra applications** → **New**.
3. **Client ID** = same as **Entra client id**, **State** = Enabled.
4. Assign permission sets (**D365 AUTOMATION** for POC; tighten for production).
5. **Grant Consent** on the app card (Global Admin or Cloud Application Admin). If consent fails, confirm the Entra **Web** redirect URI (`OAuthLanding.htm`) is configured first.

## Environment and company

1. In BC Admin Center, note the target **environment name** (exact spelling). <!-- credential-field:BC_ENVIRONMENT_NAME -->
2. On the credential form, click **Load companies** and select the target company.

Meshflow refreshes API tokens automatically — do **not** paste `access_token` values into the form.

<!-- credentials-guide-end -->

## What the client needs to provide

| Role / access | Used for |
|---|---|
| **Global Administrator** or **Cloud Application Administrator** | Grant API permissions in Entra ID; BC **Grant Consent** |
| **Dynamics 365 Administrator** or BC admin | BC Admin Center, enable app in **Microsoft Entra applications** |
| BC **environment name** and target **company** | Secrets and OData URLs |

## What Meshflow needs

| Item | Notes |
|---|---|
| Entra app registration with client secret | Service-to-service; no user login during ingest |
| App registered inside BC (**Microsoft Entra applications**) | Required for data API — Admin Center alone is not enough |
| `dbc:` block in `config.yaml` | Entity bundle + refresh schedule |

---

## Overview

```text
Azure Entra ID app (client credentials)
      |
      v
BC: Microsoft Entra applications  (+ permission sets)
      |
      v
BC OData API  .../api/v2.0/companies({id})/...
      |
      v
Refresh pipeline  -->  raw/dbc/{run_id}/...  -->  silver_stg/dbc/{entity}/data.parquet
                                              -->  silver_stg/dbc/{entity}_lines/data.parquet  (document lines)
```

Meshflow acquires and refreshes `access_token` automatically. Do **not** paste tokens into the secrets file.

---

## Step 1 — Register an app in Microsoft Entra ID

1. [Entra ID → App registrations](https://entra.microsoft.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade) → **New registration**.
2. Name: e.g. `Meshflow BC Ingest - {Client}`.
3. **Single tenant** (typical).
4. Copy **Application (client) ID** → `BC_CLIENT_ID`
5. Copy **Directory (tenant) ID** → `BC_TENANT_ID`
6. **Certificates & secrets** → **New client secret** → copy the **Value** (not Secret ID) → `BC_CLIENT_SECRET`

---

## Step 2 — API permissions (Entra ID)

1. **API permissions** → **Add a permission** → **Dynamics 365 Business Central**.
2. **Application permissions** → **API.ReadWrite.All** (or **API.Read.All** for read-only POC).
3. **Grant admin consent for [tenant]** — green check required.

---

## Step 3 — Register the app in Business Central

> Admin Center → **Authorized Microsoft Entra Apps** is for the **administration API**, not company data. Meshflow needs registration **inside BC**.

1. Open Business Central for the target environment.
2. Search (**Alt+Q**) → **Microsoft Entra applications** → **New**.
3. **Client ID** = same as `BC_CLIENT_ID`, **State** = Enabled.
4. Assign permission sets (**D365 AUTOMATION** for POC; tighten for production).
5. **Grant Consent** on the app card (Global Admin or Cloud Application Admin).

---

## Step 4 — Resolve environment and company IDs

| Secret key | Source |
|---|---|
| `BC_ENVIRONMENT_NAME` | BC Admin Center — exact spelling, e.g. `Production` or `Sandbox` |
| `BC_COMPANY_ID` | Companies API — GUID, not tenant ID |
| `BC_ENVIRONMENT` | Meshflow label: `sandbox` or `production` (metadata) |

List companies (after Steps 1–3):

```powershell
$tenant = "<BC_TENANT_ID>"
$clientId = "<BC_CLIENT_ID>"
$clientSecret = "<BC_CLIENT_SECRET>"
$bcEnv = "Production"

$token = (Invoke-RestMethod -Method Post `
  -Uri "https://login.microsoftonline.com/$tenant/oauth2/v2.0/token" `
  -Body @{
    grant_type    = "client_credentials"
    client_id     = $clientId
    client_secret = $clientSecret
    scope         = "https://api.businesscentral.dynamics.com/.default"
  }).access_token

Invoke-RestMethod `
  -Uri "https://api.businesscentral.dynamics.com/v2.0/$tenant/$bcEnv/api/v2.0/companies" `
  -Headers @{ Authorization = "Bearer $token" } |
  Select-Object -ExpandProperty value |
  Format-Table id, displayName
```

Copy company **`id`** → `BC_COMPANY_ID`.

---

## Step 5 — `config.yaml`

```yaml
companies:
  ACME:
    environments:
      dev:
        aws:
          region: us-east-2
        dbc:
          entity_bundle: full
          schedule:
            hour: 6
            minute: 0
```

### Entity bundles

| Bundle | Scope | Use |
|---|---|---|
| `full` | ~75 standard BC API v2.0 entities | Broad operational lake |
| `v1_intra` | customers, items, sales_orders, sales_shipments, sales_invoices, customer_payments | `MESH-BC-INTRA` |
| `v1_accounting` | customers, sales_invoices, open_sales_invoices, customer_payments | Accounting-focused |

See [`packages/meshflow-connectors/src/meshflow/bc/entities.py`](../packages/meshflow-connectors/src/meshflow/bc/entities.py). Individual entity failures (e.g. 403) do not stop the run — check `manifest.json` → `ingest_summary`.

---

## Step 6 — Secrets Manager

```powershell
Copy-Item secrets.example.dbc.yaml secrets/acme-dbc-dev.yaml
python scripts/create_secrets.py --file secrets/acme-dbc-dev.yaml
```

```yaml
company: ACME
source: dbc
environment: dev

BC_CLIENT_ID: "<app-client-id>"
BC_CLIENT_SECRET: "<secret-value>"
BC_TENANT_ID: "<tenant-id>"
BC_ENVIRONMENT_NAME: Production
BC_COMPANY_ID: "<company-guid>"
BC_ENVIRONMENT: production
access_token: ""
expires_at: ""
```

Incremental watermarks live in S3 at `raw/dbc/_state/watermarks.json`, not in Secrets Manager.

---

## Step 7 — Deploy AWS infrastructure

```powershell
cdk deploy -c company=ACME -c environment=dev IngestStack-ACME-dev
```

Key outputs:

- `DbcRefreshStateMachineArn` — scheduled bronze + silver
- `DbcBronzeIngestFunctionName` — ad-hoc single entity
- `RawBucketName`

---

## Step 8 — Verify ingest

**Scheduled:** `acme-dev-dbc` at `schedule.hour:minute` UTC.

**Manual full refresh:**

```powershell
aws stepfunctions start-execution `
  --state-machine-arn <DbcRefreshStateMachineArn> `
  --input '{"full_load": false, "full_rebuild": false}'
```

**Full reload** (ignore incremental watermarks):

```powershell
aws stepfunctions start-execution `
  --state-machine-arn <DbcRefreshStateMachineArn> `
  --input '{"full_load": true, "full_rebuild": true}'
```

**Local smoke test:**

```powershell
$env:MESHFLOW_COMPANY = "ACME"
$env:MESHFLOW_ENVIRONMENT = "dev"
$env:MESHFLOW_SOURCE = "dbc"
$env:MESHFLOW_SECRET_ID = "meshflow-acme-dbc-dev"

python scripts/bc_ingest.py
python scripts/consolidate.py --source dbc
```

**Check S3:**

```text
s3://{bucket}/raw/dbc/{run_id}/{entity}/data.parquet
s3://{bucket}/silver_stg/dbc/{entity}/data.parquet
```

Incremental watermarks (`lastModifiedDateTime` per entity) persist in S3 at `raw/dbc/_state/watermarks.json` after each run.

---

## Ongoing operations

| Task | How |
|---|---|
| Daily refresh | EventBridge → DBC refresh Step Functions |
| Full reload | `"full_load": true, "full_rebuild": true` on refresh SM |
| Rotate client secret | New secret in Entra → update YAML → `create_secrets.py --update` |
| Permission gaps | Review manifest failed entities; adjust BC permission sets |

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `AADSTS7000215: Invalid client secret` | Secret ID used instead of Value | Copy secret **Value** from Entra |
| **401** on `/companies` | App not in BC Entra applications or no admin consent | Steps 2–3 |
| **404** on API | Wrong `BC_ENVIRONMENT_NAME` | Match Admin Center exactly |
| Empty companies list | Missing permission sets on BC app record | Assign **D365 AUTOMATION** |
| Some entities **403** | Least-privilege set too narrow | Expand sets or use smaller bundle |

---

## Related docs

- [Onboarding index](./README.md)
- [Detailed BC setup guide](../docs/business-central-setup.md)
- [Data model reference](../docs/dbc-data-model.md) — entity relationships and join paths (Microsoft APV2)
- [Mesh node catalog — SYS-BC](../docs/product-scoping/mesh-node-catalog.md)
- [Mesh catalog — MESH-BC-INTRA](../docs/product-scoping/mesh-catalog.md)
