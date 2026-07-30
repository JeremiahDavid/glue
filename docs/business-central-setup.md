# Dynamics 365 Business Central — Meshflow setup

This guide walks through connecting Meshflow to **Business Central (BC)** using **service-to-service** auth (Azure app registration + client credentials). Meshflow pulls OData entities on a schedule and lands Parquet under `raw/bc/{run_id}/`.

**Mesh node:** `SYS-BC` · **Sample mesh:** `MESH-BC-INTRA`

---

## Overview

```text
Azure Entra ID app (client credentials)
      |
      v
BC Web Client: Microsoft Entra applications  (+ permission sets)
      |
      v
BC OData API  .../api/v2.0/companies({id})/...
      |
      v
Meshflow ingest  -->  s3://.../raw/bc/{run_id}/{entity}/data.parquet
      |
      v
Consolidate Lambda  -->  silver/bc/{entity}/data.parquet
```

Meshflow acquires and refreshes **`access_token`** automatically. You do **not** paste a token into the secrets file.

---

## Prerequisites

You need:

| Role / access | Used for |
|---------------|----------|
| **Global Administrator** or **Cloud Application Administrator** | Grant API permissions in Entra ID; **Grant Consent** in BC |
| **Dynamics 365 Administrator** (or BC admin) | BC Admin Center, enable app in **Microsoft Entra applications** |
| AWS access | Secrets Manager, optional CDK deploy |

> **Note:** Dynamics 365 Administrator alone is **not** enough to grant tenant-wide API consent in Entra ID.

---

## Step 1 — Register an app in Microsoft Entra ID

