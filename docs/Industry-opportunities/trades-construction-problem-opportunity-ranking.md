# Trades / Construction — Problem Opportunity Ranking (Pre-Discovery)

**Scope:** SMB **trades & light construction** ($2M–$40M) — HVAC, plumbing, electrical, roofing, general contracting (residential + light commercial), and overlapping **field service** shops that run jobs / work orders in the field.

**Not in scope here:** Large GCs on Procore + job-cost ERP at enterprise scale; pure material suppliers (see [small-distribution](./small-distribution-problem-opportunity-ranking.md)); pure counter retail with no field jobs.

**Cluster:** **C — Trades / construction** (+ **D — Field service** overlap) in [gtm-industry-system-matrix.md](../gtm-industry-system-matrix.md)

**Companions:**
- [industry-system-clusters.md](../industry-system-clusters.md) — `servicetitan_qb_excel` / `jobber_hcp_qb_excel`
- [job-shop-manufacturing-problem-opportunity-ranking.md](./job-shop-manufacturing-problem-opportunity-ranking.md) — same “complete → bill” spine, different entity
- [retail-problem-opportunity-ranking.md](./retail-problem-opportunity-ranking.md) — Square overlap for small trades
- [small-distribution-problem-opportunity-ranking.md](./small-distribution-problem-opportunity-ranking.md) — contractors as *customers* of distributors, not ICP here

**Purpose:** Rank trades/construction pains for Meshflow before discovery. Wave-2 cluster after mfg/dist beachhead — same spine, **job/WO-centric** entity model.

**Status:** Pre-discovery hypothesis. Validate with 8–10 tagged interviews (`cluster = C` or `D`).

---

## Trades vs mfg / distribution — what’s different

| Dimension | Product mfg / dist | **Trades / construction** |
|---|---|---|
| **Unit of work** | SO line / shipment | **Job / work order / ticket** |
| **Fulfillment event** | Ship / pick confirm | **Job complete, WO closed, tech checkout, milestone** |
| **Cash leak shape** | Shipped, not invoiced | **Completed / approved, not invoiced; CO not billed; parts on truck** |
| **Ops fire** | Backorder, OTIF | **Callbacks, schedule slips, change orders, truck stock** |
| **System #3** | NetSuite, BC, Fishbowl | **ServiceTitan, Jobber, Housecall Pro, Sage, AccuLynx** |
| **Who bills** | Accounting after warehouse | **Office after tech** — dispatch culture, not dock culture |
| **Meshflow sweet spot** | Shipment ↔ invoice line | **WO/job complete ↔ QB invoice; CO ↔ billable event** |

**Headline:** Trades is **excellent spine fit** (completed work ↔ QuickBooks). Pain language is **jobs and tickets**, not shipments. Change orders and materials-on-job rise vs pure mfg.

---

## Universal stack (trades)

| Slot | System | Role |
|---|---|---|
| **U1** | **QuickBooks** (Online / Desktop) | Invoices, AR, customer financial identity — almost always separate from FSM |
| **U2** | **Excel / Sheets** | Job lists, CO trackers, material takeoffs, week-end billing holds |
| **U3** | **FSM / job system** | ServiceTitan, Jobber, Housecall Pro, Sage 100 Contractor, AccuLynx, Service Fusion |

See playbooks: `servicetitan_qb_excel` | `jobber_hcp_qb_excel` | `square_qb_excel` (small / downmarket)

---

## How to read the scores

Same formula as companion docs:

| Score | **Business importance** (1–5) | **Ease of implementation** (1–5) |
|---|---|---|
| 5 | Owner/controller loses sleep; cash or churn | Clean FSM + QB fields; days to first value |

**Meshflow novelty (1–5):** Requires FSM ↔ QB (or Excel) join — not a single ServiceTitan report.

**Trades fit (1–5):** How cleanly this maps to a productized exception queue for trades buyers.

**Launch score** = `(Importance × 2) + Ease + Meshflow novelty`  
**Product score** = Launch score + Trades fit (trades-specific prioritization)

---

