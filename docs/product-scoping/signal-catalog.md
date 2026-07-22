# Meshflow — Signal Catalog

**Purpose:** Canonical list of **Signal nodes** — productized insight packs (one operational metric or exception type) that run on a Mesh. Each Signal has a fixed definition, inputs, output shape, and known limitations.

**Definitions (SOW):** See [sow-template-meshflow.md](../contracts/sow-template-meshflow.md) §1.1  
**Companion:** [mesh-node-catalog.md](./mesh-node-catalog.md) — Mesh nodes (`SYS-…`); [mesh-catalog.md](./mesh-catalog.md) — sample Meshes  
**Scoring sources:** Industry problem-opportunity rankings under [Industry-opportunities/](./Industry-opportunities/)

**Status:** Product catalog — SOW Section 4 may only select IDs listed here (or added via catalog revision + change order).

---

## How to read a Signal node

| Field | Meaning |
|---|---|
| **Signal ID** | Stable commercial ID (`SIG-<FAMILY>-<nn>`) |
| **Name** | Buyer-facing label |
| **Family** | Billing · Cash · Ops · Membership · Margin · Identity · Other |
| **Requires** | System **roles** and/or **System IDs** that must be in the deal Mesh |
| **Industry tags** | Clusters where the problem ranks high |
| **Meshflow strength** | High / Med / Low — needs cross-system join vs single-system report |
| **Sell posture** | Hero · Follow-on · Bundle · Enabler · Defer |
| **Output** | Default queue / view shape |

**Output shape (standard unless noted):** Ranked exception list and/or period KPI · drill IDs · definition card · optional briefing slot.

**Mesh rule:** Compose a Mesh from [mesh-node-catalog.md](./mesh-node-catalog.md) (see samples in [mesh-catalog.md](./mesh-catalog.md)). Signals care about **roles** — not a mandatory Mesh sample ID.

---

## Industry tag legend

Same as Mesh node catalog: **A** Dist · **B** Product mfg · **B-js** Job shop · **C** Trades · **D** Field svc · **E** Pro svc · **F** Retail · **G** Logistics · **H** Prop mgmt · **I** Restaurant · **J** Staffing

---

## Catalog index (all Signal nodes)

