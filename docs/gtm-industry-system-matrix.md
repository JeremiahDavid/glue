# GTM Reset — Industry × Source System Matrix

**Purpose:** Choose a GTM product that hits **the broadest SMB market** while still **landing hard enough to sell** — without anchoring on job shops.

**Product spine:** Invisible AI-assisted meshflow links **source systems or full-ERP module domains** → trusted operational facts → **ranked exceptions / insights** (not dashboards, not “data platform” language).

**Companion (system-first view):** [industry-system-clusters.md](./industry-system-clusters.md)

**Status:** Strategic hypothesis—**A+B is the provisional ICP; BC and NetSuite are the leading Phase 1 candidates.** Fishbowl/Cin7 are validation-only because native integrations erode the original split-stack wedge.

---

## Strategic frame

### What “hits the most market” actually means

| Goal | Means | Does not mean |
|---|---|---|
| **Wide TAM** | Same spine + same integration clusters across many verticals | One generic dashboard for every industry |
| **Hard impact** | Dollarized queue in week 1 (cash stuck, delivery broken, margin leaking) | KPI catalog nobody opens |
| **Buildable v1** | One validated system family + shared canonical model | 20 connectors before first customer |

**Ideal shape:** One **spine SKU** (billing / fulfillment / cash completeness) × **industry definition packs** × **integration playbooks** grouped by shared system family. The playbook may connect separate ops + accounting systems or cross modules inside a full ERP.

**Layer 4 — DNA (optional):** For BC/full-ERP customers needing **custom semantic analytics**, [Meshflow DNA](../product-scoping/dna-offering.md) adds versioned definition packs and certified gold tables on the same ingest pipeline. Signals-only customers (e.g. HVAC thin stack) skip DNA.

---

## Common foundation and accounting paths

Treat the canonical model, ranked-exception engine, and Excel ingest as reusable foundation. Do **not** assume every A+B customer uses QuickBooks.

| Slot | System | Role | v1 priority |
|---|---|---|---|
| **U1-QB** | **QuickBooks** (Online + Desktop export) | Accounting for split-stack customers | **Foundation already in progress** |
| **U1-ERP** | **NetSuite or Business Central** | Cross-module accounting + operations; optional external nodes | **Phase 1 candidate — choose one family** |
| **U2** | **Excel / Google Sheets** (templated ingest) | Shadow ops: allocations, hot lists, pricing, manual reconciliations | **Common foundation** |

Every customer interview should identify the accounting and operations system of record. A full ERP is not automatically out of scope: discovery must test whether cross-module reporting and recurring exception management remain painful.

For a split stack, the ops system is the additional node. For a full ERP, the product connects ERP modules and any critical Excel or satellite workflows into the same operational fact model.

---

## The spine SKU (cross-industry)

**Name (internal):** Fulfillment ↔ billing completeness  
**Buyer message:** *“Stop leaving money on the dock—see what shipped, completed, or delivered without the right billing or follow-through.”*

| Why this spine | |
|---|---|
| Exists in **most** operational SMBs (not pure retail counter-sale) | Mfg, dist, trades, field service, pro services, many logistics |
| **Requires connected operational facts** | Cross-system for split stacks; cross-module/historical for full ERPs |
| ROI in days | “$X unbilled right now” |
| Same engine | Match entity, link fulfillment event → invoice, rank by $ × age |

**Entity varies by pack:** shipment line · job complete · WO closed · project milestone · delivery ticket — same pipeline.

**Weaker spine fit (defer or different pack):**
- **Property management** — rent billing often inside AppFolio/Buildium; different cadence (leases, delinquency)
- **Counter retail** — sale = payment; less fulfillment→invoice gap
- **Pure logistics 3PL** — billing on scans/contracts; heavier TMS/WMS, smaller $5–30M sweet spot

---

## Industry clusters (10 segments)

Grouped by **who buys**, **ops pain**, and **typical third-slot system** — not by NAICS alone.

