# Meshflow DNA — Semantic Engine Offering

**Product ID:** `DNA-BC-01` (BC-native; additional packs TBD)  
**Status:** Product catalog — SOW may select DNA tier or DNA add-on per [meshflow-pricing-sheet.md](../terms/meshflow-pricing-sheet.md)

**Companion:** [dna-kpi-starter-catalog.md](./dna-kpi-starter-catalog.md) · [dna-semantic-engine.md](../internal-execution-scoping/dna-semantic-engine.md) · [dbc-data-model.md](../dbc-data-model.md)

---

## What DNA is

**DNA — Semantic Engine** turns customer documentation and BC lake data into **versioned, human-validated semantic definitions** — certified gold tables, KPI snapshots, and an interactive Meshflow web portal.

DNA shares the **same ingest pipeline** as Meshflow Signals (bronze → silver). It is **optional** — not every customer needs it.

| Customer profile | Offer |
|---|---|
| HVAC / thin stack / wants ranked to-do list | **Signals only** |
| BC-native, custom KPIs, distrusts ad-hoc reports | **DNA** |
| Signals customer expanding to custom analytics | **DNA add-on** |

---

## Deliverables (v1)

1. **Definition pack portal** — versioned joins, grains, KPI formulas, limitations, approver record
2. **Certified gold tables** — tenant Athena/Glue (`dna_*` tables)
3. **Meshflow web views** — interactive KPI pages + definition browser (no Power BI required)
4. **Optional:** weekly PDF/email export; BYO-BI via Athena ODBC (customer-managed PBI/Fabric)

Power BI is **not** the default deliverable. Managed `.pbix` development is out of scope unless added via change order.

---

## Workflow (Phases A → E)

### Phase A — Discovery & doc collection

- Systems inventory (same as Mesh)
- Collect controller KPI definitions, existing report specs, BC posting rules, dimension usage, golden sample transactions
- **Output:** doc bundle + DNA fit confirmation

### Phase B — Draft definition pack (AI-assisted)

- Rule/AI-assisted draft from customer docs + silver schema + industry starter pack (`bc_intra_v1`)
- Internal review
- **Status:** `draft`

### Phase C — Validation workshop (human)

- 60–90 min with controller: confirm grain, joins, 5–10 KPIs, 2–3 anchor scenarios
- Customer signs definition card (email acceptance OK for v1)
- **Status:** `validated`

### Phase D — Compile, test, publish

- DNA compiler + logic regression tests
- Fix failures → bump pack version
- **Status:** `production`

### Phase E — Ongoing

- Scheduled refresh re-runs compiler against pinned production pack version
- Schema drift / test failure → alert, suppress publish
- Change requests → new pack version; **never silent logic changes**

---

## What's included

| Item | Included |
|---|---|
| BC `full` or agreed entity bundle ingest | Yes (shared with Mesh) |
| Starter KPI library (10 catalog KPIs) | Yes |
| Custom KPIs | Up to **5** at activation; beyond = PS |
| Definition pack portal + web KPI views | Yes |
| Logic regression tests on every publish | Yes |
| Managed Power BI development | No |
| Unlimited custom KPIs | No |
| Audited financials | No |

---

## Fit gate (discovery)

Proceed with DNA when **≥2** are true:

1. Customer runs BC (or full ERP) as system of record with `full` or near-full entity bundle
2. Controller needs **custom** KPIs or cross-module reports not satisfied by catalog Signals
3. Customer distrusts ad-hoc reports / prior BI failed on join correctness
4. Customer will attend validation workshop and sign definition card

**Do not sell DNA** when customer only wants a ranked exception to-do list (Signals is faster and cheaper).

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