| ID | Name | Family | Sell | Meshflow | Primary industries |
|---|---|---|---|---|---|
| `SIG-BILL-01` | Closed / shipped work not invoiced | Billing | **Hero** | High | A, B, B-js, C, D, E |
| `SIG-BILL-02` | Partial / under-invoiced lines | Billing | Follow-on | High | A, B, B-js |
| `SIG-BILL-03` | Progress / milestone billing incomplete | Billing | Follow-on | High | C (remodel/GC), E |
| `SIG-LABOR-01` | Labor / hours missing on invoice | Billing | Follow-on | High | C, D, E |
| `SIG-PART-01` | Materials / parts missing on invoice | Billing | Follow-on | High | C, D |
| `SIG-CO-01` | Change orders not billed | Billing | Follow-on | High | C, B-js (contractors) |
| `SIG-WIP-01` | Unbilled WIP / hours | Billing | Hero (E) | High | E, J |
| `SIG-AR-01` | Outstanding AR | Cash | Bundle | Med–Low* | All with QB |
| `SIG-CASH-01` | Sales / POS vs QB deposits | Cash | **Hero (F)** | High | F, I |
| `SIG-CREDIT-01` | Over credit limit blocking ship | Cash | Follow-on | High | A, B |
| `SIG-BO-01` | Backorder aging ($) | Ops | Follow-on | Med | A, B |
| `SIG-OTIF-01` | OTIF / fill-rate failures | Ops | Follow-on | Med | A, B |
| `SIG-STOCK-01` | Stockouts on open demand | Ops | Follow-on | Med–High | A, B, F |
| `SIG-INV-01` | Slow / dead / excess inventory | Ops | Later | Low | A, B, F |
| `SIG-INV-02` | Multi-channel inventory mismatch | Ops | Follow-on (F) | High | F |
| `SIG-LATE-01` | Late / at-risk jobs or orders | Ops | Later | Low–Med | B-js, B, C |
| `SIG-STATUS-01` | Stale job / fulfillment status | Ops | Enabler | High | B-js, C |
| `SIG-HOLD-01` | Ready-to-bill holds | Ops | Follow-on | Med | C, D |
| `SIG-PO-01` | Inbound supplier / PO late | Ops | Later | Med | A, B |
| `SIG-EDI-01` | EDI / portal orders stuck | Ops | Later | High | A, B, F |
| `SIG-MEM-01` | Membership visit gaps | Membership | Follow-on | High | C (HVAC) |
| `SIG-MEM-02` | Membership / plan billing gaps | Membership | Follow-on | High | C |
| `SIG-MARGIN-01` | Job / customer margin outliers | Margin | Later | Med | B-js, C, E |
| `SIG-MARGIN-02` | SKU / tier / channel margin outliers | Margin | Later | Med | A, B, F |
| `SIG-MARGIN-03` | Quote / estimate vs actual | Margin | Later | Med | B-js, C |
| `SIG-MARGIN-04` | Stale COGS → false margin | Margin | Follow-on (F) | Med–High | F, B |
| `SIG-LABOR-02` | Labor % out of band | Margin | Follow-on (F) | High | F |
| `SIG-NEW-01` | New customer revenue | Other | Bundle | Med–High | All |
| `SIG-MKT-01` | Marketing spend return (thin) | Other | Sparingly | Weak | F, C |
| `SIG-CALLBACK-01` | Callback / warranty untracked | Other | Later | Med | C, D |
| `SIG-SHRINK-01` | Shrink / velocity vs on-hand drift | Other | Later | Med | F |
| `SIG-VENDOR-01` | Vendor bill vs receiving gap | Other | Later | Med | F, A |
| `SIG-CUST-01` | Customer identity chaos | Identity | **Enabler** | High | All multi-system |
| `SIG-CASHAPP-01` | Cash application / unmatched payments | Cash | Defer | High | All — crowded |
| `SIG-SCHED-01` | Schedule / capacity overload | Ops | **Defer** | Low | C, B-js — not Meshflow |
| `SIG-UTIL-01` | Tech / labor utilization % | Ops | **Defer** | Low | C, D — FSM-native |
| `SIG-LEAD-01` | Lead → booked conversion | Other | **Defer** | Low | C — CRM product |

\*AR is easy data / weak solo Meshflow novelty — sell as Cash Cycle **bundle** with a billing hero.

---

## Family: Billing completeness (spine)

### `SIG-BILL-01` — Closed / shipped work not invoiced ★ Core spine

| | |
|---|---|
| **Metric** | Fulfillment or completion events with no (or under) matching QB invoice after N days — ranked by **$ × age** |
| **Entity by role** | Ship/fulfillment (Ops ERP) · Job/WO complete (FSM) · Time/WIP close (PSA) |
| **Requires** | Ops ERP **or** FSM **or** PSA + Accounting (`SYS-QBO`/`SYS-QBD`); examples: `SYS-NETSUITE`, `SYS-BC`, `SYS-FISHBOWL`, `SYS-SERVICETITAN`, `SYS-JOBBER`, `SYS-OPTSY`, `SYS-HARVEST` |
| **Industry tags** | **A, B, B-js, C, D, E** |
| **Meshflow strength** | **High** |
| **Sell posture** | **Hero** (mfg/dist/trades/field); probe on every FSM+QB deal |
| **Inputs** | M1 completion/ship events + M2 invoices + customer match |
| **Known limits** | Progress billing, hold-for-docs, consignment, same-system auto-invoice with no gap |
| **Buyer message** | *Bill what you shipped / finished* |

---

### `SIG-BILL-02` — Partial / under-invoiced lines