## Ranked catalog — trades / construction

### Tier A — Strong launch / early products

| Rank | Problem | Imp. | Ease | Meshflow | Trades fit | Product | vs job shop | Notes |
|---|---|---|---|---|---|---|---|---|
| **1** | **Completed / closed WO not invoiced** | 5 | 4 | 5 | 5 | **23** | Same family — **job complete** not ship | Core spine; ServiceTitan “done” ≠ QB invoice |
| **2** | **Past-due AR — ranked collections** | 5 | 5 | 2 | 4 | **21** | Same | Universal Cash Cycle add-on; weak solo Meshflow |
| **3** | **Approved change orders not billed** | 5 | 3 | 5 | 5 | **21** | **↑ vs mfg** (#15 there) | Signature trades pain; Excel CO lists common |
| **4** | **Materials / parts used on job, missing on invoice** | 5 | 3 | 5 | 5 | **21** | Morph of partial ship | Truck stock + PO → job → invoice gap |
| **5** | **Labor / tech hours on job, missing on invoice** | 4 | 3 | 5 | 5 | **19** | Morph of labor variance | T&M and flat-rate underbill; FSM time ↔ invoice |

### Tier B — Strong follow-ons (same meshflow spine)

| Rank | Problem | Imp. | Ease | Meshflow | Trades fit | Product | Notes |
|---|---|---|---|---|---|---|---|
| **6** | **Customer identity chaos (FSM ↔ QB)** | 3 | 4 | 5 | 4 | **19** | Enabler — sell via unbilled outcomes |
| **7** | **Progress / milestone billing incomplete** | 4 | 2 | 5 | 4 | **17** | Strong for remodel / light GC; definition fights |
| **8** | **Membership / maintenance plan billing gaps** | 4 | 3 | 4 | 4 | **18** | Recurring revenue leak; ServiceTitan-native competitors |
| **9** | **Unprofitable jobs / techs (closed-job margin)** | 5 | 2 | 3 | 4 | **17** | Owner gold long-term; cost completeness hard |
| **10** | **Quote / estimate vs actual variance** | 4 | 2 | 3 | 4 | **15** | Estimator + GM; needs clean estimate + actuals |
| **11** | **Jobs stuck “ready to bill” (doc / photo / approval hold)** | 4 | 3 | 3 | 4 | **17** | Ops process + Meshflow snooze reasons; high false positives if naive |
| **12** | **Callback / warranty work eating margin (untracked)** | 4 | 2 | 3 | 3 | **15** | Real pain; tagging discipline required |

### Tier C — Real but poor Meshflow v1 fit

| Rank | Problem | Imp. | Ease | Meshflow | Trades fit | Product | Why defer |
|---|---|---|---|---|---|---|---|
| **13** | **Schedule / capacity overload** | 5 | 1 | 1 | 2 | **12** | Crowded (ServiceTitan dispatch); not reconciliation |
| **14** | **Truck stock / van inventory accuracy** | 4 | 1 | 2 | 2 | **11** | Mobile inventory product category |
| **15** | **Permit / inspection delaying close** | 3 | 2 | 2 | 2 | **11** | Niche; weak dollar queue alone |
| **16** | **Lead → booked conversion** | 4 | 2 | 1 | 1 | **11** | CRM / marketing stack |
| **17** | **Technician utilization %** | 4 | 2 | 1 | 2 | **11** | FSM-native dashboards |
| **18** | **Cash application / unmatched payments** | 4 | 2 | 4 | 2 | **14** | Bill.com / Lockstep territory |

---

## Comparison — what moves vs other clusters

| Problem | Job shop | Product mfg / dist | **Trades / construction** |
|---|---|---|---|
| Unbilled fulfillment | **#1** (ship) | **#1** (ship / line) | **#1** (**job / WO complete**) |
| Past-due AR | #2 | #2 | #2 |
| **Change orders not billed** | Tier C (#15) | Low | **#3** |
| **Parts / materials on invoice** | Partial ship | Line partial | **#4** |
| **Labor hours on invoice** | Labor vs est (#13) | Low | **#5** |
| Late jobs / OTD | #3 | Falls | → schedule slips — **defer as hero** |
| Backorder / OTIF | Low | **#3–5** | N/A (unless material supply arm) |
| Membership billing | N/A | N/A | **#8** (HVAC / plumbing) |
| Progress billing | Rare | Rare | **#7** (remodel / GC) |

---

## Launch Signal for trades

### Still the spine: Billing completeness — entity = **job / WO complete**

> **“Job 8841 closed Friday — QuickBooks still has no invoice. Here’s $X ready to bill.”**

| Why it wins | Trades nuance |
|---|---|
| Cash stuck after work left the truck | Tech closes ticket; office forgets or waits on photos/approvals |
| Ops ≠ finance gap | FSM is system of record for work; QB for money |
| Meshflow novelty | WO complete / approved ↔ invoice match; age × $ ranking |
| ROI | Dollarize unbilled completed work in week 1 |

**Product name sketch:** *“Bill what you finished”* or *“Closed-job invoice gap”* — not “unbilled shipments.”

### Best **second** products for trades (pick by sub-segment)

| Pack | Buyer | When it wins |
|---|---|---|
| **Change-order billing** | Owner / office mgr | Remodel, roofing, GC — COs in Excel or FSM notes |
| **Materials + labor completeness** | Controller | T&M and “parts heavy” service; truck stock → invoice |
| **Cash Cycle** (bundle) | Controller | Unbilled completed + past-due AR |
| **Membership billing** (later) | Owner (HVAC) | Service agreements with missed renewals / visits |

**Do not lead with:** dispatch optimization, tech utilization, lead gen, van inventory accuracy.

---

## Recommended roadmap — trades track (wave 2)

```
LAUNCH (shared spine — trades pack)
  Completed / closed WO not invoiced
       │
       ├─► + Past-due AR                 = Cash Cycle pack
       ├─► + Materials missing on invoice
       ├─► + Labor hours missing on invoice
       │
TRADES PACK (follow-on)
       ├─► Approved change orders not billed
       ├─► Progress / milestone incomplete (GC / remodel)
       ├─► Membership / maintenance gaps (HVAC)
       │
LATER
       ├─► Closed-job margin outliers
       ├─► Quote vs actual
       └─► Callback / warranty tracking
```

**GTM timing:** After A+B (NetSuite) paid proof — unless discovery pulls C+D first. Same engine; new playbook + definition pack.

---

## Sub-segments (rankings shift)

| Sub-segment | Top pain after unbilled WO | Best follow-on |
|---|---|---|
| **HVAC / plumbing service** | Membership gaps; parts on truck | #8, #4 |
| **Electrical (service)** | Labor underbill; CO light | #5, #4 |
| **Roofing / exterior** | Change orders; progress draws | #3, #7 |
| **Remodel / light GC** | Progress billing; CO leakage | #7, #3 |
| **Commercial FSM / equipment** | Completed ticket → invoice (cluster D) | #1, #2 |
| **Downmarket Jobber / HCP / Square** | Same spine; thinner FSM data | #1 first; simplify #3–5 |

---

## Systems & data model implications

### Typical stack

| Role | Common systems |
|---|---|
| FSM / jobs | ServiceTitan, Jobber, Housecall Pro, Service Fusion, AccuLynx |
| Accounting | QuickBooks Online / Desktop (dominant) |
| Estimating / takeoff | Excel, JobNimbus, AccuLynx, Sage |
| Payments | ST Payments, Jobber Payments, Square |
| Payroll | Gusto, ADP, QB Payroll |

### Canonical entities (trades Meshflow)

| Entity | Maps from mfg/dist |
|---|---|
| `WorkOrder` / `Job` | SalesOrder / Job |
| `JobCompleteEvent` (closed, approved, checkout) | Shipment |
| `ChangeOrder` | (new — first-class) |
| `JobMaterialLine` / `JobLaborLine` | ShipmentLine / time |
| `Invoice` + `InvoiceLine` | Same |
| `Membership` / `ServiceAgreement` | (new — recurring) |
| `Customer` (FSM ↔ QB) | Same |

**Architecture:** Header-only “job shipped” is wrong. Need **completion status + billable lines (labor, materials, CO)** and hold reasons (photos, customer approval, permit).

---

## Competitive reality (be honest)

| Alternative | Why buyer might stick |
|---|---|
| ServiceTitan / Jobber billing reports | “We already see open invoices in ST” |
| Office manager checklist / Excel | Habit; trust in person over tool |
| Bookkeeper month-end | Catches some leakage after cash pain |

**Win when:** Work closes in FSM and invoices live in **QuickBooks** (or ST invoice sync is incomplete / delayed); owner can name dollars left on closed jobs last month.

**Weaker when:** All-in-one FSM billing with no QB split and office already invoices same-day on close.

---

## Discovery questions (trades-specific)

**Full call script:** [discovery-interview-trades.md](../../cold-call/discovery-interview-trades.md) — use that for booked discovery.

Short list when `cluster = C` or `D` (also embedded in the cold-call script):

1. Walk me through a job from **tech checkout → invoice in QuickBooks** — who owns each step?  
2. How many days from **closed / completed** to invoice on a normal residential job?  
3. Where do **change orders** live — FSM, Excel, text to office? How often do they miss the bill?  
4. Do **parts from the truck** always land on the invoice? How do you check?  
5. Flat-rate vs T&M — where does **labor** get underbilled?  
6. ServiceTitan / Jobber / other — and is **QB** still the invoice system of record?  
7. Membership / maintenance plans — any **missed billings or renewals**?  
8. Would you pay for a queue that said **“these completed jobs have no QB invoice”** every morning?

**Segment tag:** `hvac` | `plumbing` | `electrical` | `roofing` | `remodel_gc` | `commercial_fsm` | `landscaping_adj`

**Go/no-go for trades Launch Signal:** ≥50% describe **completed-not-invoiced** or **CO / parts leakage**; FSM export or API can yield job status + invoice link + line dollars.

---

## ICP positioning summary

| If beachhead is… | Lead problem | Lead follow-on | Avoid as hero |
|---|---|---|---|
| Job shop mfg | Unbilled ship | Late jobs | Change-order depth day 1 |
| Product mfg / dist | Unbilled ship / line | Backorder / OTIF | Job/WO language |
| **Trades / construction** | **Unbilled completed WO** | **CO + materials/labor completeness** | Dispatch, utilization, leads |
| Retail multi-channel | Cash recon | Channel inventory | Unbilled WO (unless field install arm) |

**Wave-2 message:** Same Meshflow spine as mfg/dist — *connect how work gets done to QuickBooks* — trades pack swaps **shipment** for **job complete**.

---

## Scoring caveats

- ServiceTitan-native billing shops with **tight same-day invoice** are weaker for #1 — probe QB split and CO/parts leakage anyway  
- **Ease scores assume** API or reliable export of job status, closed date, billable lines, and QB invoices — validate ST vs Jobber API coverage before committing connector  
- Change-order importance can **emotionally outrank** unbilled WO in remodel/roofing even if launch score favors #1  
- Cluster **D field service** shares #1–2; #3–5 soften if few change orders / materials  
- Scores are pre-discovery; re-rank after 8–10 tagged calls  

---

## Related

- [gtm-industry-system-matrix.md](../gtm-industry-system-matrix.md) — cluster C+D as wave 2
- [industry-system-clusters.md](../industry-system-clusters.md) — ServiceTitan / Jobber playbooks
- [job-shop-manufacturing-problem-opportunity-ranking.md](./job-shop-manufacturing-problem-opportunity-ranking.md)
- [retail-problem-opportunity-ranking.md](./retail-problem-opportunity-ranking.md)

---

## Revision log

| Date | Change |
|---|---|
| 2026-07-20 | Initial trades/construction ranking; hero = completed WO not invoiced; CO + materials/labor as #3–5 |
| 2026-07-20 | Link full discovery script in cold-call/discovery-interview-trades.md |
