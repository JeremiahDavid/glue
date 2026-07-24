# GTM — Product Manufacturing & Small Distribution

**Scope:** Two primary clusters from [gtm-industry-system-matrix.md](./gtm-industry-system-matrix.md):

- **B. Product / repetitive manufacturing** — catalog SKUs, MTS/ATO, often selling through distributors (e.g. insulated linesets, components, packaged goods)
- **A. Wholesale / small distribution** — buy-and-resell or light value-add; high line count, partial ships, backorders

**Phase 1 system decision:** Open primarily between **Business Central cross-module** and **NetSuite cross-module**. Fishbowl/Cin7 remain validation-only because their native QBO/Xero—and for Cin7, commerce—integrations cover much of the original seam. Build one family after segmented discovery and a committed design partner.

**Product spine:** Invisible meshflow connects fulfillment/ops events to financial records → **ranked exception queues** (not dashboards).

**Status:** Pre-discovery — A+B is the provisional ICP; system prevalence, recurring pain, and the first implementation family remain unvalidated.

---

## Who you're selling to

| Role | Product mfg | Small distributor |
|---|---|---|
| **Economic buyer** | Owner, GM, controller | Owner, GM, controller |
| **Daily user** | Controller (billing), ops/plant mgr (ship) | Controller, warehouse/ops mgr, inside sales |
| **Champion** | Controller tired of month-end invoice hunts | Ops or AR lead tired of backorder fire drills |

**Company profile (working hypothesis):**

| Attribute | Product mfg | Small distributor |
|---|---|---|
| Revenue | $5M–$50M | $5M–$50M |
| Employees | 30–200 | 20–150 |
| Fulfillment | SO ship, FG, sometimes production complete | Pick/pack/ship, partials common |
| Customers | Distributors, OEMs, sometimes direct | B2B accounts, repeat orders |
| Excel | Pricing, allocations, commodity cost | Customer pricing, backorder logs, allocations |

Do not use the current $5M–$50M hypothesis to pre-filter system discovery. Include adjacent upper-band A+B companies so the research can reveal whether BC/NetSuite prevalence and pilot economics improve with company size.

---

## Universal buyer message

**Headline (both segments):**  
> *Stop leaving money on the dock — we connect orders, fulfillment, billing, and cash and show what needs action.*

**Segment sub-lines:**

| Segment | Sub-line |
|---|---|
| Product mfg | *See unbilled shipments, invoice lag, and where catalog margin is leaking.* |
| Small distributor | *See unbilled and partial lines, backorders you can't fill, and cash stuck after ship.* |

**Never lead with:** data platform, lakehouse, dashboards, job-shop job costing, analytics AI chat.

---

## GTM solution catalog (SKUs)

Each SKU is a **productized exception queue** with daily/weekly delivery (email + simple detail view). Value may come from cross-system reconciliation or from cross-module facts that the full ERP does not make operational.

### Launch SKU

#### SKU-1: Unbilled Fulfillment

| | |
|---|---|
| **Customer promise** | Nothing ships or completes without you seeing whether it's billed |
| **Queue contains** | Fulfillment events (ship / complete / pick confirmed) with no matching invoice above confidence threshold—cross-system or cross-module—ranked by **$ × days since event** |
| **Primary systems** | Split stack: Fishbowl/Cin7 shipments + QBO invoices. Full ERP: NetSuite/BC order, fulfillment, and invoice modules. |
| **Excel role** | Optional hold list (do-not-bill, consignment, pending QC) to reduce false positives |
| **ROI metric** | Total $ unbilled; count > N days; trend week over week |
| **Mfg emphasis** | FG shipped to distributor not invoiced; production complete not closed out financially |
| **Dist emphasis** | Same — often higher line volume and partial-ship complexity |

**Acceptance (trial):** Client agrees top 5 queue items are real; total $ within reasonable range of their gut estimate.

---

### Expansion SKUs (same spine)

#### SKU-2: Billing Completeness (partial / under-invoiced)

