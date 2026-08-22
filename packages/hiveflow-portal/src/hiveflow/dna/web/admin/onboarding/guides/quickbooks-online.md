# Onboarding — QuickBooks Online (`qbo`)

**Mesh node:** `SYS-QBO` · **Auth:** OAuth 2.0 (Intuit) · **Ingest:** Scheduled refresh pipeline (bronze fan-out → silver consolidate)

---

<!-- credentials-guide-start -->

## What the client needs to provide

| Item | Who |
|---|---|
| Access to connect Meshflow to their QuickBooks Online company (sandbox or production) | Client admin |
| Approval to create an Intuit Developer app (or use Meshflow’s app with client consent) | Client / Meshflow |
| Named billing/admin contact for credential handoff | Client |

## Intuit Developer app

1. Go to [developer.intuit.com](https://developer.intuit.com) and create (or reuse) an app with **QuickBooks Online** scope.
2. Copy **Client ID** → **QBO client id** <!-- credential-field:QBO_CLIENT_ID -->
3. Copy **Client Secret** → **QBO client secret** <!-- credential-field:QBO_CLIENT_SECRET -->
4. Add redirect URI: `http://localhost:8080/callback` → **QBO redirect URI** <!-- credential-field:QBO_REDIRECT_URI -->
5. Enable **Accounting** scope.
6. Set **QBO environment** to `sandbox` or `production` (must match Intuit app tier). <!-- credential-field:QBO_ENVIRONMENT -->

For production clients, use **Production** keys in the Intuit portal. For testing, use Development keys.

After saving these values, run **Validate connector** to check OAuth status.

<!-- credentials-guide-end -->

## What the client needs to provide

| Item | Who |
|---|---|
| Access to connect Meshflow to their QuickBooks Online company (sandbox or production) | Client admin |
| Approval to create an Intuit Developer app (or use Meshflow’s app with client consent) | Client / Meshflow |
| Named billing/admin contact for credential handoff | Client |

## What Meshflow needs

| Item | Notes |
|---|---|
| AWS Secrets Manager (secret created before CDK deploy) | `meshflow-{company}-qbo-{environment}` |
| One-time OAuth from a machine with a browser | Cannot run inside Lambda |
| `qbo:` block in `config.yaml` for the client environment | Drives entity bundle, schedule, tier |

---

## Step 1 — Intuit Developer app

1. Go to [developer.intuit.com](https://developer.intuit.com) and create (or reuse) an app with **QuickBooks Online** scope.
2. Copy **Client ID** and **Client Secret** (Development for sandbox, Production for live).
3. Add redirect URI: `http://localhost:8080/callback`
4. Enable **Accounting** scope.

For production clients, use Production keys and set `QBO_ENVIRONMENT: production` in the secret.

---

## Step 2 — `config.yaml`

Add the client company/environment and a `qbo` block:

```yaml
companies:
  ACME:
    environments:
      dev:
        aws:
          region: us-east-2
        qbo:
          tier: sandbox          # metadata; aligns with QBO_ENVIRONMENT in secret
          entity_bundle: full_accounting
          schedule:
            hour: 6              # UTC — EventBridge cron on refresh pipeline
            minute: 0
```

### Entity bundles

| Bundle | Entities | Typical use |
|---|---|---|
| `v1_accounting` | customers, invoices, open_invoices, payments | Default POC / AR playbook |
| `full_accounting` | v1 plus vendors, items, accounts, bills, and related entities | Broader accounting mirror |

Defined in [`packages/meshflow-connectors/src/meshflow/qbo/entities.py`](../packages/meshflow-connectors/src/meshflow/qbo/entities.py).

---

## Step 3 — Secrets Manager

```powershell
Copy-Item secrets.example.yaml secrets/acme-qbo-dev.yaml
# Edit: company, source, environment, QBO_CLIENT_ID, QBO_CLIENT_SECRET

python scripts/create_secrets.py --file secrets/acme-qbo-dev.yaml
```

Required secret keys:

```yaml
QBO_CLIENT_ID: "<intuit-client-id>"
QBO_CLIENT_SECRET: "<intuit-client-secret>"
QBO_ENVIRONMENT: sandbox          # or production
QBO_REDIRECT_URI: http://localhost:8080/callback
access_token: ""
refresh_token: ""
realm_id: ""
```

Leave token fields empty until OAuth (Step 5).

---

## Step 4 — Deploy AWS infrastructure

From repo root with `.venv` activated:

```powershell
cdk bootstrap
cdk deploy -c company=ACME -c environment=dev IngestStack-ACME-dev
```

Note stack outputs:

- `QboSecretName`
- `QboRefreshStateMachineArn` — full bronze + silver refresh
- `RawBucketName` / `DataBucketName`
- `QboBronzeIngestFunctionName` — ad-hoc single-entity runs

---

## Step 5 — OAuth (one-time per company file)

OAuth requires a browser; run locally against the client’s secret:

```powershell
$env:MESHFLOW_COMPANY = "ACME"
$env:MESHFLOW_ENVIRONMENT = "dev"
python scripts/qbo_auth.py
```

Sign in and select the client’s QBO company. Tokens and `realm_id` are written to Secrets Manager. Lambda ingest refreshes access tokens automatically on 401.

---

## Step 6 — Verify ingest

**Scheduled:** Refresh pipeline runs daily at `schedule.hour:schedule.minute` UTC (`acme-dev-qbo`).

**Manual full refresh:**

```powershell
aws stepfunctions start-execution `
  --state-machine-arn <QboRefreshStateMachineArn> `
  --input '{"full_load": false, "full_rebuild": false}' `
  --region us-east-2
```

**Check S3:**

```text
s3://{bucket}/raw/qbo/{run_id}/
  customers.parquet
  invoices.parquet
  manifest.json

s3://{bucket}/silver_stg/qbo/{entity}/data.parquet
```

**Local smoke test (optional):**

```powershell
python scripts/qbo_ingest.py
python scripts/consolidate.py --source qbo
```

---

## Ongoing operations

| Task | How |
|---|---|
| Daily refresh | EventBridge → `{company}-{env}-qbo` Step Functions |
| Full reload | Start refresh with `"full_load": true, "full_rebuild": true` |
| Re-auth | Re-run `python scripts/qbo_auth.py` if refresh token revoked |
| Update app creds | Edit secrets YAML → `create_secrets.py --update` |

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Lambda auth errors | Missing or expired OAuth | Re-run `qbo_auth.py` |
| Empty ingest / wrong company | Wrong `realm_id` in secret | Re-auth; pick correct QBO company |
| No scheduled runs | Stack not deployed or wrong region | Confirm EventBridge rule on refresh SM |
| Sandbox vs prod mismatch | `QBO_ENVIRONMENT` ≠ Intuit app keys | Align secret and Intuit app tier |

---

## Related docs

- [Onboarding index](./README.md)
- [README — QBO deployment](../README.md)
- [Mesh node catalog — SYS-QBO](../docs/product-scoping/mesh-node-catalog.md)