| | |
|---|---|
| **Metric** | Shipped/picked qty (or billed qty) ≠ invoice line qty |
| **Requires** | Ops ERP (`SYS-NETSUITE`, `SYS-BC`, `SYS-FISHBOWL`, `SYS-CIN7`, …) + Accounting |
| **Industry tags** | **A, B, B-js** |
| **Meshflow strength** | **High** |
| **Sell posture** | Follow-on to BILL-01 (critical for distributors) |
| **Known limits** | Line-level matching harder; needs SO/shipment/invoice lines |

---

### `SIG-BILL-03` — Progress / milestone billing incomplete

| | |
|---|---|
| **Metric** | Milestones / % complete / draws reached without matching invoice |
| **Requires** | FSM or PSA + Accounting; often + `SYS-EXCEL` for milestones |
| **Industry tags** | **C** (remodel/GC/roofing), **E** |
| **Meshflow strength** | **High** |
| **Sell posture** | Follow-on — definition fights; lock assumptions in SOW §10 |

---

### `SIG-LABOR-01` — Labor / hours missing on invoice

| | |
|---|---|
| **Metric** | Billable labor/tech hours on job with no corresponding invoice lines |
| **Requires** | FSM (`SYS-SERVICETITAN`, `SYS-JOBBER`, …) or PSA + Accounting |
| **Industry tags** | **C, D, E** |
| **Meshflow strength** | **High** |
| **Sell posture** | Follow-on (T&M and flat-rate underbill) |

---

### `SIG-PART-01` — Materials / parts missing on invoice

| | |
|---|---|
| **Metric** | Parts/materials used on job (truck/PO) not on invoice |
| **Requires** | FSM + Accounting (`SYS-SERVICETITAN`, `SYS-JOBBER`, `SYS-OPTSY`, …) |
| **Industry tags** | **C, D** |
| **Meshflow strength** | **High** |
| **Sell posture** | Follow-on — often with BILL-01 |

---

### `SIG-CO-01` — Change orders not billed

| | |
|---|---|
| **Metric** | Approved change orders with no matching billable invoice content |
| **Requires** | FSM + Accounting; often + `SYS-EXCEL` for CO lists |
| **Industry tags** | **C**, adjacent **B-js** contractors |
| **Meshflow strength** | **High** |
| **Sell posture** | Follow-on — signature trades pain; often needs M3 Excel |

---

### `SIG-WIP-01` — Unbilled WIP / hours

| | |
|---|---|
| **Metric** | Unbilled time, WIP, or project hours past threshold |
| **Requires** | PSA (`SYS-HARVEST`, `SYS-BQE`, …) or Accounting + Excel templates; some Ops ERP |
| **Industry tags** | **E, J** |
| **Meshflow strength** | **High** |
| **Sell posture** | **Hero** for pro services |

---

## Family: Cash & collections

### `SIG-AR-01` — Outstanding AR

| | |
|---|---|
| **Metric** | Past-due AR ranked for collections (age × $ × optional ops context) |
| **Requires** | **Any with QuickBooks** |
| **Industry tags** | **A–J** |
| **Meshflow strength** | Med–Low alone / High with M1 context |
| **Sell posture** | **Bundle** (Cash Cycle) — do not solo-launch Meshflow on AR |

---

### `SIG-CASH-01` — Sales / POS vs QB deposits

| | |
|---|---|
| **Metric** | POS/Shopify gross vs fees/refunds/tips vs QB deposit vs bank timing exceptions |
| **Requires** | Commerce (`SYS-SHOPIFY`, `SYS-SQUARE`, `SYS-LIGHTSPEED`, `SYS-CLOVER`) + Accounting |
| **Industry tags** | **F**, some **I** |
| **Meshflow strength** | **High** |
| **Sell posture** | **Hero for retail** |

---

### `SIG-CREDIT-01` — Over credit limit blocking ship

| | |
|---|---|
| **Metric** | Open orders blocked or risky vs QB AR + ERP credit limit |
| **Requires** | Ops ERP (`SYS-NETSUITE`, `SYS-BC`, `SYS-FISHBOWL`, `SYS-CIN7`, …) + Accounting |
| **Industry tags** | **A, B** |
| **Meshflow strength** | **High** |
| **Sell posture** | Follow-on |

---