| Cluster | Example businesses | Ops unit | Spine fit (1–5) | QB + Excel | Typical ops system (slot 3) |
|---|---|---|---|---|---|
| **A. Wholesale / distribution** | Industrial supply, building materials, F&B wholesale | SO line / ship | **5** | Very common | NetSuite, Dynamics BC, Fishbowl, Cin7 |
| **B. Product / repetitive manufacturing** | Catalog makers, process/light assembly (PDM-like) | SO / ship / FG | **5** | Very common | NetSuite, BC, Epicor (SaaS), Fishbowl |
| **C. Trades / construction (SMB)** | HVAC, electrical, plumbing, roofing | Job / WO | **5** | Very common | ServiceTitan, Jobber, Housecall Pro, Sage |
| **D. Field service & equipment** | Commercial service, equipment repair | Ticket / WO | **5** | Very common | ServiceTitan, FieldEdge, ServiceMax lite |
| **E. Professional services** | Agencies, engineering, consultancies | Project / time | **4** | Dominant | Harvest, BQE, Mavenlink, **QB + Excel heavy** |
| **F. Retail (multi-channel)** | Shopify + wholesale + marketplace | Order line | **3–4** | Common | Shopify, Lightspeed, Square, BC |
| **G. Logistics / delivery (SMB)** | Regional courier, freight broker lite, 3PL small | Load / shipment | **3** | Mixed | Spreadsheets + TMS lite, Magaya, custom |
| **H. Property management (SMB)** | Residential PM, small commercial | Unit / lease | **2–3** | Mixed — often **in-app** | AppFolio, Buildium, Rent Manager |
| **I. Restaurants / hospitality** | Single/multi-unit | Ticket | **2** | Mixed | Toast, Square — often integrated | 
| **J. Staffing / light workforce** | Temp staffing, guards | Timesheet / placement | **4** | Common | Bullhorn lite, spreadsheets, QB payroll |

### Recommended **primary GTM clusters (provisional)**

Focus discovery and first playbooks here — aligns with your instinct (product mfg + distribution) and maximizes shared integrations:

1. **A + B** — NetSuite / BC / Fishbowl / Cin7 cluster (distribution + product mfg); **retain as ICP while validating system mix**
2. **C + D** — ServiceTitan / Jobber cluster (trades + field service) — *second wave, different playbook*  
3. **E** — Pro services — *often QB + Excel only for v1; add PSA later*

**Defer early:** H (property mgmt), I (restaurant), G (logistics) unless discovery pulls you there — different spine or heavier specialization.

---

## Source system candidates (development order not yet locked)

**Rule:** Choose the first A+B family using **reachable account count × recurring pain × willingness to pay × data accessibility × repeatability**. Prevalence alone and cross-system novelty alone are insufficient.

### Existing/shared foundation

| System | Industries touched | Integration pattern | Notes |
|---|---|---|---|
| **QuickBooks Online** | Broad; split-stack path | API | Existing customer, invoice, payment, and AR ingest |
| **QuickBooks Desktop** | Broad legacy split-stack path | Scheduled export | Same semantic model as QBO when selected |
| **Excel / Sheets template** | All | File drop | Column-mapped templates per exception type |

### Phase 1 candidates — validate head-to-head

| System | Primary clusters | Also appears in | v1 rationale |
|---|---|---|---|
| **NetSuite** | A, B | Some E, F | Full-ERP path; test cross-module order-to-cash, inventory, margin, multi-entity, and Excel-shadow pain |
| **Microsoft Dynamics 365 Business Central** | A, B, F | Some C | Full-ERP path; strong dist/mfg fit; test the same packaged operational-control Signals |
| **Fishbowl / Cin7 + QB** | A, B | — | **Validate only:** both provide native accounting integrations; require evidence of recurring, expensive sync or operational-control gaps before connector work |

### Post-beachhead candidates — after the A+B family is selected

| System | Primary clusters | v1 rationale |
|---|---|---|
| **ServiceTitan** | C, D | Trades/FSM — massive SMB count; API; different entity model |
| **Jobber / Housecall Pro** | C, D | Smaller trades; good for downmarket |
| **Harvest / BQE Core** | E | Pro services unbilled WIP |

### Tier 3 — Later / niche

| System | Clusters | Why later |
|---|---|---|
| AppFolio / Buildium | H | PM often single stack; less QB fragmentation |
| Toast / Square | I, F | POS→payment often same day; weaker unbilled Signal |
| Epicor (on-prem job) | Legacy mfg | Access friction — file/ODBC playbook |
| Magaya / TMS variants | G | Specialized, smaller ICP overlap |
| Sage Intacct | Mid-market up | Overlaps NetSuite/BC customers; longer sales |

### Connector decision sequence

```
0. Shared foundation: canonical model, exception engine, Excel; retain existing QBO ingest
1. Discovery gate across A+B:
   a. Business Central cross-module (+ optional Excel / satellites)
   b. NetSuite cross-module (+ optional Excel / satellites)
   c. Fishbowl or Cin7 + QB only when native-integration gaps are demonstrated
2. Build ONE Phase 1 family based on scored evidence and reachable pilot partners
3. Add the second family only after the first produces repeatable paid Signals
4. Choose wave 2 vertical (Shopify or ServiceTitan/Jobber) after A+B validation
```

---