| | |
|---|---|
| **Customer promise** | Catch short-ships and under-billed order lines before customer dispute |
| **Queue contains** | SO lines where qty shipped ≠ qty invoiced, or header ship $ ≠ invoice $ |
| **Meshflow dependency** | Line-level ship ↔ invoice link; higher than SKU-1 complexity |
| **Dist emphasis** | **Primary follow-on for distributors** |
| **Mfg emphasis** | Multi-SKU orders, mixed partials to distributors |

---

#### SKU-3: Cash Cycle Briefing

| | |
|---|---|
| **Customer promise** | One morning view: bill these + collect these |
| **Queue contains** | SKU-1 (and optionally SKU-2) **plus** past-due AR from the accounting system of record, ranked by $ × age |
| **Meshflow novelty** | Moderate on AR alone — bundle only; don't sell AR-only as Signal |
| **Cross-system bonus** | Flag past-due accounts with **open unbilled ship** (same matched customer) |

---

### Segment packs (after spine proven)

#### PACK-D: Distribution Operations

| SKU | Name | Queue |
|---|---|---|
| D1 | **Backorder exceptions** | Open SO lines backordered — by customer, SKU, $, age |
| D2 | **Fill-rate / OTIF risk** | Orders at risk of missing promise date; stockout-driven misses |
| D3 | **Ship-to-invoice lag** | Customers or reps with chronic billing delay after ship |

**Primary systems:** Fishbowl/Cin7 + QB, or NetSuite/BC cross-module order, inventory, fulfillment, invoice, and AR records.

**Excel role:** Manual backorder log merge when ERP exceptions are ugly

---

#### PACK-M: Product Manufacturing

| SKU | Name | Queue |
|---|---|---|
| M1 | **Excess & slow FG / raw** | SKUs with high on-hand $ and low movement (ERP inventory) |
| M2 | **SKU / customer margin shortlist** | Bottom quartile margin—ERP cost + revenue from the accounting system of record |
| M3 | **Price vs cost mismatch** | Catalog/sheet price (Excel or ERP) vs current cost — loss risk on quotes/orders |

**Gate M2/M3 on discovery:** item costing is trusted; controller confirms cost and revenue sources.

---

## Pain → connected solution map

### Tier 1 — Requires connected facts

| Pain (their words) | Disconnected reality | Connected outcome |
|---|---|---|
| "We shipped it but never got paid" | Native Fishbowl/Cin7 export failed, waited, duplicated, or mismatched—or full-ERP modules disagree | Queue item with $ and days, only if native controls miss it |
| "Finance finds out at month-end" | No daily join | Daily briefing by 6am |
| "Customer says we short-shipped" | Partial ship not matched to invoice | SKU-2 line exceptions |
| "Same customer, different name in QB" | Broken rollups | Entity match → one customer truth |
| "We don't know how much cash is stuck" | Ship $ in ERP, AR in QB | Single "$ unbilled + $ past due" |
| "Distributor portal shows shipped, books don't" | EDI/portal vs QB | Ship confirm ↔ invoice gap (when data available) |
| "The ERP has the data, but no one trusts the report" | Orders, fulfillments, invoices, credits, and custom fields cross module boundaries | One defined operational state + ranked exceptions + provenance |

### Tier 2 — Stronger with connection; partial value in one system

| Pain | Connection adds |
|---|---|
| Backorders killing OTIF (dist) | Backorder $ + customer AR risk + unbilled on same account |
| OTIF looks fine but cash is late | Ship-to-invoice lag by customer (PACK-D3) |
| Busy but margin feels wrong | SKU/customer margin needs trusted cost + accounting revenue + Excel price |
| Too much inventory cash (mfg) | FG $, demand, fulfillment, and billed revenue distinguish true excess from timing gaps |
| Pricing sheet out of date (mfg) | Excel price + ERP cost + actual invoice price |

### Tier 3 — Mostly single-system (defer or light touch)