1. Open [Entra ID → App registrations](https://entra.microsoft.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade) → **New registration**.
2. Name: e.g. `Meshflow BC Ingest`.
3. Supported account types: **Single tenant** (typical for one organization).
4. Register and copy:
   - **Application (client) ID** → `BC_CLIENT_ID`
   - **Directory (tenant) ID** → `BC_TENANT_ID`

### Create a client secret

1. **Certificates & secrets** → **New client secret**.
2. Copy the **Value** immediately (shown once) → `BC_CLIENT_SECRET`.

> Use the secret **Value**, not the **Secret ID** (GUID). Using the Secret ID causes `AADSTS7000215: Invalid client secret`.

---

## Step 2 — API permissions (Entra ID)

1. App registration → **API permissions** → **Add a permission**.
2. **APIs my organization uses** → **Dynamics 365 Business Central**.
3. **Application permissions** (not Delegated) → **API.ReadWrite.All** (or **API.Read.All** for read-only).
4. **Grant admin consent for [your tenant]** — status must show a green check.

Without this step you may get a token from Azure but BC returns **401 Unauthorized**.

---

## Step 3 — Register the app in Business Central (required for data API)

This is the step that fixes most **401** errors on `/companies`.

> **Do not confuse** with **BC Admin Center → Authorized Microsoft Entra Apps**. That page is for the **Administration Center API** (environment management). Meshflow reads **company data** via the standard OData API and needs registration **inside BC**.

1. Open **Business Central** for the target environment (e.g. Production).
2. Search (**Alt+Q**) for **Microsoft Entra applications**.
3. **New**:
   - **Client ID** — same as `BC_CLIENT_ID`
   - **Description** — e.g. `Meshflow`
   - **State** — **Enabled**
4. Assign permission sets (start with **D365 AUTOMATION** for POC; tighten for production).
5. Run **Grant Consent** on the app card and sign in as **Global Administrator** or **Cloud Application Administrator** if prompted.

Until this record exists and consent is granted, calls like:

`GET .../api/v2.0/companies`

will return **401**, even if the app appears in BC Admin Center.

---

## Step 4 — BC Admin Center (optional for Meshflow ingest)

**BC Admin Center** → **Authorized Microsoft Entra Apps** authorizes apps for the **administration center API**, not for reading sales orders/invoices.

- Listing your app there is fine but **not sufficient** for Meshflow ingest.
- The **Grant** link on that page may remain visible even after consent; that is a known UI quirk and does not block data API access once Step 3 is complete.

Use Admin Center to confirm your **environment name** (e.g. `Production`, `Sandbox`) → `BC_ENVIRONMENT_NAME`.

---

## Step 5 — Resolve IDs for the secrets file

| Secret key | What it is | Where to get it |
|------------|------------|-----------------|
| `BC_TENANT_ID` | Azure AD tenant | Entra app **Overview** → Directory (tenant) ID |
| `BC_CLIENT_ID` | App registration | Entra app **Overview** → Application (client) ID |
| `BC_CLIENT_SECRET` | App secret **Value** | Entra → Certificates & secrets (not Secret ID) |
| `BC_ENVIRONMENT_NAME` | BC environment slug | [BC Admin Center](https://businesscentral.dynamics.com/admin) — exact spelling/casing, e.g. `Production` |
| `BC_COMPANY_ID` | Company GUID in BC | Companies API (below) — **not** the same as tenant ID |
| `BC_ENVIRONMENT` | Meshflow label | `sandbox` or `production` (metadata only) |

### List companies (get `BC_COMPANY_ID`)

After Steps 1–3, run in PowerShell:

```powershell
$tenant = "<BC_TENANT_ID>"
$clientId = "<BC_CLIENT_ID>"
$clientSecret = "<BC_CLIENT_SECRET>"
$bcEnv = "Production"   # must match Admin Center exactly

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

Copy the **`id`** for your company → `BC_COMPANY_ID`.

Leave token fields empty in YAML; Meshflow fills them on first ingest:

```yaml
access_token: ""
expires_at: ""
watermarks: {}
```

---

## Step 6 — Secrets Manager

Copy `secrets.example.bc.yaml` → `secrets/<company>-bc-<environment>.yaml` and fill in values.

```powershell
python scripts/create_secrets.py --file secrets/poc-bc-dev.yaml
# update later:
python scripts/create_secrets.py --file secrets/poc-bc-dev.yaml --update
```

Secret name follows `config.yaml`: `meshflow-{company}-{source}-{environment}` (e.g. `meshflow-poc-bc-dev`).

---

## Step 7 — config.yaml

Add a `bc:` block under your company/environment:

```yaml
companies:
  POC:
    environments:
      dev:
        dbc:
          entity_bundle: full
          schedule:
            hour: 6
            minute: 0
```

### Entity bundles

| Bundle | Entities | Use |
|--------|----------|-----|
| **`full`** (default) | ~75 standard BC API v2.0 company entities — master data, sales/purchase docs (with lines), GL, inventory ledger, financial reports, workflows | Full operational lake for analytics / future MCP KPI queries |
| **`v1_intra`** | `customers`, `items`, `sales_orders`, `sales_shipments`, `sales_invoices`, `customer_payments` | `MESH-BC-INTRA` hero signals |
| **`v1_accounting`** | `customers`, `sales_invoices`, `open_sales_invoices`, `customer_payments` | Smaller accounting-focused pull |

Defined in [`src/meshflow/bc/entities.py`](../src/meshflow/bc/entities.py).

Ingest continues when individual entities fail (for example **403** on entities your BC permission set does not cover). Check `manifest.json` → `ingest_summary` and per-entity `status: failed` entries.

---

## Step 8 — Deploy (AWS)

```powershell
cd infra
cdk deploy IngestStack-POC-dev
```

With a `bc:` block, CDK provisions **BcIngestFunction** (scheduled Lambda), Glue/Athena tables `raw_bc_*` / `silver_bc_*`, and reuses the shared data bucket.

---

## Step 9 — Run ingest

**Local / manual:**

```powershell
$env:MESHFLOW_COMPANY = "POC"
$env:MESHFLOW_ENVIRONMENT = "dev"
$env:MESHFLOW_SOURCE = "bc"
$env:MESHFLOW_SECRET_ID = "meshflow-poc-bc-dev"

python scripts/bc_ingest.py
```

**Full reload** (ignore incremental watermarks):

```powershell
python scripts/bc_ingest.py --full-load
```

**Single entity:**

```powershell
python scripts/bc_ingest.py --entity customers
```

**Consolidate to silver:**

```powershell
python scripts/consolidate.py --source bc
```

Incremental watermarks (`lastModifiedDateTime` per entity) are stored in the secret under `watermarks` after each successful run.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `AADSTS7000215: Invalid client secret` | Secret ID used instead of secret Value | Create new secret; copy **Value** |
| **401** on `/companies` | App not in **BC → Microsoft Entra applications**, or missing Entra admin consent | Complete Steps 2 and 3 |
| **401** after Admin Center only | Wrong authorization path | Admin Center ≠ data API; do Step 3 |
| Admin Center **Grant** still shows link | UI quirk for admin API | Ignore if Step 3 works and API returns companies |
| **404** on API URL | Wrong `BC_ENVIRONMENT_NAME` | Match Admin Center exactly (`Production` vs `Sandbox`) |
| Empty companies list | App lacks permission sets in BC | Assign **D365 AUTOMATION** (POC) on Entra app record |
| Consent appears to do nothing | Signed-in user lacks Entra admin role | Use Global Admin or Cloud Application Administrator |

---

## Security notes

- Rotate client secrets if exposed in logs or chat.
- Do not commit `secrets/*.yaml` with real credentials.
- Prefer least-privilege permission sets in BC (not SUPER) for production.

---

## Related docs

- [Data lake architecture](./internal-execution-scoping/data-lake-architecture.md) — BC ingest pattern
- [Mesh node catalog](./product-scoping/mesh-node-catalog.md) — `SYS-BC`
- [Mesh catalog](./product-scoping/mesh-catalog.md) — `MESH-BC-INTRA`
