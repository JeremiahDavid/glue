# GTM Reset — Industry × Source System Matrix

**Purpose:** Choose a GTM product that hits **the broadest SMB market** while still **landing hard enough to sell** — without anchoring on job shops.

**Product spine (unchanged):** Invisible AI-assisted meshflow links **multiple source systems** → trusted operational facts → **ranked exceptions / insights** (not dashboards, not “data platform” language).

**Companion (system-first view):** [industry-system-clusters.md](./industry-system-clusters.md)

**Status:** Strategic hypothesis — validate with segmented discovery (tag every interview by industry cluster + systems).

---

## Strategic frame

### What “hits the most market” actually means

| Goal | Means | Does not mean |
|---|---|---|
| **Wide TAM** | Same spine + same integration clusters across many verticals | One generic dashboard for every industry |
| **Hard impact** | Dollarized queue in week 1 (cash stuck, delivery broken, margin leaking) | KPI catalog nobody opens |
| **Buildable v1** | QB + Excel + **one ops system family** per cluster | 20 connectors before first customer |

**Ideal shape:** One **spine SKU** (billing / fulfillment / cash completeness) × **industry definition packs** × **integration playbooks** grouped by shared ops system.

---

## Universal layer (every cluster)

Treat these as **assumed** for v1 architecture — not optional nice-to-haves.

| Slot | System | Role | v1 priority |
|---|---|---|---|
| **U1** | **QuickBooks** (Online + Desktop export) | AR, invoices, cash, customer financial identity | **P0 — always** |
| **U2** | **Excel / Google Sheets** (templated ingest) | Shadow ops: allocations, hot lists, pricing, manual reconciliations | **P0 — always** |

Every customer interview should confirm QB (or flag non-QB accounting — out of v1 or separate pack).

**Third slot (ops system of record)** is where industry clustering and connector priority live.

---

## The spine SKU (cross-industry)

**Name (internal):** Fulfillment ↔ billing completeness  
**Buyer message:** *“Stop leaving money on the dock — what shipped, completed, or delivered but never hit QuickBooks.”*

| Why this spine | |
|---|---|
| Exists in **most** operational SMBs (not pure retail counter-sale) | Mfg, dist, trades, field service, pro services, many logistics |
| **Requires cross-system meshflow** (ops ≠ QB) | Defensible vs single-system reports |
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

### Recommended **primary GTM clusters (v1–v2)**

Focus discovery and first playbooks here — aligns with your instinct (product mfg + distribution) and maximizes shared integrations:

1. **A + B** — NetSuite / BC / Fishbowl cluster (distribution + product mfg)  
2. **C + D** — ServiceTitan / Jobber cluster (trades + field service) — *second wave, different playbook*  
3. **E** — Pro services — *often QB + Excel only for v1; add PSA later*

**Defer early:** H (property mgmt), I (restaurant), G (logistics) unless discovery pulls you there — different spine or heavier specialization.

---

## Source system priority (development order)

**Rule:** Prioritize ops systems that **span the most target clusters** with **API or reliable export** — after QB + Excel.

### Tier 0 — Universal (build first)

| System | Industries touched | Integration pattern | Notes |
|---|---|---|---|
| **QuickBooks Online** | All clusters | API | Customer, invoice, AR aging — spine dependency |
| **QuickBooks Desktop** | All (legacy SMB) | Scheduled export | Same semantic model as QBO |
| **Excel / Sheets template** | All | File drop | Column-mapped templates per exception type |

### Tier 1 — Highest cross-industry ops ROI

| System | Primary clusters | Also appears in | v1 rationale |
|---|---|---|---|
| **NetSuite** | A, B | Some E, F | **#1 ops connector** — cloud API, wholesale + mfg + hybrid |
| **Microsoft Dynamics 365 Business Central** | A, B, F | Some C | Strong in dist/mfg; SaaS API; good second playbook |
| **Shopify** | F | Some B (DTC) | Huge retail TAM; clean API; pairs with QB multi-channel pain |

