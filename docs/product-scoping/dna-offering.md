# Meshflow DNA — Semantic Engine Offering

**Product ID:** `DNA-BC-01` (BC-native; additional packs TBD)  
**Status:** Product catalog — SOW may select DNA tier or DNA add-on per [meshflow-pricing-sheet.md](../terms/meshflow-pricing-sheet.md)

**Companion:** [dna-kpi-starter-catalog.md](./dna-kpi-starter-catalog.md) · [dna-semantic-engine.md](../internal-execution-scoping/dna-semantic-engine.md) · [dbc-data-model.md](../dbc-data-model.md)

---

## What DNA is

**DNA — Semantic Engine** turns customer documentation and BC lake data into **versioned, governed semantic definitions** — certified gold tables, KPI snapshots, and a HiveFlowAI reporting portal.

A parallel **Reporting Engine** governs portal layout (charts, tables, filters, dimensions) from the same documentation-driven, version-controlled model.

DNA shares the **same ingest pipeline** as Meshflow Signals (bronze → silver). It is **optional** — not every customer needs it.

| Customer profile | Offer |
|---|---|
| HVAC / thin stack / wants ranked to-do list | **Signals only** |
| BC-native, custom KPIs, distrusts ad-hoc reports | **DNA** |
| Signals customer expanding to custom analytics | **DNA add-on** |

---

## How customization works

Customers customize **to the degree they can provide documentation**. There is no per-KPI professional-services menu.

| Want | Submit | Engine | Result |
|---|---|---|---|
| New or changed KPI / join / grain | Business logic docs | **DNA Engine** | Updated DNA file → semantic layer |
| New or changed report / chart / page | Reporting layout docs | **Reporting Engine** | Updated reporting file → portal UI |

Both files (YAML or MD) are **version-controlled** — they are the company's DNA and reporting contract. Changes are promoted deliberately; production never drifts silently.

Provider supports onboarding and complex cases; routine updates are **self-service**.

---

## General data flow

```text
[data lake (S3)] → [semantic layer (S3 gold)] → [web portal (HTML)]
```

**Scheduled:** BC ingest refreshes silver; compile/publish re-materializes the **pinned** semantic pack against new data.

**On-demand:** DNA and Reporting Engines run only when the customer submits documentation updates — not on every refresh.

---

## Customer workflow (DBC / DNA)

### 1. Data lake ingest

Pull the customer's BC environment into the tenant data lake (bronze fan-out → silver consolidate). Same pipeline as Mesh; DNA tier typically uses the `full` or agreed entity bundle.

### 2. DNA requirements (semantic layer)

Work with the customer to define business logic and KPI definitions. Output: a version-controlled **DNA file** (YAML/MD) — joins, grains, calculations, filters, limitations.

Flow:

```text
[raw customer docs] → [AI: consolidate & summarize] → [DNA file]
  → [AI: code generator] → [semantic layer SQL/Python] → [gold tables]
```

Industry starter packs (e.g. `bc_intra_v1`) bootstrap the first DNA file; customer docs extend or replace.

### 3. Reporting requirements (portal)

Same structure for what they want to **see**: chart types, tables, dimensions, filters, page layout. Output: a version-controlled **reporting file** (YAML/MD).

Flow:

```text
[raw customer docs] → [AI: consolidate & summarize] → [reporting file]
  → [AI: code generator] → [portal HTML/Python] → [HiveFlowAI views]
```

Reporting binds to certified gold outputs — it does not change calculations unless the DNA file also changed.

### 4. Ongoing updates

Customers submit documentation when they want changes. DNA and Reporting Engines regenerate code from the updated files after promotion. Provider available for support; not required for every change.

---

## Deliverables

1. **Tenant data lake** — BC (and optional adjunct) data in bronze/silver
2. **DNA file + semantic layer** — versioned definition pack and certified gold tables (`dna_*`)
3. **Reporting file + portal** — HiveFlowAI client views (no Power BI required)
4. **Optional:** weekly PDF/email export; BYO-BI via Athena ODBC (customer-managed PBI/Fabric)

Power BI is **not** the default deliverable.

---

## What's included

| Item | Included |
|---|---|
| BC `full` or agreed entity bundle ingest | Yes (shared with Mesh) |
| Starter KPI library (seed pack) | Yes |
| Custom KPIs / reports via customer documentation | Yes — self-service |
| DNA + Reporting version control and promotion workflow | Yes |
| Logic regression tests on every DNA publish | Yes |
| Provider support for onboarding and edge cases | Yes |
| Managed Power BI development | No |
| Audited financials | No |

---

## Fit gate (discovery)

Proceed with DNA when **≥2** are true:

1. Customer runs BC (or full ERP) as system of record with `full` or near-full entity bundle
2. Controller needs **custom** KPIs or cross-module reports not satisfied by catalog Signals
3. Customer distrusts ad-hoc reports / prior BI failed on join correctness
4. Customer can articulate requirements in documentation (or will work with provider to produce the first DNA/reporting files)

**Do not sell DNA** when customer only wants a ranked exception to-do list (Signals is faster and cheaper).

---

## Pricing phases

See [meshflow-pricing-sheet.md](../terms/meshflow-pricing-sheet.md) for full detail.

| Phase | Implementation | Monthly | Notes |
|---|---|---|---|
| **Beta (current)** | $0 | **$100** | Design partners; starter pack + self-service doc workflow |
| **GA (target)** | **$5,000** | **$1,000** | Full DNA + Reporting engines; feasibility TBD at scale |

Beta clients migrate to GA pricing on renewal or when Phase 2 is announced.

---

## Related offerings

- **Meshflow Signals** — catalog exception queues; see [signal-catalog.md](./signal-catalog.md)
- Signals can later consume **DNA-certified gold tables** as inputs (shared join logic)

---

## Internal commands

```powershell
# Deploy (DNA is a separate CDK stack from ingest)
cd infra
cdk deploy DnaStack-POC-dev

meshflow-dna draft-from-docs --pack-id acme_bc docs/customer-kpis.md
meshflow-dna promote --target validated --approver "Controller Name"
meshflow-dna publish
meshflow-dna serve
```

See [dna-semantic-engine.md](../internal-execution-scoping/dna-semantic-engine.md) for technical detail.
