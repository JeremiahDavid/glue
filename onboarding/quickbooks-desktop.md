# Onboarding — QuickBooks Desktop (`qbd`)

**Mesh node:** `SYS-QBD` · **Auth:** QuickBooks Web Connector username/password · **Ingest:** QBWC polls SOAP endpoint (push/pull by Intuit design) · **Silver:** Manual or on-demand refresh Step Functions

---

## What the client needs to provide

| Item | Who |
|---|---|
| Windows PC with **QuickBooks Desktop** and **QuickBooks Web Connector** installed | Client |
| Company file open and authorized for Web Connector | Client |
| Stable network path from QBWC machine to Meshflow SOAP URL (HTTPS in AWS) | Client IT |
| QBWC run schedule (Web Connector controls timing, not Meshflow EventBridge) | Client |

## What Meshflow needs

| Item | Notes |
|---|---|
| AWS deploy with `qbd:` in `config.yaml` | Provisions SOAP Lambda + API Gateway |
| Secret with QBWC credentials and `QBWC_SOAP_URL` | Set after deploy from `QbdSoapUrl` output |
| Generated `.qwc` file installed in Web Connector | One per company file / endpoint |

---

## Architecture

```text
QuickBooks Desktop + Web Connector (client Windows PC)
      |
      |  HTTPS SOAP (scheduled by QBWC)
      v
API Gateway  -->  Lambda (poc-dev-qbd-bronze-ingest)
      |
      v
S3  raw/qbd/{run_id}/...  +  qbd/_state/ (sessions, watermarks)

Silver:  Step Functions poc-dev-qbd-pipeline-refresh  (consolidate only; no bronze in SM)
```

Bronze ingest is **not** on the Meshflow EventBridge schedule. QBWC decides when to connect. The refresh state machine only runs **silver consolidate** after bronze data exists.

---

## Step 1 — `config.yaml`

```yaml
companies:
  ACME:
    environments:
      dev:
        aws:
          region: us-east-2
        qbd:
          entity_bundle: full_accounting   # same bundle names as QBO
```

No `schedule` block for QBD — ingest timing is controlled by Web Connector on the client machine.

Entity bundles match QBO naming; queries are qbXML in [`packages/meshflow-connectors/src/meshflow/qbd/entities.py`](../packages/meshflow-connectors/src/meshflow/qbd/entities.py).

---

## Step 2 — Secrets Manager (initial)

```powershell
Copy-Item secrets.example.qbd.yaml secrets/acme-qbd-dev.yaml
# Edit company, source, environment, QBWC username/password, company name

python scripts/create_secrets.py --file secrets/acme-qbd-dev.yaml
```

```yaml
QBD_COMPANY_NAME: "Acme Corp"
QBD_COMPANY_FILE: ""                    # optional; filled by QBWC session
QBD_ENVIRONMENT: dev
QBD_QBWC_USERNAME: "<choose-a-username>"
QBD_QBWC_PASSWORD: "<choose-a-strong-password>"
QBD_QBWC_APP_NAME: Meshflow QBD Connector
QBD_QBXML_VERSION: "13.0"               # match supported QB Desktop version
QBWC_SOAP_URL: ""                       # fill after deploy (Step 4)
```

---

## Step 3 — Deploy AWS infrastructure

Deploy with QBO and/or other connectors in the same stack if needed:

```powershell
cdk deploy -c company=ACME -c environment=dev IngestStack-ACME-dev
```

Note outputs:

- `QbdSoapUrl` — production SOAP endpoint (e.g. `https://….execute-api.us-east-2.amazonaws.com/prod/soap`)
- `QbdBronzeIngestFunctionName`
- `QbdRefreshStateMachineArn` — silver consolidate only

---

## Step 4 — Point secret at SOAP URL

1. Copy `QbdSoapUrl` from stack outputs.
2. Update the secret:

```powershell
# Set QBWC_SOAP_URL in secrets/acme-qbd-dev.yaml, then:
python scripts/create_secrets.py --file secrets/acme-qbd-dev.yaml --update
```

Or set `QBWC_SOAP_URL` directly in AWS Secrets Manager.

---

## Step 5 — Install Web Connector app (`.qwc`)

Generate the connector file:

```powershell
$env:MESHFLOW_COMPANY = "ACME"
$env:MESHFLOW_ENVIRONMENT = "dev"
$env:MESHFLOW_SOURCE = "qbd"

python scripts/qbd_generate_qwc.py `
  --output meshflow-acme.qwc `
  --soap-url "https://<api-id>.execute-api.us-east-2.amazonaws.com/prod/soap"
```

On the **client Windows machine**:

1. Open **QuickBooks Web Connector**.
2. **Add an application** → select `meshflow-acme.qwc`.
3. Enter the **same username/password** as in Secrets Manager.
4. Authorize access to the QuickBooks company file when prompted.
5. Set QBWC **auto-run** interval (e.g. every 60 minutes or daily before business hours).

---

## Step 6 — Verify bronze ingest

1. Run sync once from Web Connector (or wait for scheduled QBWC poll).
2. Check CloudWatch logs for `acme-dev-qbd-bronze-ingest`.
3. Confirm S3:

```text
s3://{bucket}/raw/qbd/{run_id}/
  customers.parquet
  invoices.parquet
  manifest.json
```

**Local dev (no AWS):** run `python scripts/qbd_soap.py` on `:8080` and point QBWC at `http://localhost:8080/soap`.

---

## Step 7 — Silver consolidate

After at least one successful bronze run:

```powershell
aws stepfunctions start-execution `
  --state-machine-arn <QbdRefreshStateMachineArn> `
  --input '{"full_rebuild": false}'
```

Or locally:

```powershell
python scripts/consolidate.py --source qbd
```

There is **no** scheduled silver job for QBD unless you add one later. Typical flow: QBWC sync overnight → run refresh (or automate refresh via EventBridge once bronze cadence is stable).

---

## Ongoing operations

| Task | How |
|---|---|
| Bronze ingest | Client keeps QBWC running on schedule; PC must be on and QB available |
| Silver update | Invoke `QbdRefreshStateMachineArn` after syncs (manual today) |
| New company file | New `.qwc`, update `QBD_COMPANY_NAME`, re-authorize in QBWC |
| Rotate QBWC password | Update secret → `--update`; update password in Web Connector |

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| QBWC “failed to connect” | Wrong `QBWC_SOAP_URL` or API Gateway down | Verify URL; check Lambda/API Gateway |
| Authentication failed | Username/password mismatch | Align secret and Web Connector |
| No new S3 data | QB closed, PC off, or QBWC disabled | Client ops checklist |
| qbXML errors | Version mismatch | Adjust `QBD_QBXML_VERSION` for their QB year |
| Empty silver | Consolidate not run after bronze | Run refresh Step Functions |

---

## Related docs

- [Onboarding index](./README.md)
- [README — QBD section](../README.md)
- [Mesh node catalog — SYS-QBD](../docs/product-scoping/mesh-node-catalog.md)