## Industry × system heat map

**Legend:** ●●● = primary system of record · ●● = common · ● = sometimes · — = rare

|  | Fishbowl/Cin7 | NetSuite | BC | Shopify | ServiceTitan/Jobber | AppFolio | QB | Excel |
|---|---|---|---|---|---|---|---|---|
| **A. Distribution** | ●●● | ●● | ●● | ● | — | — | ●●● | ●●● |
| **B. Product mfg** | ●● | ●● | ●● | ● | — | — | ●●● | ●●● |
| **C. Trades** | — | ● | ● | — | ●●● | — | ●●● | ●●● |
| **D. Field service** | — | ● | — | — | ●●● | — | ●●● | ●● |
| **E. Pro services** | — | ● | — | — | — | — | ●●● | ●●● |
| **F. Retail multi-chan** | — | ● | ●● | ●●● | — | — | ●●● | ●● |
| **G. Logistics SMB** | — | ● | — | — | — | — | ●● | ●●● |
| **H. Property mgmt** | — | — | — | — | — | ●●● | ●● | ●● |
| **I. Restaurant** | — | — | — | — | — | — | ●● | ● |
| **J. Staffing** | — | ● | — | — | — | — | ●●● | ●●● |

**Current interpretation:** Fishbowl and Cin7 already integrate natively with QBO/Xero; Cin7 also connects commerce channels such as Shopify. That materially weakens connectivity and basic billing reconciliation as a standalone Meshflow wedge. NetSuite/BC cross-module operational control is now the stronger Phase 1 hypothesis, while split-stack playbooks remain validation-only for integration assurance or exception workflows their native tools do not solve.

---

## GTM product shape (reset)

### One company, three layers

```
LAYER 1 — Spine (all customers)
  Billing / fulfillment / cash completeness
  Canonical order → fulfillment → invoice → payment facts
  Ranked operational exceptions

LAYER 2 — System-family playbook (pick at sale)
  fishbowl_qb_excel | cin7_qb_excel | netsuite_intra | bc_intra | shopify_qb_excel | servicetitan_qb_excel | ...

LAYER 3 — Industry definition pack (wording + rules)
  distribution | product_mfg | trades | field_service | pro_services | retail
```

**Do not sell** “job shop manufacturing platform.”  
**Do sell** “We connect orders, fulfillment, billing, and cash and show what needs action.”

### Beachhead recommendation (industry fixed provisionally; system family open)

| Decision | Choice | Why |
|---|---|---|
| **Primary clusters** | **A (distribution) + B (product mfg)** | High operational-control fit for BC/NetSuite; split stacks remain validation cohorts |
| **Phase 1 system family** | **Open: BC vs NetSuite; Fishbowl/Cin7 only if a native-integration gap validates** | Select from segmented discovery and pilot access |
| **Split-stack hypothesis** | **Fishbowl or Cin7 + QB + Excel** | Downgraded: native integrations already handle core transaction flow; test integration assurance and unsolved operational Signals only |
| **Full-ERP hypothesis** | **Choose BC or NetSuite, not both initially** | Potentially broader upper-SMB/mid-market reach, higher ACV, and cross-module operational-control value |
| **Existing foundation** | **QBO ingest** | Reuse if split-stack wins; do not let sunk work dictate ICP |
| **Wave 2 cluster** | **C+D trades** via ServiceTitan or Jobber | Huge TAM; same spine, different entities |
| **Wave 2 retail** | **Shopify + QB** | Only if multi-channel unbilled/ mismatch pain validates |

---

## Impact vs TAM matrix (where to hunt)

```
Impact (spine $ pain) ↑
5 │  A Dist   B Mfg   C Trades   D Field svc   E Pro svc
  │  J Staffing
4 │  F Retail (multi-chan)     G Logistics
3 │  H Property mgmt
2 │  I Restaurant
1 └──────────────────────────────────────────────→ TAM / reach
         narrow                                    broad
```

**Sweet spot:** upper-left **A, B, C, D, E**—hard cash/fulfillment pain, recurring shadow workflows, and buildable source access.

---

## Discovery segmentation (required)

Every call — log:

| Field | Values |
|---|---|
| `cluster` | A–J from table above |
| `revenue_band` | `<5m` \| `5-15m` \| `15-50m` \| `50-150m` \| `150m+` |
| `employee_band` | `<25` \| `25-75` \| `76-200` \| `201-500` \| `500+` |
| `manufacturing_mode` | mts \| mto \| hybrid \| n/a |
| `accounting` | qbo \| qbd \| netsuite \| bc \| other |
| `ops_system` | fishbowl \| cin7 \| netsuite \| bc \| shopify \| servicetitan \| jobber \| other |
| `excel_critical` | y/n — what file |
| `ship_to_invoice_days` | number or unknown |
| `billing_same_system` | y/n |
| `spine_pain_1_5` | self-rated |

