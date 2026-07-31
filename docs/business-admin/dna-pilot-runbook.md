# DNA Pilot Runbook — BC Design Partner

**Purpose:** Execute one BC design partner through the full DNA create → validate → update cycle.

**Audience:** Internal delivery + sales.

**Companion:** [dna-offering.md](../product-scoping/dna-offering.md)

---

## Prerequisites

- [ ] BC `dbc` connector live with `entity_bundle: full` (or agreed subset)
- [ ] Silver consolidate succeeding nightly
- [ ] Controller identified for validation workshop
- [ ] Customer documentation collected (KPI defs, sample reports, posting rules)

---

## Week 1 — Discovery & draft

| Day | Activity | Output |
|---|---|---|
| 1 | Discovery call + doc collection | Doc bundle in `docs/customers/{client}/dna/` |
| 2 | Run `meshflow-dna draft-from-docs` | Draft pack v0.1.0 |
| 3 | Internal review vs `bc_intra_v1` starter | Annotated draft |
| 4–5 | Fix obvious join/grain issues | Draft ready for workshop |

---

## Week 2 — Validation & publish

| Day | Activity | Output |
|---|---|---|
| 1 | Validation workshop (60–90 min) | Signed definition card (email OK) |
| 1 | `meshflow-dna promote --target validated` | Pack v0.2.0+ |
| 2 | `meshflow-dna publish` | Gold tables + manifest |
| 2 | `meshflow-dna serve` demo to controller | Feedback notes |
| 3–5 | Fix failed tests / wrong KPIs → bump version | Production pack |

---

## Success metrics (track per pilot)

| Metric | Target |
|---|---|
| Days draft → validated | ≤ 10 business days |
| Logic test pass rate on first publish | ≥ 80% |
| Controller sign-off on definition card | Yes |
| KPI values within anchor scenario tolerance | Spot-check 2–3 scenarios |
| Controller uses web portal within 2 weeks | ≥ 3 sessions |

---

## Update cycle test

Before closing pilot, run one controlled change:

1. Customer requests KPI definition change (or inject test change)
2. Open change ticket → AI/rule draft diff → re-validate
3. Bump pack version → publish → confirm changelog visible in portal
4. Confirm **no silent logic drift** on unchanged KPIs

---

## Pilot close-out

- [ ] Pricing feedback (activation + monthly willingness)
- [ ] Starter KPI set confirmed or revised in [dna-kpi-starter-catalog.md](../product-scoping/dna-kpi-starter-catalog.md)
- [ ] Case study bullets for GTM (anonymized if needed)
- [ ] Decision: productize DNA SKU or narrow scope

---

## POC tenant (internal)

Use `poc` / `dev` with `dbc` config for dry-run before customer pilot:

```powershell
meshflow-dna publish --config config.yaml --source dbc
meshflow-dna serve --port 8080
```