| Pain | Notes |
|---|---|
| Supplier OTD | ERP PO — weak cross-system story unless tying to customer backorder |
| Pick accuracy | WMS territory |
| Production OEE / scrap | MES — out of v1 scope |
| Dead stock report | ERP native — sell as PACK-M1 exception *ranking*, not raw report |

---

## Candidate system-family playbooks

### Split stack: Fishbowl / Cin7 + QuickBooks + Excel

**Native-integration gate:** Fishbowl already exports fulfilled orders, invoices/bills, COGS, inventory adjustments, and GL entries to QBO. Cin7 connects QBO/Xero plus channels such as Shopify and includes sync/error dashboards. Meshflow must not sell basic connectivity or presume `SIG-BILL-01`.

Proceed only when discovery measures a recurring gap such as:

- Failed, waiting, duplicated, or incorrectly completed syncs
- Invoice, payment, credit, tax, COGS, or inventory-account discrepancies
- Shopify → Cin7 → accounting reconciliation that native tools do not resolve
- Material reconciliation hours and dollar exposure
- An operational exception queue absent from Fishbowl/Cin7 reporting

#### Ops extracts (typical reports / records)

| Object | Use | SKU |
|---|---|---|
| Sales orders (open + recent closed) | Backlog, backorders | PACK-D |
| Shipments / fulfillments | Ship date, qty, $ | SKU-1, SKU-2 |
| Inventory snapshot | On-hand, last movement | PACK-M1 |
| Item cost / standard cost | Margin | PACK-M2 |
| Customer master | Match to QB | All |

**Discovery critical question:** If they use Fishbowl/Cin7 + accounting, ask what the native integration already syncs, how often it fails, how failures are surfaced, weekly reconciliation effort, and dollar impact. If no material gap remains, decline this playbook. If they run **NetSuite or BC as books**, use `MESH-NS-INTRA` / `MESH-BC-INTRA`.

#### QuickBooks extracts

| Object | Use |
|---|---|
| Customers | Entity match |
| Invoices + lines | Link to fulfillments |
| AR aging | SKU-3 |
| Payments | Optional cash application later |

#### Excel templates (generic file ingest)

| Template | Purpose |
|---|---|
| `hold-no-bill.csv` | Job/SO/customer on billing hold — suppress false positives |
| `customer-pricing.csv` | PACK-M3 price list |
| `allocation-priority.csv` | PACK-D ship priority (optional) |
| `commodity-cost.csv` | PACK-M3 raw material override (mfg) |

---

### Full ERP: NetSuite or Business Central

When accounting lives in NetSuite or Business Central, ship ↔ invoice is often **in-system**, but the reporting and action problem can still span transaction types, modules, subsidiaries, custom fields, historical state, and Excel/satellite workflows.

The product proposition is **packaged operational control**, not generic report building:

- Canonical order → fulfillment → invoice → payment state
- Partial fulfillment / billing mismatches
- Backorder and OTIF risk tied to dollars and customers
- Inventory and margin exceptions
- Historical snapshots, ranked ownership, and resolution tracking

Full ERP is a Phase 1 candidate when discovery finds a recurring, dollarized Signal that native reporting does not operationalize. Choose **NetSuite or BC**, not both initially. Dual-run NS/BC + QB remains exceptional.

## Packaging & pricing (hypothesis)

| Offer | Includes | Notes |
|---|---|---|
| **Pilot** | One discovery-selected Signal, 2–4 weeks, one playbook | Prove a recurring dollarized queue |
| **Core** | Launch Signal + one adjacent queue | Expand only after pilot acceptance |
| **Complete billing** | SKU-1 + SKU-2 + SKU-3 | Dist often wants SKU-2 early |
| **+ Distribution pack** | PACK-D | After core live |
| **+ Manufacturing pack** | PACK-M | After core live; margin SKUs gated |

Price on **outcome + ongoing queue**, not seats or dashboards.

---

## Discovery workshop script