**Pivot rule:** If job shops score high but NetSuite mfg/dist score higher on *spine pain × close probability*, drop job-shop as headline ICP.

---

## What changes vs job-shop-first plan

| Before | After (reset) |
|---|---|
| Job-shop ICP headline | **A+B operational-control Signals** selected from recurring pain |
| JobBOSS-first connector | **A+B system family selected from split-stack QBO, BC, and NetSuite evidence** |
| Late jobs as follow-on | **Backorder / OTIF / fill rate** (dist) or **partial line bill** (dist/mfg) |
| Six mfg dashboards | Ranked exception queues per cluster |
| Single vertical marketing | **Cluster packs** with shared spine |

Job shops **remain in cluster B/C** when they run NetSuite/BC/ServiceTitan — not excluded, just not the center of gravity.

---

## Risks of “widest market” approach

| Risk | Mitigation |
|---|---|
| Messaging too generic | Lead with **cash stuck unbilled** — same sentence everywhere |
| Connector sprawl | **Max 1 new system family per quarter** after shared foundation |
| Wrong industry in discovery average | **Segment tags** — never blend scores |
| NetSuite/BC customers have native reporting | Sell packaged cross-module facts, historical state, ranked exceptions, and resolution workflow—not generic custom reporting |
| Fishbowl/Cin7 already integrate with accounting and commerce | Do not sell connectivity; require recurring sync failures or operational exceptions that native integration dashboards cannot resolve |
| System choice follows intuition rather than evidence | Score segmented discovery by reachable accounts, pain, willingness to pay, access, and repeatability |
| Property mgmt / restaurant misfit | Explicit **defer list** — don’t chase in year 1 |

---

## Open decisions

- [ ] Validate the A+B system mix by company size: split-stack QBO, BC, NetSuite, and other
- [ ] Score **BC vs NetSuite** as primary candidates; retain Fishbowl/Cin7 only where native integration assurance or an unsolved Signal is demonstrably valuable
- [ ] For Fishbowl/Cin7 interviews, document native integration coverage, error frequency, reconciliation hours, dollar exposure, and what built-in dashboards fail to resolve
- [ ] Select exactly **one Phase 1 system family** and secure a design partner before hardening its connector
- [ ] For full ERP candidates, validate packaged cross-module Signals rather than generic “better reporting”
- [ ] Name the spine SKU externally (avoid “Meshflow” / “analytics”)
- [ ] Wave 2: **trades** (ServiceTitan) vs **retail** (Shopify) — pick after cluster A+B paid customers
- [ ] Minimum deal size / employee band per cluster

---

## Related docs

- [industry-system-clusters.md](./industry-system-clusters.md) — system-first playbooks and build order
- [retail-problem-opportunity-ranking.md](./Industry-opportunities/retail-problem-opportunity-ranking.md) — retail-specific pains and Signals
- [trades-construction-problem-opportunity-ranking.md](./Industry-opportunities/trades-construction-problem-opportunity-ranking.md) — trades/construction pains and Signals
- [gtm-product-mfg-distribution.md](./gtm-product-mfg-distribution.md) — provisional A+B ICP and system-family discovery gate
- [job-shop-manufacturing-problem-opportunity-ranking.md](./Industry-opportunities/job-shop-manufacturing-problem-opportunity-ranking.md) — legacy narrow ICP
- [smaller-manufacturing-problem-opportunity-ranking.md](./Industry-opportunities/smaller-manufacturing-problem-opportunity-ranking.md) — product mfg vs job shop
- [small-distribution-problem-opportunity-ranking.md](./Industry-opportunities/small-distribution-problem-opportunity-ranking.md) — distributor ranking
- [reconciliation-engine.md](./internal-execution-scoping/reconciliation-engine.md) — technical spine
- [README.md](../README.md)

---

## Revision log

| Date | Change |
|---|---|
| 2026-07-18 | Cross-links to industry-system-clusters and retail ranking |
| 2026-07-20 | Link trades/construction problem-opportunity ranking |
| 2026-07-23 | Beachhead → Fishbowl/Cin7 + QB; NS/BC = full ERP (+ Excel) |
| 2026-07-23 | Keep A+B as provisional ICP; reopen Phase 1 system family across split-stack, BC, and NetSuite paths |
| 2026-07-23 | Downgrade Fishbowl/Cin7 to validation-only after confirming native QBO/Xero/Shopify integration coverage |
