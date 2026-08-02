# MAP Meshflow DNA — Statement of Work (SOW)

**Template only — not legal advice.** Replace all `[bracketed]` fields. Have a qualified attorney review before use.

**SOW number:** `[SOW-DNA-2026-001]`  
**Effective date:** `[Date]`

**Governing MSA:** [meshflow-msa-template.md](./meshflow-msa-template.md) · **Pricing:** [meshflow-pricing-sheet.md](./meshflow-pricing-sheet.md) · **Offering:** [dna-offering.md](../product-scoping/dna-offering.md)

---

## 1. Purpose

This SOW defines scope, deliverables, and fees for **Meshflow DNA — Semantic Engine**: versioned definition packs, certified gold tables, logic regression tests, and Meshflow web KPI views on Client's Business Central (and optional adjunct) data.

This may be a **standalone DNA engagement** or a **DNA add-on** to an existing Meshflow Signals subscription (change order references parent SOW `[SOW-MESHFLOW-…]`).

---

## 2. Fees & payment

**Pricing phase:** `[Beta / GA]` — see [meshflow-pricing-sheet.md](./meshflow-pricing-sheet.md) DNA phased rollout.

| Item | Beta | GA target | Due |
|---|---|---|---|
| **DNA implementation** (one-time) | **$0** | **$[5,000 / 2,500 add-on]** | On SOW signature (GA only) |
| **Monthly DNA subscription** | **$[100 / 100 add-on] / month** | **$[1,000 / 600 add-on] / month** | Monthly, Net 15, beginning `[date]` |
| **Custom KPIs beyond included cap** | — | — | Self-service via DNA documentation; provider PS optional |

*Beta clients migrate to GA pricing on renewal or when Phase 2 is announced (typically 30 days notice).*

---

## 3. Scope

### 3.1 Systems

| System | Role |
|---|---|
| `[Dynamics 365 Business Central]` | Primary semantic source (`dbc`) |
| `[Excel / adjunct — optional]` | Supplemental dimensions or forecasts |

### 3.2 Definition pack

| Item | Detail |
|---|---|
| **Starter pack base** | `bc_intra_v1` industry template |
| **Customization** | Customer DNA file (YAML/MD) — self-service updates via documentation |
| **Reporting pack** | Customer reporting file (YAML/MD) — portal layout via Reporting Engine |
| **Initial onboarding** | Provider assists first DNA + reporting file draft |
| **Approval** | Version promotion (draft → validated → production) |

### 3.3 Deliverables

| Deliverable | Format |
|---|---|
| Versioned **Definition Pack** | Portal + JSON/YAML artifact |
| **Certified gold tables** | Tenant Athena/Glue (`dna_*`) |
| **KPI web views** | Meshflow browser UI |
| **Logic regression tests** | Run on every publish |
| **Publish manifest** | Version, compiler hash, test results |

**Not included:** Managed Power BI `.pbix`, audited financials.

---

## 4. Workflow & acceptance

| Phase | Acceptance |
|---|---|
| A — Doc collection | Client provides KPI docs + sample reports |
| B — Draft pack | Provider delivers draft for review |
| C — Validation workshop | Client confirms grain, joins, KPI definitions |
| D — Publish | Logic tests pass; gold tables refresh on schedule |
| E — Ongoing | Changes via versioned pack updates only |

**Trial (if applicable):** 2 weeks on starter KPI set per [meshflow-trial-terms.md](./meshflow-trial-terms.md) DNA variant.

---

## 5. Change control

Logic changes require a **new Definition Pack version** — no silent changes to production KPIs. Client may request updates via written change order; Provider delivers revised pack + re-validation as needed.

---

## Appendix A — Example filled scope (BC distribution — remove or replace)

| Field | Value |
|---|---|
| Client | `[Acme Distribution Inc.]` |
| Systems | BC `full` bundle only |
| Custom KPIs | Ship-to-invoice lag, line margin, DSO, fill rate, backorder $ |
| Pricing phase | Beta |
| Implementation | $0 |
| Monthly | $100 |

---

*End of DNA SOW template*