### `SIG-CASHAPP-01` — Cash application / unmatched payments

| | |
|---|---|
| **Metric** | Payments unmatched to invoices |
| **Requires** | Any with QB (+ bank) |
| **Industry tags** | Broad |
| **Meshflow strength** | High but **crowded** (bill.com / Lockstep) |
| **Sell posture** | **Defer** as Meshflow hero |

---

## Family: Operations exceptions

### `SIG-BO-01` — Backorder aging ($)

| | |
|---|---|
| **Requires** | Ops ERP (`SYS-NETSUITE`, `SYS-BC`, `SYS-FISHBOWL`, `SYS-CIN7`, …) + Accounting |
| **Industry tags** | **A**, **B** |
| **Meshflow strength** | Med (often ERP-native) |
| **Sell posture** | Follow-on — #1 *ops emotion* for distributors |

---

### `SIG-OTIF-01` — OTIF / fill-rate failures

| | |
|---|---|
| **Requires** | Ops ERP + Accounting |
| **Industry tags** | **A, B** |
| **Meshflow strength** | Med |
| **Sell posture** | Follow-on |

---

### `SIG-STOCK-01` — Stockouts on open demand

| | |
|---|---|
| **Requires** | Ops ERP + Accounting; Commerce for retail winners |
| **Industry tags** | **A, B, F** |
| **Meshflow strength** | Med–High when joining open demand ↔ on-hand |
| **Sell posture** | Follow-on |

---

### `SIG-INV-01` — Slow / dead / excess inventory

| | |
|---|---|
| **Requires** | Ops ERP or Commerce + Accounting |
| **Industry tags** | **A, B, F** |
| **Meshflow strength** | **Low** (ERP-native) |
| **Sell posture** | Later / weak Meshflow story |

---

### `SIG-INV-02` — Multi-channel inventory mismatch

| | |
|---|---|
| **Requires** | Commerce (`SYS-SHOPIFY` + store POS) + Accounting; hybrid retail |
| **Industry tags** | **F** |
| **Meshflow strength** | **High** |
| **Sell posture** | Follow-on / co-hero with CASH-01 |

---

### `SIG-LATE-01` — Late / at-risk jobs or orders

| | |
|---|---|
| **Requires** | Ops ERP (incl. legacy) or FSM + Accounting |
| **Industry tags** | **B-js**, some **B**, **C** |
| **Meshflow strength** | Low–Med |
| **Sell posture** | Later — felt pain, weak cross-system hero |

---

### `SIG-STATUS-01` — Stale job / fulfillment status

| | |
|---|---|
| **Requires** | Ops ERP or FSM + Accounting |
| **Industry tags** | **B-js, C** |
| **Meshflow strength** | High (inference) |
| **Sell posture** | Enabler for BILL-01 / LATE-01 |

---

### `SIG-HOLD-01` — Ready-to-bill holds

| | |
|---|---|
| **Metric** | Closed work blocked by photo / approval / permit / docs |
| **Requires** | FSM + Accounting (`SYS-SERVICETITAN`, `SYS-JOBBER`, `SYS-OPTSY`, …) |
| **Industry tags** | **C, D** |
| **Meshflow strength** | Med |
| **Sell posture** | Follow-on — needs snooze/hold reasons |

---

### `SIG-PO-01` — Inbound supplier / PO late

| | |
|---|---|
| **Requires** | Ops ERP + Accounting |
| **Industry tags** | **A, B** |
| **Sell posture** | Later |

---

### `SIG-EDI-01` — EDI / portal orders stuck

| | |
|---|---|
| **Requires** | ERP / retail wholesale hybrids |
| **Industry tags** | **A, B, F** |
| **Meshflow strength** | High |
| **Sell posture** | Later / segment-dependent |

---

## Family: Membership (trades)

### `SIG-MEM-01` — Membership visit gaps

| | |
|---|---|
| **Metric** | Active agreements with no visit in X days |
| **Requires** | FSM + Accounting (`SYS-SERVICETITAN`, `SYS-JOBBER`, `SYS-OPTSY`, …) |
| **Industry tags** | **C** (HVAC/plumbing) |
| **Meshflow strength** | High |
| **Sell posture** | Follow-on / pack lead for membership shops |