### Tier 2 — Large TAM, vertical-specific (wave 2)

| System | Primary clusters | v1 rationale |
|---|---|---|
| **ServiceTitan** | C, D | Trades/FSM — massive SMB count; API; different entity model |
| **Jobber / Housecall Pro** | C, D | Smaller trades; good for downmarket |
| **Fishbowl / Cin7** | A, B | Inventory-heavy SMB without NetSuite |
| **Harvest / BQE Core** | E | Pro services unbilled WIP |

### Tier 3 — Later / niche

| System | Clusters | Why later |
|---|---|---|
| AppFolio / Buildium | H | PM often single stack; less QB fragmentation |
| Toast / Square | I, F | POS→payment often same day; weaker unbilled Signal |
| Epicor (on-prem job) | Legacy mfg | Access friction — file/ODBC playbook |
| Magaya / TMS variants | G | Specialized, smaller ICP overlap |
| Sage Intacct | Mid-market up | Overlaps NetSuite/BC customers; longer sales |

### Connector priority summary (build order)

```
1. QBO + QBD + Excel templates          (universal)
2. NetSuite                             (clusters A + B — your instinct)
3. Dynamics 365 Business Central        (A + B + F overlap)
4. Shopify                              (retail multi-channel — if retail in v2)
5. ServiceTitan OR Jobber               (pick one trades stack for wave 2)
6. Fishbowl / Cin7                      (NetSuite downmarket alternative)
7. PSA (Harvest/BQE)                    (pro services)
```

---

## Industry × system heat map

**Legend:** ●●● = primary system of record · ●● = common · ● = sometimes · — = rare

|  | NetSuite | BC | Fishbowl/Cin7 | Shopify | ServiceTitan/Jobber | AppFolio | QB | Excel |
|---|---|---|---|---|---|---|---|---|
| **A. Distribution** | ●●● | ●● | ●●● | ● | — | — | ●●● | ●●● |
| **B. Product mfg** | ●●● | ●●● | ●● | ● | — | — | ●●● | ●●● |
| **C. Trades** | ● | ● | — | — | ●●● | — | ●●● | ●●● |
| **D. Field service** | ● | — | — | — | ●●● | — | ●●● | ●● |
| **E. Pro services** | ● | — | — | — | — | — | ●●● | ●●● |
| **F. Retail multi-chan** | ● | ●● | — | ●●● | — | — | ●●● | ●● |
| **G. Logistics SMB** | ● | — | — | — | — | — | ●● | ●●● |
| **H. Property mgmt** | — | — | — | — | — | ●●● | ●● | ●● |
| **I. Restaurant** | — | — | — | — | — | — | ●● | ● |
| **J. Staffing** | ● | — | — | — | — | — | ●●● | ●●● |

**NetSuite + QB + Excel** is the densest **multi-industry** cell (A + B + parts of E, F, G, J).

---

## GTM product shape (reset)

### One company, three layers

```
LAYER 1 — Spine (all customers)
  "Unbilled / incomplete billing" queue
  QB + Excel + ops fulfillment events
  Cash Cycle add-on (past-due AR)

LAYER 2 — Integration playbook (pick at sale)
  netsuite_qb_excel | bc_qb_excel | shopify_qb_excel | servicetitan_qb_excel | ...

LAYER 3 — Industry definition pack (wording + rules)
  distribution | product_mfg | trades | field_service | pro_services | retail
```

**Do not sell** “job shop manufacturing platform.”  
**Do sell** “We connect how you fulfill work to QuickBooks and show what you haven’t billed.”

### Beachhead recommendation (aligned with your instinct + max overlap)

| Decision | Choice | Why |
|---|---|---|
| **Primary clusters** | **A (distribution) + B (product mfg)** | High spine fit; shared NetSuite/BC/Fishbowl stack; your PDM-like intuition |
| **First ops connector** | **NetSuite** | Spans A+B; API; also touches E/F/G at margins |
| **Second ops connector** | **Dynamics BC** or **Fishbowl** | BC = mfg/dist; Fishbowl = downmarket without NetSuite |
| **Universal** | **QBO + Excel** | Every playbook |
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

