# GTM — Product Manufacturing & Small Distribution

**Scope:** Two primary clusters from [gtm-industry-system-matrix.md](./gtm-industry-system-matrix.md):

- **B. Product / repetitive manufacturing** — catalog SKUs, MTS/ATO, often selling through distributors (e.g. insulated linesets, components, packaged goods)
- **A. Wholesale / small distribution** — buy-and-resell or light value-add; high line count, partial ships, backorders

**Stack assumption (v1 playbook):** **NetSuite** (or BC / Fishbowl as alternate playbook) + **QuickBooks** + **Excel**

**Product spine:** Invisible meshflow connects fulfillment/ops events to financial records → **ranked exception queues** (not dashboards).

**Status:** Pre-discovery — validate with segmented interviews before locking SKU copy.

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

---

## Universal buyer message

**Headline (both segments):**  
> *Stop leaving money on the dock — we connect how you fulfill orders to QuickBooks and show what you haven't billed.*

**Segment sub-lines:**

| Segment | Sub-line |
|---|---|
| Product mfg | *See unbilled shipments, invoice lag, and where catalog margin is leaking.* |
| Small distributor | *See unbilled and partial lines, backorders you can't fill, and cash stuck after ship.* |

**Never lead with:** data platform, lakehouse, dashboards, job-shop job costing, analytics AI chat.

---

## GTM solution catalog (SKUs)

Each SKU is a **productized exception queue** with daily/weekly delivery (email + simple detail view). All require cross-system meshflow for full value.

### Launch SKU

#### SKU-1: Unbilled Fulfillment

| | |
|---|---|
| **Customer promise** | Nothing ships or completes without you seeing whether it's billed |
| **Queue contains** | Fulfillment events (ship / complete / pick confirmed) with no matching QB invoice above confidence threshold — ranked by **$ × days since event** |
| **Primary systems** | NetSuite shipments / item fulfillment / SO status + QBO invoices |
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
| **Queue contains** | SKU-1 (and optionally SKU-2) **plus** past-due AR from QuickBooks, ranked by $ × age |
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

**Primary systems:** NetSuite SO / inventory / backorder reports + QB (for customer $ context)

**Excel role:** Manual backorder log merge when ERP exceptions are ugly

---

#### PACK-M: Product Manufacturing

| SKU | Name | Queue |
|---|---|---|
| M1 | **Excess & slow FG / raw** | SKUs with high on-hand $ and low movement (ERP inventory) |
| M2 | **SKU / customer margin shortlist** | Bottom quartile margin — ERP cost + QB revenue via matched customer |
| M3 | **Price vs cost mismatch** | Catalog/sheet price (Excel or ERP) vs current cost — loss risk on quotes/orders |

**Gate M2/M3 on discovery:** job/item costing trusted; controller confirms cost source.

---

## Pain → connected solution map

### Tier 1 — Only works when systems connect

| Pain (their words) | Disconnected reality | Connected outcome |
|---|---|---|
| "We shipped it but never got paid" | Ship in NetSuite; no invoice in QB | SKU-1 queue item with $ and days |
| "Finance finds out at month-end" | No daily join | Daily briefing by 6am |
| "Customer says we short-shipped" | Partial ship not matched to invoice | SKU-2 line exceptions |
| "Same customer, different name in QB" | Broken rollups | Entity match → one customer truth |
| "We don't know how much cash is stuck" | Ship $ in ERP, AR in QB | Single "$ unbilled + $ past due" |
| "Distributor portal shows shipped, books don't" | EDI/portal vs QB | Ship confirm ↔ invoice gap (when data available) |

### Tier 2 — Stronger with connection; partial value in one system

| Pain | Connection adds |
|---|---|
| Backorders killing OTIF (dist) | Backorder $ + customer AR risk + unbilled on same account |
| OTIF looks fine but cash is late | Ship-to-invoice lag by customer (PACK-D3) |
| Busy but margin feels wrong | SKU/customer margin needs ERP cost + QB revenue + Excel price |
| Too much inventory cash (mfg) | FG $ in ERP + billed $ in QB → "shipped but not billed" vs true excess |
| Pricing sheet out of date (mfg) | Excel price + ERP cost + actual invoice price |

### Tier 3 — Mostly single-system (defer or light touch)