---

### `SIG-MEM-02` — Membership / plan billing gaps

| | |
|---|---|
| **Metric** | Missed renewals, wrong plan invoices, lapsed plans still serviced |
| **Requires** | FSM + Accounting (`SYS-SERVICETITAN`, `SYS-JOBBER`, `SYS-OPTSY`, …) |
| **Industry tags** | **C** |
| **Sell posture** | Follow-on |

---

## Family: Margin & cost

### `SIG-MARGIN-01` — Job / customer margin outliers

| | |
|---|---|
| **Requires** | FSM/ERP + QB + cost completeness |
| **Industry tags** | **B-js, C, E** |
| **Meshflow strength** | Med |
| **Sell posture** | Later — cost hygiene hard |

---

### `SIG-MARGIN-02` — SKU / tier / channel margin outliers

| | |
|---|---|
| **Requires** | Ops ERP or Commerce + Accounting |
| **Industry tags** | **A, B, F** |
| **Sell posture** | Later |

---

### `SIG-MARGIN-03` — Quote / estimate vs actual

| | |
|---|---|
| **Requires** | Ops ERP (job-centric) or FSM + Accounting |
| **Industry tags** | **B-js, C** |
| **Sell posture** | Later |

---

### `SIG-MARGIN-04` — Stale COGS → false margin

| | |
|---|---|
| **Requires** | Commerce or Ops ERP + cost sources + Accounting |
| **Industry tags** | **F, B** |
| **Sell posture** | Follow-on (retail) |

---

### `SIG-LABOR-02` — Labor % out of band

| | |
|---|---|
| **Metric** | Payroll hours vs POS sales by day/location vs threshold |
| **Requires** | Commerce (`SYS-SQUARE`) + Payroll (`SYS-GUSTO`) + Accounting; or Shopify + payroll |
| **Industry tags** | **F** |
| **Meshflow strength** | **High** |
| **Sell posture** | Follow-on / co-hero retail |

---

## Family: Identity & other

### `SIG-CUST-01` — Customer identity chaos

| | |
|---|---|
| **Metric** | Unmatched / ambiguous customer links across M1 ↔ M2 |
| **Requires** | Any Mesh with 2+ systems (Ops/FSM/Commerce/PSA + Accounting) |
| **Industry tags** | All |
| **Meshflow strength** | **High** |
| **Sell posture** | **Enabler** — do not sell alone; required infrastructure for billing Signals |

---

### `SIG-NEW-01` — New customer revenue

| | |
|---|---|
| **Metric** | Revenue from customers first seen in period (definition locked in SOW §10) |
| **Requires** | Any with customers + invoices |
| **Industry tags** | Broad |
| **Sell posture** | Bundle |

---

### `SIG-MKT-01` — Marketing spend return (thin)

| | |
|---|---|
| **Metric** | Spend sheet vs new-customer revenue — **not** full multi-touch ROAS |
| **Requires** | Accounting + `SYS-EXCEL` spend sheet (optional marketing M4) |
| **Industry tags** | **F, C** |
| **Meshflow strength** | **Weak** |
| **Sell posture** | Sparingly — set expectations hard |

---

### `SIG-CALLBACK-01` — Callback / warranty untracked

| | |
|---|---|
| **Requires** | FSM + Accounting (`SYS-SERVICETITAN`, `SYS-JOBBER`, `SYS-OPTSY`, …) |
| **Industry tags** | **C, D** |
| **Sell posture** | Later |

---

### `SIG-SHRINK-01` — Shrink / velocity vs on-hand drift

| | |
|---|---|
| **Requires** | Commerce + Accounting |
| **Industry tags** | **F** |
| **Sell posture** | Later — signals only; count still needed |

---

### `SIG-VENDOR-01` — Vendor bill vs receiving gap

| | |
|---|---|
| **Requires** | Commerce or Ops ERP + Accounting |
| **Industry tags** | **F, A** |
| **Sell posture** | Later |