**Sweet spot:** upper-left **A, B, C, D, E** — hard cash/fulfillment pain + QB/Excel reality + buildable connectors.

---

## Discovery segmentation (required)

Every call — log:

| Field | Values |
|---|---|
| `cluster` | A–J from table above |
| `manufacturing_mode` | mts \| mto \| hybrid \| n/a |
| `accounting` | qbo \| qbd \| other |
| `ops_system` | netsuite \| bc \| fishbowl \| shopify \| servicetitan \| jobber \| other |
| `excel_critical` | y/n — what file |
| `ship_to_invoice_days` | number or unknown |
| `billing_same_system` | y/n |
| `spine_pain_1_5` | self-rated |

**Pivot rule:** If job shops score high but NetSuite mfg/dist score higher on *spine pain × close probability*, drop job-shop as headline ICP.

---

## What changes vs job-shop-first plan

| Before | After (reset) |
|---|---|
| Job-shop ICP headline | **Fulfillment ↔ QB billing completeness** headline |
| JobBOSS-first connector | **QBO + Excel + NetSuite** first |
| Late jobs as follow-on | **Backorder / OTIF / fill rate** (dist) or **partial line bill** (dist/mfg) |
| Six mfg dashboards | Ranked exception queues per cluster |
| Single vertical marketing | **Cluster packs** with shared spine |

Job shops **remain in cluster B/C** when they run NetSuite/BC/ServiceTitan — not excluded, just not the center of gravity.

---

## Risks of “widest market” approach

| Risk | Mitigation |
|---|---|
| Messaging too generic | Lead with **cash stuck unbilled** — same sentence everywhere |
| Connector sprawl | **Max 1 new ops family per quarter** after QB+Excel |
| Wrong industry in discovery average | **Segment tags** — never blend scores |
| NetSuite customers have built-in reports | Sell **QB cross-system** gap, not NS dashboards |
| Property mgmt / restaurant misfit | Explicit **defer list** — don’t chase in year 1 |

---

## Open decisions

- [ ] Confirm **NetSuite** vs **BC** as first ops playbook (run 5 interviews in A+B with each)
- [ ] Name the spine SKU externally (avoid “Meshflow” / “analytics”)
- [ ] Wave 2: **trades** (ServiceTitan) vs **retail** (Shopify) — pick after cluster A+B paid customers
- [ ] Minimum deal size / employee band per cluster

---

## Related docs

- [industry-system-clusters.md](./industry-system-clusters.md) — system-first playbooks and build order
- [retail-problem-opportunity-ranking.md](./Industry-opportunities/retail-problem-opportunity-ranking.md) — retail-specific pains and Signals
- [trades-construction-problem-opportunity-ranking.md](./Industry-opportunities/trades-construction-problem-opportunity-ranking.md) — trades/construction pains and Signals
- [gtm-product-mfg-distribution.md](./gtm-product-mfg-distribution.md) — beachhead SKU detail
- [job-shop-manufacturing-problem-opportunity-ranking.md](./Industry-opportunities/job-shop-manufacturing-problem-opportunity-ranking.md) — legacy narrow ICP
- [smaller-manufacturing-problem-opportunity-ranking.md](./Industry-opportunities/smaller-manufacturing-problem-opportunity-ranking.md) — product mfg vs job shop
- [small-distribution-problem-opportunity-ranking.md](./Industry-opportunities/small-distribution-problem-opportunity-ranking.md) — distributor ranking
- [reconciliation-engine.md](./reconciliation-engine.md) — technical spine
- [README.md](./README.md)

---

## Revision log

| Date | Change |
|---|---|
| 2026-07-18 | Cross-links to industry-system-clusters and retail ranking |
| 2026-07-20 | Link trades/construction problem-opportunity ranking |
