# Glue Layer — v1 Scope

What the reconciliation engine **ships in v1**, what waits, and how it unlocks the user-facing product (Option A → Option B).

---

## v1 goal

Prove that invisible glue can produce **trusted daily exceptions** for job-shop manufacturers on **ERP + QuickBooks** — faster and more reliably than manual Excel reconciliation — without custom ETL per client.

**Success:** First tenant gets a published snapshot within **5 business days** of access; morning briefing false-positive rate **< 5%** after tuning week.

---

## In scope (v1)

### Sources

| Source | Priority | Pattern |
|---|---|---|
| ERP (one family P0, one P1) | P0 | Scheduled CSV / ODBC |
| QuickBooks Online | P0 | API |
| QuickBooks Desktop | P0 | Scheduled export |
| Excel / Google Sheets (templated) | P0 | Column map template per file type |

**ERP P0 target:** JobBOSS (or whichever system scores highest in discovery interviews).

**ERP P1 target:** E2 or Epicor — playbook stub acceptable if extracts similar.

### Pipeline capabilities

| Capability | v1 |
|---|---|
| Ingest + raw storage | Yes |
| Playbook-based column map | Yes |
| AI-suggested map drift (internal approve) | Yes |
| Customer ERP ↔ QB match | Yes |
| Job ↔ invoice link | Yes |
| Effective status (shipped vs open) | Yes |
| Promise date fallback tier 1–2 | Yes |
| Promise date tier 3 inference | Optional; strict tenants off by default |
| Batch quality gate + suppression | Yes |
| Review queue (admin) | Yes |
| Tenant memory (aliases, confirmed links) | Yes |
| Provenance chain per exception | Yes |
| Unstructured PDF/email | **No** — v1.1 |

### Canonical entities (v1)

- Customer
- Job / Work order
- Job cost (closed jobs + open WIP where ERP provides)
- Invoice / AR open balance
- Inventory exception row (ERP MRP export or Excel template)

### Downstream exceptions enabled

These feed the user-facing briefing once glue publishes:

| Exception | Glue dependencies |
|---|---|
| Late jobs | `effective_promise_date`, `effective_status`, job $ |
| Past-due AR | QB invoice entities |
| Unbilled WIP | Shipped/complete job + job–invoice link tier B+ |
| Margin outlier (basic) | Closed job cost from ERP, customer link |
| Material shortage | ERP exception report or Excel template linked to job |
| Customer concentration | Revenue rollup via customer link |

---

## Out of scope (v1)

| Item | Target |
|---|---|
| Real-time MES / shop floor | Never v1 |
| Write-back to ERP/QB | v2+ if ever |
| PDF / email unstructured ingest | v1.1 |
| CRM / quoting module | v1.2 |
| Multi-entity consolidation | PS |
| Custom costing / overhead allocation | PS |
| Customer-facing review UI | v1.1 (admin email/link OK v1) |
| Cross-tenant benchmarking | v2+ |
| Full Option B quote-intelligence | v1.2 (basic closed-job margin in v1) |

---

## Automate vs review (v1 defaults)

| Decision | Auto | Review |
|---|---|---|
| Customer match tier A/B | ✓ | |
| Customer match tier C/D | | ✓ |
| Job–invoice link tier B+ | ✓ | |
| Job–invoice link tier C | | ✓ |
| Schema map change | | ✓ (internal) |
| Batch confidence < 0.75 | Suppress | ✓ (internal) |
| Promise date fallback tier 2 | ✓ | |
| Promise date tier 3 inference | | ✓ or exclude |
| Excel → job link tier B+ | ✓ | |
| Excel → job link tier C | | ✓ |

---

## User-facing product coupling

### Phase 1 — Exception briefing (Option A)

Glue v1 must reliably power:

1. Late jobs (ranked by days × $)
2. Past-due AR (from QB)
3. Unbilled WIP (cross-system — **hero proof of glue value**)
4. Optional: shortage rows from Excel/MRP

Delivery: daily email + minimal detail links. Provenance one click.

### Phase 2 — Profitability layer (Option B)

Add on same glue snapshot:

1. Closed job margin table
2. Customer rollup (sum closed jobs)
3. Quote vs actual when quote $ in ERP
4. "Bottom quartile" shortlist → folds into briefing as exception type

Requires: job costing fields in ERP playbook + `cost_status` (provisional vs final).

---

## Onboarding fit gate (must pass before glue build)

Score at discovery — **≥ 7/10** to proceed:

| # | Gate |
|---|---|
| 1 | ERP daily export or ODBC feasible within 5 days |
| 2 | QuickBooks access feasible |
| 3 | Job numbers exist and appear on invoices or memos (for link) |
| 4 | Due or promise dates populated on **≥ 70%** open jobs |
| 5 | Job costing enabled OR unbilled/late-only scope accepted |
| 6 | Named admin for review queue (controller or ops lead) |
| 7 | Client accepts 10-day tuning period |
| 8 | No air-gap / ITAR blocker |
| 9 | Primary contact responds within 1 business day |
| 10 | Client accepts standard margin/late definitions (not custom PS) |

---

## Playbook deliverables (v1 engineering)

Per ERP family playbook:

- [ ] Named standard reports (open jobs, closed jobs, job cost, AR detail if in ERP)
- [ ] Column map → canonical model
- [ ] Status vocabulary map
- [ ] Job number normalization rules
- [ ] Known quirks doc (1 pager)
- [ ] Sample anonymized extract for CI tests

Per accounting playbook (QBO/QBD):

- [ ] Customer list, invoice lines, AR aging extracts
- [ ] Customer ID / name map strategy

---

## Week-by-week delivery (new tenant)

| Day | Milestone |
|---|---|
| 1–2 | Access granted; playbooks selected; first raw extracts |
| 3 | First parse + map; customer match draft |
| 4 | First entity graph; review queue populated |
| 5 | First **published snapshot** (internal) |
| 6–10 | Tuning: false positive fixes, alias confirms |
| 10+ | Briefing goes live to end users |

---

## Internal tooling (v1)

Minimum ops tools for you — not client product:

| Tool | Purpose |
|---|---|
| Batch monitor | Missing files, row count anomalies |
| Review queue admin | Confirm/reject links |
| Provenance debugger | Trace any surfaced fact |
| Playbook editor | Version column maps |
| Tenant memory viewer | Aliases, policies, overrides |

---

## Expansion path (industry repeatability)

Same glue engine, new **definition packs**:

| Pack | Changes |
|---|---|
| `job_shop_mfg` | Job, work center, OTD semantics |
| `distribution` | Order lines, fill rate, OTIF |
| `trade_contractor` | Change orders, job WIP |
| `field_service` | Work orders, callbacks |

Entity types and pipeline stay stable; exception catalog and field maps swap per pack.

---

## v1 metrics dashboard

Track weekly:

| Metric | Target |
|---|---|
| Tenants with daily publish success | ≥ 98% |
| Median onboarding days to first publish | ≤ 5 |
| Customer auto-match rate | ≥ 95% |
| Job–invoice auto-link rate (shipped) | ≥ 85% |
| Briefing false positive rate (client snooze/reject) | < 5% |
| Review items per tenant per week (steady state) | < 10 |
| Glue-hours per onboarding | Baseline then ↓ with playbooks |

---

## Related

- [reconciliation-engine.md](./reconciliation-engine.md)
- [../product-pillars.md](../product-pillars.md)