---

## Explicitly deferred (not sold as Meshflow Signals)

| ID | Name | Why |
|---|---|---|
| `SIG-SCHED-01` | Schedule / capacity overload | Crowded; not reconciliation |
| `SIG-UTIL-01` | Tech utilization % | FSM-native dashboards |
| `SIG-LEAD-01` | Lead → booked | CRM / marketing product |
| `SIG-CASHAPP-01` | Cash application | Crowded category (listed above as defer-hero) |

---

## Recommended packs by industry / systems

| Context | Typical systems in Mesh | Launch Signals | Next |
|---|---|---|---|
| **A Dist** | NetSuite/BC/Fishbowl + QB + Excel | BILL-01, BILL-02, AR-01 | BO-01, OTIF-01, STOCK-01 |
| **B Product mfg** | NetSuite/BC + QB + Excel | BILL-01, AR-01 | BILL-02, STOCK-01, MARGIN-02 |
| **B-js Job shop** | Legacy ERP or NS + QB + Excel | BILL-01, AR-01 | BILL-02, STATUS-01, MARGIN-01 |
| **C/D Trades / field** | ServiceTitan/Jobber/Opts + QB + Excel | BILL-01, AR-01 | CO-01, PART-01, LABOR-01, MEM-01 |
| **E Pro svc** | Harvest/BQE or QB+Excel | WIP-01, AR-01 | NEW-01, MARGIN-01 |
| **F Retail** | Shopify/Square + QB + Excel (+ Gusto) | CASH-01 | INV-02, LABOR-02, MARGIN-04 |
| **Thin stack** | QB + Excel only | AR-01 | WIP-01 (Excel), NEW-01 |

---

## Signal × system-role compatibility (summary)

| Signal | Ops ERP | FSM | Commerce | PSA | QB + Excel only |
|---|---|---|---|---|---|
| BILL-01 | ●●● | ●●● | ● (B2B only) | ●● | ○ Excel |
| BILL-02 | ●●● | ● | — | — | — |
| CO / PART / LABOR-01 | — | ●●● | — | labor ○ | — |
| MEM-* | — | ●●● | — | — | — |
| BO / OTIF / STOCK | ●●● | — | STOCK ○ | — | — |
| CASH-01 / INV-02 / LABOR-02 | — | — | ●●● | — | — |
| WIP-01 | ○ | — | — | ●●● | ●● |
| AR-01 / NEW-01 | ●●● | ●●● | ●●● | ●●● | ●●● |
| CUST-01 | ●●● | ●●● | ●●● | ●●● | — |

●●● = designed for · ●● = strong · ● = situational · ○ = limited / template · — = not a fit

---

## SOW usage

1. Compose Mesh from **System IDs** in [mesh-node-catalog.md](./mesh-node-catalog.md) (optionally start from a sample in [mesh-catalog.md](./mesh-catalog.md)).  
2. Select Signals **only** from this catalog whose **Requires** roles are covered.  
3. Lock thresholds (“N days”, “new customer”, hold reasons) in SOW §10.  
4. New Signal ideas → add a catalog card here **before** putting an ID on a customer SOW.

---

## Related

- [mesh-node-catalog.md](./mesh-node-catalog.md) — Mesh nodes (`SYS-…`)
- [mesh-catalog.md](./mesh-catalog.md) — sample Meshes
- [sow-template-meshflow.md](../contracts/sow-template-meshflow.md)
- [Industry-opportunities/](./Industry-opportunities/) — problem rankings that feed this catalog

---

## Revision log

| Date | Change |
|---|---|
| 2026-07-20 | Initial Wedge catalog — IDs, families, industry tags, packs |
| 2026-07-20 | Requires = system roles/IDs (Meshes composed, not prebuilt) |
| 2026-07-21 | Renamed Wedge → **Signal**; IDs `W-*` → `SIG-*`; file signal-catalog.md |
| 2026-07-20 | Requires = system roles/IDs (Meshes composed, not prebuilt) |