**Duration:** 45–60 min  
**Attendees:** Owner or GM + controller (+ ops/warehouse mgr for dist; plant/ops for mfg)  
**Output:** Segment tag, fit score, systems map, pilot scope

### Before the call

- [ ] Confirm accounting + ops path: Fishbowl/Cin7 + QB, BC, NetSuite, or other; note critical Excel/satellite workflows
- [ ] Website / LinkedIn — catalog mfg vs wholesale dist
- [ ] Open [gtm-industry-system-matrix.md](./gtm-industry-system-matrix.md) segmentation fields

---

### 1. Opening (3 min)

> Thanks for the time. I want to understand how orders move from fulfillment to getting paid—what systems and modules are involved, what still lives in spreadsheets, and where the team loses time or cash. No wrong answers; I'm not auditing you.

---

### 2. Segment & business model (8 min)

1. **What do you sell** — catalog products, wholesale lines, or custom make-to-order?
2. **Who buys** — distributors, contractors, OEMs, direct accounts?
3. **Rough scale** — revenue band, employees, locations?
4. **Make vs buy** — do you stock finished goods, drop-ship, or both?

**Tag:** `product_mfg` | `distribution` | `hybrid`

**Capture:** Primary mode (MTS / wholesale / hybrid), customer type, headcount

---

### 3. Systems map (10 min)

> Walk me through where data lives from order → ship → invoice → payment.

5. **Order and inventory system?** Fishbowl, Cin7, NetSuite, BC, something else?
6. **Where do invoices and AR live?** QuickBooks Online or Desktop? Or inside a full ERP?
7. **Where does shipping get recorded?** Ops system, warehouse module, something else?
8. **Critical Excel or Sheets** — pricing, allocations, backorders, "do not ship" lists?
9. **Confirm:** books in QB vs full ERP? Any sync tool between ops and accounting?
10. **If Fishbowl/Cin7:** Which native integrations are enabled? What fails or requires manual reconciliation despite their status/error dashboards?

**Capture:** Ops system, accounting system of record, Excel file names, sync middleware if any. If accounting = NS/BC → full-ERP path, not Fishbowl+QB playbook.

---

### 4. Billing & cash pain (12 min) — *core Signal validation*

11. **When something ships, how do you know it was fully invoiced?** Native report, saved query, spreadsheet, manual check, or “we find out later”?
12. **Typical days from ship to invoice** — best case and worst case?
13. **Ever shipped product that wasn't billed, or billed late?** How did you find out? Rough frequency?
14. **Partial shipments** — common? How do you match partial ship to partial invoice?
15. **Month-end** — does anyone run "shipped not invoiced" or equivalent? How long does it take?
16. **Past-due AR** — where do you look today? How do you prioritize collections?

**Probe:** Dollar impact — "If I waved a wand, what's stuck unbilled right now — thousands, tens of thousands, more?"

**Capture:** Ship-to-invoice days, partial ship y/n, unbilled incidents, AR process, pain 1–5

---

### 5. Segment-specific pain (10 min)

**If distribution — ask:**

17. **Backorders** — how visible? ERP report, Excel, daily stand-up?
18. **Fill rate / OTIF** — do customers score you? What's your biggest miss reason — stock, partial, late PO?
19. **Top customers** — concentration? Any account where billing or delivery is always messy?

**If product mfg — ask:**

17. **Finished goods / raw inventory** — too much cash tied up? How do you spot slow movers?
18. **Cost changes** (material, copper, etc.) — how fast do selling prices update vs cost?
19. **Distributor OTIF** — penalties or lost business from late or incomplete ship?

**Capture:** Top 3 ops exceptions they check weekly; inventory/margin pain 1–5

---

### 6. Data access & fit (5 min)

20. **Could you get API access or standard exports for the relevant system modules within a week?** Who approves?
21. **Refresh need** — is yesterday's data good enough, or do you need same-day?
22. **What would make a 2-week pilot an obvious success?** What would make it a waste?

---

### 7. Close (2 min)

