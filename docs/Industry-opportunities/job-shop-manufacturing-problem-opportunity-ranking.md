# Job-Shop Manufacturing — Problem Opportunity Ranking (Pre-Discovery)

**Scope:** Discrete / **job-shop** manufacturers ($5M–$30M) — make-to-order, custom or high-mix low-volume work, job/work-order centric.

**Companion:** For broader small manufacturing (product / repetitive / process-like plants such as [PDM US, LLC](https://pdmus.com/)-style makers), see [smaller-manufacturing-problem-opportunity-ranking.md](./smaller-manufacturing-problem-opportunity-ranking.md).

**Purpose:** Pre-research ranking of problems Meshflow could productize as **single-problem solutions** — before discovery calls. Launch with one Signal; expand as the product matures.

**Status:** Hypothesis ranking — validate with 8–10 interviews. Scores are judgment calls grounded in industry literature + ICP assumptions (job-shop / discrete; adjacent: contractors, distribution, field service).

**Sources informing this ranking:**
- Industry reporting on shipped-not-invoiced revenue leakage and dispatch-to-invoice delays
- Job-shop ops literature (OTD, quoting, costing variability)
- Prior ICP research in this repo (ERP + QuickBooks + Excel fragmentation)
- Meshflow architecture constraints (cross-system joins, confidence gates, no invented dollars)

---

## How to read the scores

| Score | **Business importance** (1–5) | **Ease of implementation** (1–5) |
|---|---|---|
| 5 | Acute cash/EBITDA; owner will pay quickly | Few systems; clean fields; clear definition; days to first value |
| 4 | Recurring weekly pain; clear ROI story | Mostly standard extracts; light meshflow |
| 3 | Real but chronic; competes with other priorities | Moderate hygiene risk or definition work |
| 2 | Nice-to-have or niche | Heavy data discipline or custom semantics |
| 1 | Rarely budget-worthy alone | MES/real-time, heavy PS, or unreliable fields |

**Meshflow novelty (1–5):** How much the problem *requires* cross-system reconciliation (vs a single ERP report). Higher = better Signal for Meshflow as a differentiated product.

**Launch score** = `(Importance × 2) + Ease + Meshflow novelty`  
(Weights importance heaviest — you need pain people feel; then ease; then differentiation.)

---

## Ranked problem catalog

### Tier A — Strong launch candidates

| Rank | Problem | Imp. | Ease | Meshflow | Launch | Why it ranks here |
|---|---|---|---|---|---|---|
| **1** | **Shipped / completed but not invoiced** | 5 | 4 | 5 | **18** | Direct cash stuck; classic ops↔finance gap; ERP ship + QB invoice join is Meshflow's hero proof; industry cases cite 10–15%+ leakage and large $ stuck between dispatch and invoice |
| **2** | **Past-due AR — ranked collections queue** | 5 | 5 | 2 | **17** | Cash urgency max; easiest data (mostly QB); **weak Meshflow novelty** — Intuit and bookkeepers already compete; better as *add-on* to #1 than solo launch |
| **3** | **Late / at-risk jobs (delivery exceptions)** | 5 | 3 | 2 | **15** | Extremely felt on the floor; mostly ERP-only; date hygiene and definition fights ("late" vs whose date) lower ease; weak cross-system story unless tied to customer AR risk |

### Tier B — Strong follow-on products (same meshflow spine)

| Rank | Problem | Imp. | Ease | Meshflow | Launch | Why |
|---|---|---|---|---|---|---|
| **4** | **Partial ship / under-invoiced orders** | 4 | 3 | 5 | **16** | Same family as #1; harder (line-level qty matching); natural expansion of shipped-not-invoiced |
| **5** | **Jobs closed / shipped with open WIP or stale status** | 4 | 4 | 4 | **16** | Status lies in ERP; effective-status inference is core Meshflow; enables cleaner late + unbilled logic |
| **6** | **Customer identity chaos (ERP ↔ QB mismatch)** | 3 | 4 | 5 | **15** | Infrastructure problem — rarely bought alone; **enables** #1, #7, #8; sell outcomes not matching |
| **7** | **Unprofitable jobs / customers (closed-job margin)** | 5 | 2 | 3 | **15** | Highest EBITDA story long-term; costing definitions and incomplete job cost kill ease; needs Option B discipline |
| **8** | **Quote vs actual variance** | 4 | 2 | 3 | **13** | Estimator gold; requires quote + actual cost completeness; later Signal |

### Tier C — Valuable but harder / less Meshflow-native

| Rank | Problem | Imp. | Ease | Meshflow | Launch | Why |
|---|---|---|---|---|---|---|
| **9** | **Material shortages blocking open jobs** | 4 | 2 | 3 | **13** | Ops cares deeply; MRP exception data ugly or Excel-only; high false positives |
| **10** | **Slow / obsolete inventory** | 3 | 4 | 1 | **11** | Mostly single-system ERP; ERP already reports this; low Meshflow story |
| **11** | **Supplier / PO late receipts** | 3 | 3 | 2 | **11** | Useful; secondary to customer delivery; medium data quality |
| **12** | **Capacity vs backlog overload** | 4 | 1 | 1 | **10** | Critical business pain; routing/capacity data often fiction — not a Meshflow v1 play |
| **13** | **Labor hours vs estimate** | 3 | 2 | 2 | **10** | Needs timesheet discipline; often Excel; definition fights |
| **14** | **Cash application / unmatched payments** | 4 | 2 | 4 | **14** | High finance pain; bank feed + AR matching is a different product (bill.com/Lockstep territory) |
| **15** | **Change-order / scope leakage (contractors)** | 4 | 2 | 4 | **14** | Adjacent vertical Signal; strong $; harder entity model than job-shop ship→invoice |

---

## Scatter view (importance vs ease)

```
Importance ↑
5 │  [#3 Late jobs]     [#2 Past-due AR]     ★ [#1 Unbilled ship]
  │  [#7 Margin]                             [#5 Stale status]
4 │  [#9 Shortages]     [#4 Partial invoice] [#8 Quote variance]
  │  [#12 Capacity]     [#15 Change orders]  [#14 Cash app]
3 │  [#6 Customer match][#11 Supplier late]  [#10 Dead inventory]
  │  [#13 Labor vs est]
2 │
1 └──────────────────────────────────────────────────────────→ Ease
         Hard (1)              Medium (3)              Easy (5)
```

**Sweet spot for Meshflow launch (job shop):** high importance + medium-high ease + **high Meshflow novelty** → **#1 Unbilled shipments**.

---

## Deep dive — top candidates

### 1. Shipped / completed but not invoiced ★ Recommended launch (job shop)

| Dimension | Assessment |
|---|---|
| **Buyer pain** | Cash trapped; month-end scramble; "we shipped free product"; owner/controller feel it in payroll weeks |
| **Who feels it** | Controller (daily), owner (cash), ops (less — they already shipped) |
| **Systems** | ERP shipments/jobs + accounting invoices |
| **Meshflow job** | Job/ship ↔ invoice link; customer match; effective shipped status; days-since-ship ranking |
| **Definition** | Relatively crisp: shipped/complete with no (or under) linked invoice after N days |
| **ROI story** | "$X sitting unbilled right now" — measurable in week 1 |
| **Competition** | Some ERPs have "shipped not invoiced" *inside* ERP; weak when billing is in QuickBooks |
| **False-positive risk** | Progress billing, hold-for-docs, consignment — need hold reasons / snooze |
| **Adjacent markets** | Contractors (WIP not billed), field service (completed tickets), distribution (shipped SO lines) |

**Launch product shape:** Daily/weekly **"Bill these"** queue — ranked by $ × days since ship — with one-click provenance ("ERP ship 7/10 · no QB invoice match").

**Discovery questions:**
- How do you know something shipped but wasn't invoiced?
- Roughly how many days from ship to invoice on a normal job?
- Ever found product that left without a bill? How often?
- Is invoicing in the same system as shipping, or QuickBooks / separate?

---

### 2. Past-due AR collections queue

| Dimension | Assessment |
|---|---|
| **Pain** | Extremely high — but saturated tooling (QB reports, collectors, bookkeepers) |
| **Meshflow novelty** | Low if QB-only |
| **When to ship** | Bundle with #1: "Get cash from unbilled *and* unpaid" as a **cash cycle** SKU |
| **Risk** | Competing with free QB aging + human bookkeeper |

---

### 3. Late / at-risk jobs

| Dimension | Assessment |
|---|---|
| **Pain** | Highest *ops* emotion; customer calls; overtime |
| **Meshflow novelty** | Low — ERP report territory |
| **Ease drag** | Missing promise dates, status lies, whose date counts |
| **When to ship** | After #1 proves meshflow; use effective-status + date fallbacks Meshflow already built |
| **Risk** | Feels like "another ERP dashboard" unless packaged as morning action queue |

---

### 4–5. Partial invoice + stale job status

Natural **Phase 2** expansions of the unbilled spine — same joins, more precision.

---

### 7. Unprofitable jobs / customers

| Dimension | Assessment |
|---|---|
| **Pain** | Owner gold — "we're busy and broke" |
| **Ease drag** | Job costing incomplete; margin definition wars |
| **When to ship** | After closed-job cost quality validated in discovery; Option B |
| **Risk** | Wrong margin number = instant churn |

---

## Recommended product roadmap (problem-first)

```
Launch SKU          "Unbilled Shipments" (shipped/complete → no invoice)
       │
       ├─► + Past-due AR          = Cash Cycle pack
       ├─► + Partial / underbill  = Billing Completeness pack
       ├─► + Stale status         = Ops Truth pack (enabler)
       │
       ├─► Late jobs queue        = Delivery Exceptions (reuse dates/status)
       │
       └─► Margin outliers        = Profitability (Option B — gated on costing)
```

**Do not launch** on capacity, MES, or labor variance — high importance, wrong feasibility for Meshflow v1.

---

## Adjacent industry ports of the same Signal

Same *problem shape* (work done → not billed) travels well:

| Industry | Analog of "unbilled shipment" | Systems |
|---|---|---|
| Job-shop mfg | Shipped / complete job, no invoice | ERP + QB |
| Distribution | Shipped SO lines, no invoice | ERP/WMS + accounting |
| Specialty contractor | Completed milestones / WIP aging unbilled | Job cost + QB |
| Field service | Closed tickets / work orders unbilled | FSM + QB |
| Professional services | Hours/WIP not billed | PSA + accounting |

**Thesis (job-shop Signal):** Meshflow is a **billing completeness / cash leakage** platform that starts in job-shop manufacturing, not a general analytics suite.

---

## What to validate in discovery (priority order)

Ask every interview; tally frequency and severity (1–5):

1. Ship-to-invoice lag and any known unbilled incidents  
2. Whether shipping and invoicing live in **different systems**  
3. How they prioritize collections today  
4. Late-job visibility (and whether dates are trusted)  
5. Whether they trust job cost / know underwater customers  
6. Material shortage visibility source (ERP vs Excel)  

**Go/no-go for Launch Signal #1:** ≥50% of ICP interviews describe ship-to-invoice friction *or* admit they've found unbilled shipments — and billing is not fully automated inside one cloud ERP.

---

## Scoring caveats (be honest)

- Scores are **pre-discovery hypotheses**, not market research with n≥30  
- Importance assumes US **job-shop / discrete MTO** $5–30M  
- Ease assumes ERP export + QB is available within a week  
- "ERP has a report" does **not** kill #1 if billing is in QB — that *is* the Meshflow gap  
- AR-only products are easier but harder to differentiate — resist launching there alone  
- Product / repetitive manufacturers (catalog SKUs, MTS) may reorder this list — see companion doc  

---

## Revision log

| Date | Change |
|---|---|
| 2026-07-17 | Initial pre-discovery problem ranking; recommend Unbilled Shipments as Launch Signal |
| 2026-07-17 | Renamed from `problem-opportunity-ranking.md`; scoped explicitly to job-shop; linked generalized companion |