| Pain | Notes |
|---|---|
| Supplier OTD | ERP PO — weak cross-system story unless tying to customer backorder |
| Pick accuracy | WMS territory |
| Production OEE / scrap | MES — out of v1 scope |
| Dead stock report | ERP native — sell as PACK-M1 exception *ranking*, not raw report |

---

## NetSuite + QuickBooks + Excel playbook

### NetSuite extracts (typical reports / records)

| Object | Use | SKU |
|---|---|---|
| Sales orders (open + recent closed) | Backlog, backorders | PACK-D |
| Item fulfillments / shipments | Ship date, qty, $ | SKU-1, SKU-2 |
| Invoice records (if NS billing used) | Reconcile vs QB — know which system bills | Discovery |
| Inventory snapshot | On-hand, last movement | PACK-M1 |
| Item cost / standard cost | Margin | PACK-M2 |
| Customer master | Match to QB | All |

**Discovery critical question:** Do they invoice in **NetSuite**, **QuickBooks**, or **both**? Playbook assumes **fulfillment in NS, AR/invoicing in QB** (maximum meshflow value). If single system bills and syncs cleanly, Signal is weaker.

### QuickBooks extracts

| Object | Use |
|---|---|
| Customers | Entity match |
| Invoices + lines | Link to fulfillments |
| AR aging | SKU-3 |
| Payments | Optional cash application later |

### Excel templates (generic file ingest)

| Template | Purpose |
|---|---|
| `hold-no-bill.csv` | Job/SO/customer on billing hold — suppress false positives |
| `customer-pricing.csv` | PACK-M3 price list |
| `allocation-priority.csv` | PACK-D ship priority (optional) |
| `commodity-cost.csv` | PACK-M3 raw material override (mfg) |

---

## Packaging & pricing (hypothesis)

| Offer | Includes | Notes |
|---|---|---|
| **Pilot** | SKU-1 only, 2–4 weeks, one playbook | Prove $ unbilled |
| **Core** | SKU-1 + SKU-3 | Cash Cycle |
| **Complete billing** | SKU-1 + SKU-2 + SKU-3 | Dist often wants SKU-2 early |
| **+ Distribution pack** | PACK-D | After core live |
| **+ Manufacturing pack** | PACK-M | After core live; margin SKUs gated |

Price on **outcome + ongoing queue**, not seats or dashboards. Align with [product-pillars.md](../product-pillars.md) pillar 10.

---

## Discovery workshop script

**Duration:** 45–60 min  
**Attendees:** Owner or GM + controller (+ ops/warehouse mgr for dist; plant/ops for mfg)  
**Output:** Segment tag, fit score, systems map, pilot scope

### Before the call

- [ ] Confirm NetSuite (or BC/Fishbowl) + QuickBooks + any known Excel rituals
- [ ] Website / LinkedIn — catalog mfg vs wholesale dist
- [ ] Open [gtm-industry-system-matrix.md](./gtm-industry-system-matrix.md) segmentation fields

---

### 1. Opening (3 min)

> Thanks for the time. I want to understand how orders move from fulfillment to getting paid — what's in NetSuite, what's in QuickBooks, and where the team loses time or cash. No wrong answers; I'm not auditing you.

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

5. **Order and inventory system?** NetSuite edition? Cloud?
6. **Where do invoices and AR live?** QuickBooks Online or Desktop? Same person owns both systems?
7. **Where does shipping get recorded?** NetSuite fulfillment, warehouse module, something else?
8. **Critical Excel or Sheets** — pricing, allocations, backorders, "do not ship" lists?
9. **Do you invoice in NetSuite, QuickBooks, or both?** Any sync tool between them?

**Capture:** NS version, QB version, invoice system of record, Excel file names, sync middleware if any

---

### 4. Billing & cash pain (12 min) — *core Signal validation*

10. **When something ships, how do you know it was invoiced in QuickBooks?** Manual check, report, or "we find out later"?
11. **Typical days from ship to invoice** — best case and worst case?
12. **Ever shipped product that wasn't billed, or billed late?** How did you find out? Rough frequency?
13. **Partial shipments** — common? How do you match partial ship to partial invoice?
14. **Month-end** — does anyone run "shipped not invoiced" or equivalent? How long does it take?
15. **Past-due AR** — where do you look today? How do you prioritize collections?