> Based on what you shared, the highest-value starting point may be a **daily list of fulfillment, billing, inventory, or margin exceptions** ranked by dollars. Which recurring queue would remove the most risk or manual work?

**Next step:** Data source assessment + one-Signal pilot proposal

---

## Fit scorecard (internal)

Score **1 = yes / 0 = no**. **≥8 = strong pilot fit**, **6–7 = fit with gaps**, **≤5 = defer**.

| # | Criterion |
|---|---|
| 1 | System path is identified: split-stack QBO, BC, NetSuite, or other |
| 2 | A recurring exception requires cross-system or cross-module facts and is not already resolved by native integrations/reports |
| 3 | Known billing, fulfillment, inventory, or margin incidents have material dollar exposure |
| 4 | Partial shipments occur (dist) OR multi-line SO common (both) |
| 5 | Controller or owner will own pilot and review queue weekly |
| 6 | Can grant exports/API access within 10 business days |
| 7 | Selected billing, fulfillment, inventory, or margin pain self-rated ≥3/5 |
| 8 | Revenue and employee bands are recorded; account sits in a deliberately tested A+B segment |
| 9 | Existing native reporting does not already provide a trusted, actionable queue |
| 10 | Accepts daily batch (not real-time shop floor) |

**Red flags:** Fishbowl/Cin7 native integration already handles the workflow with low failure/reconciliation effort; request is generic custom reporting; native reporting resolves the queue; NS/BC + QB dual-run presented as standard without a migration story; no access path; “we're fine at month-end”; air-gap / no external data.

---

## Pilot scope (system family selected after discovery)

| Item | Included |
|---|---|
| Systems | One validated family: Fishbowl/Cin7 + QBO, BC cross-module, or NetSuite cross-module (+ Excel/satellite only if material) |
| Duration | 2–4 weeks from first successful extract |
| Deliverable | Daily ranked queue for one selected Signal + weekly $ summary |
| Success criteria | Client confirms ≥80% of top-10 queue items; dollar exposure directionally correct |
| Out of scope | Additional Signals, custom accounting logic, and write-back to source systems |

---

## Competitive positioning (internal)

| They say | You say |
|---|---|
| "Fishbowl/Cin7 has reports" | "If its native integration and error dashboard already make the process reliable, this is not a fit. We proceed only when a material control gap remains." |
| "NetSuite/BC has reports" | "We are not replacing native reporting; we package cross-module facts into a ranked queue with history, ownership, and dollar exposure." |
| "Our bookkeeper handles it" | "We give them a ranked list every morning — not month-end archaeology." |
| "We need dashboards" | "We give you a **to-do list** — what to bill and who to call." |
| "Integrate everything" | "We start with **ship → invoice** — where money actually leaks." |

---

## Roadmap tie-in

```
Week 0–4   Segmented discovery — tag industry, size band, accounting, ops system, and recurring Signal
Gate       Score BC vs NetSuite; admit Fishbowl/Cin7 only with measured native-integration gap
Week 1–6   Pilot the winning family and one packaged Signal
Week 6–12  Harden launch Signal; add one adjacent queue only after acceptance
Dist path  Expand into billing completeness, backorder, or OTIF
Mfg path   Expand into billing completeness, inventory, or margin (gated)
```

Technical spine: [reconciliation-engine.md](./internal-execution-scoping/reconciliation-engine.md)
Industry context: [gtm-industry-system-matrix.md](./gtm-industry-system-matrix.md)

---

## Revision log

| Date | Change |
|---|---|
| 2026-07-18 | Initial GTM doc — SKUs, pain map, NetSuite+QB+Excel discovery script |
| 2026-07-23 | Beachhead → Fishbowl/Cin7 + QB; NS/BC = full ERP later |
| 2026-07-23 | Keep A+B ICP; reopen Phase 1 family and treat BC/NetSuite cross-module operational control as first-class candidates |
| 2026-07-23 | Downgrade Fishbowl/Cin7 to validation-only because native accounting/commerce integrations erode the original wedge |