**Probe:** Dollar impact — "If I waved a wand, what's stuck unbilled right now — thousands, tens of thousands, more?"

**Capture:** Ship-to-invoice days, partial ship y/n, unbilled incidents, AR process, pain 1–5

---

### 5. Segment-specific pain (10 min)

**If distribution — ask:**

16. **Backorders** — how visible? ERP report, Excel, daily stand-up?
17. **Fill rate / OTIF** — do customers score you? What's your biggest miss reason — stock, partial, late PO?
18. **Top customers** — concentration? Any account where billing or delivery is always messy?

**If product mfg — ask:**

16. **Finished goods / raw inventory** — too much cash tied up? How do you spot slow movers?
17. **Cost changes** (material, copper, etc.) — how fast do selling prices update vs cost?
18. **Distributor OTIF** — penalties or lost business from late or incomplete ship?

**Capture:** Top 3 ops exceptions they check weekly; inventory/margin pain 1–5

---

### 6. Data access & fit (5 min)

19. **Could you get a NetSuite export and QuickBooks access to a pilot partner within a week?** Who approves?
20. **Refresh need** — is yesterday's data good enough, or do you need same-day?
21. **What would make a 2-week pilot an obvious success?** What would make it a waste?

---

### 7. Close (2 min)

> Based on what you shared, the highest-value starting point is usually a **daily list of what shipped but isn't in QuickBooks** — ranked by dollars. Does that match your world, or is something else more urgent?

**Next step:** Data source assessment + pilot proposal (SKU-1 scope)

---

## Fit scorecard (internal)

Score **1 = yes / 0 = no**. **≥8 = strong pilot fit**, **6–7 = fit with gaps**, **≤5 = defer**.

| # | Criterion |
|---|---|
| 1 | NetSuite (or BC/Fishbowl) + QuickBooks both in use |
| 2 | Fulfillment in ops system; invoicing primarily in QuickBooks |
| 3 | Ship-to-invoice lag ≥3 days OR known unbilled incidents |
| 4 | Partial shipments occur (dist) OR multi-line SO common (both) |
| 5 | Controller or owner will own pilot and review queue weekly |
| 6 | Can grant exports/API access within 10 business days |
| 7 | Billing/cash pain self-rated ≥3/5 |
| 8 | Revenue $5M–$50M band (adjust as you learn) |
| 9 | Not single cloud ERP with trusted built-in billing + AR only in same system |
| 10 | Accepts daily batch (not real-time shop floor) |

**Red flags:** Invoice and ship both in NetSuite with auto-sync to QB and no gaps; no access path; "we're fine at month-end"; air-gap / no external data.

---

## Pilot scope (SKU-1 standard)

| Item | Included |
|---|---|
| Systems | NetSuite + QBO (+ one Excel template if needed) |
| Duration | 2–4 weeks from first successful extract |
| Deliverable | Daily unbilled fulfillment queue + weekly $ summary |
| Success criteria | Client confirms ≥80% of top-10 queue items; total $ directionally correct |
| Out of scope | SKU-2 line matching, PACK-D/M, custom margin logic, write-back to ERP/QB |

---

## Competitive positioning (internal)

| They say | You say |
|---|---|
| "NetSuite has reports" | "Does NS show what's **not in QuickBooks** yet? That's the cash gap." |
| "Our bookkeeper handles it" | "We give them a ranked list every morning — not month-end archaeology." |
| "We need dashboards" | "We give you a **to-do list** — what to bill and who to call." |
| "Integrate everything" | "We start with **ship → invoice** — where money actually leaks." |

---

## Roadmap tie-in

```
Week 0–4   Discovery (this script) — tag product_mfg vs distribution
Week 1–6   Pilot SKU-1 — NetSuite + QBO + Excel holds
Week 6–12  Core SKU-1 + SKU-3 (Cash Cycle)
Dist path  Add SKU-2 → PACK-D (backorder / OTIF)
Mfg path   Add SKU-2 → PACK-M (inventory / margin, gated)
```

Technical spine: [reconciliation-engine.md](./reconciliation-engine.md)  
Industry context: [gtm-industry-system-matrix.md](./gtm-industry-system-matrix.md)

---

## Revision log

| Date | Change |
|---|---|
| 2026-07-18 | Initial GTM doc — SKUs, pain map, NetSuite+QB+Excel discovery script |
