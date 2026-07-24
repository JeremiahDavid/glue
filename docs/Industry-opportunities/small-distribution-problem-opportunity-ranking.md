# Small Distribution — Problem Opportunity Ranking (Pre-Discovery)

**Scope:** Small **wholesale / distribution** companies ($5M–$50M) — inventory-centric businesses that buy, stock, pick, pack, and ship catalog SKUs to customers (contractors, dealers, retailers, other distributors).

**Not in scope here:** Large 3PLs, pure e-commerce marketplaces, or distributors with full WMS + EDI at enterprise scale (different buyer and build).

**Companions:**
- [job-shop-manufacturing-problem-opportunity-ranking.md](./job-shop-manufacturing-problem-opportunity-ranking.md)
- [smaller-manufacturing-problem-opportunity-ranking.md](./smaller-manufacturing-problem-opportunity-ranking.md)

**Purpose:** Show how Meshflow problem rankings shift for **distributors** — the third leg of “small industrial businesses” alongside job shops and product manufacturers.

**Status:** Pre-discovery hypothesis. Validate with distributor-specific discovery calls.

---

## Distributor vs manufacturer — what’s different

| Dimension | Job shop mfg | Product mfg (PDM-like) | **Small distributor** |
|---|---|---|---|
| **Core asset** | Capacity + labor | Production + FG inventory | **Inventory turns** |
| **Unit of work** | Job / work order | Production run + SKU | **Sales order line + pick/shipment** |
| **Customer promise** | Custom due date | Lead time / fill to distributor | **OTIF, fill rate, backorder ETA** |
| **Ops fire** | Late jobs | Stockout / excess FG | **Backorders, stockouts, partials, mis-picks** |
| **Cash leak** | Shipped job, no invoice | Shipped SO, no invoice | **Shipped lines not invoiced, partial bill, pricing errors** |
| **Margin truth** | Job cost | SKU + commodity cost | **SKU / category / customer tier margin** |
| **Typical systems** | JobBOSS + QB | ERP + QB | **NetSuite, Dynamics, Epicor, Fishbowl, Cin7 + QB** |
| **Meshflow sweet spot** | Job ↔ invoice | SO ↔ invoice | **Shipment line ↔ invoice line; backorder ↔ inventory** |

**Headline:** Distributors look like **product manufacturers on fulfillment** (orders + SKUs) but care **more about inventory and backorders** and **less about production, jobs, or yield**.

---

## How to read the scores

Same formula as companion docs:

| Score | **Business importance** (1–5) | **Ease of implementation** (1–5) |
|---|---|---|
| 5 | Acute cash or customer-retention pain | Clean ERP fields; days to first value |

**Meshflow novelty (1–5):** Requires cross-system reconciliation (not a single ERP report).

**Launch score** = `(Importance × 2) + Ease + Meshflow novelty`

---

## Ranked catalog — small distributor

### Tier A — Strong launch / early products

| Rank | Problem | Imp. | Ease | Meshflow | Launch | vs job shop | Notes |
|---|---|---|---|---|---|---|---|
| **1** | **Shipped / picked lines not fully invoiced** | 5 | 3 | 5 | **17** | Same family, **line-level harder** | Partials, split shipments, qty mismatch SO↔invoice — core Meshflow play |
| **2** | **Past-due AR — ranked collections** | 5 | 5 | 2 | **17** | Same | Universal; weak solo Meshflow Signal |
| **3** | **Backorder aging / open backorders ($)** | 5 | 4 | 2 | **16** | **Replaces late jobs** | #1 *ops* emotion for dist; mostly ERP — action queue still valuable |
| **4** | **OTIF / fill-rate failures (open orders)** | 5 | 3 | 3 | **16** | OTIF not OTD | Customer retention; needs request date + qty shipped vs ordered |
| **5** | **Stockouts on SKUs with open customer demand** | 5 | 3 | 3 | **16** | **↑ vs mfg** | Join open SO lines to on-hand = Meshflow value |

### Tier B — Strong follow-ons

| Rank | Problem | Imp. | Ease | Meshflow | Launch | Notes |
|---|---|---|---|---|---|---|
| **6** | **Slow / dead / excess inventory ($ tied up)** | 5 | 4 | 1 | **14** | **Higher imp than mfg** — inventory *is* the business; ERP-native |
| **7** | **SKU / customer / tier margin outliers** | 4 | 2 | 3 | **13** | Vendor cost changes vs sell price lists |
| **8** | **Customer over credit limit blocking ship** | 4 | 3 | 4 | **15** | ERP credit + accounting AR — cross-system |
| **9** | **Customer identity chaos (ERP ↔ QB)** | 3 | 4 | 5 | **15** | Same enabler as mfg |
| **10** | **Inbound supplier late (PO OTD)** | 4 | 3 | 2 | **13** | Causes backorders; secondary to customer-facing pain |
| **11** | **Pricing / cost sheet drift (wrong margin)** | 4 | 2 | 3 | **13** | Excel price lists + ERP cost — Meshflow + unstructured |
| **12** | **EDI / portal orders stuck (ack → ship → bill)** | 3 | 2 | 4 | **12** | If they sell via EDI; gap between ship confirm and invoice |

### Tier C — Real but poor Meshflow v1 fit

| Rank | Problem | Imp. | Ease | Meshflow | Launch | Notes |
|---|---|---|---|---|---|---|
| **13** | **Pick accuracy / mis-ship rate** | 4 | 1 | 1 | **10** | WMS / scan territory |
| **14** | **Freight-out margin leakage** | 3 | 2 | 3 | **11** | Allocation fights |
| **15** | **Late custom jobs** | 1 | — | — | **—** | N/A |
| **16** | **Job / quote costing variance** | 1 | — | — | **—** | N/A |
| **17** | **Warehouse capacity / labor utilization** | 3 | 2 | 1 | **9** | Labor scheduling — different category |

---

## Three-way comparison — what moves

| Problem | Job shop | Product mfg | **Small distributor** |
|---|---|---|---|
| Unbilled / incomplete billing | **#1** | **#1** | **#1** (line-level emphasis) |
| Past-due AR | #2 | #2 | #2 |
| Late jobs | #3 | ~#14 | **N/A** |
| **Backorder aging** | Low | Medium | **#3 ops pain** |
| **OTIF / fill rate** | Low | #3-ish | **#4** |
| **Stockouts on open demand** | Medium | #3 | **#5** |
| **Dead / excess inventory** | #10 | #5 | **#6 (imp 5)** |
| Job margin | #7 | → SKU margin | **SKU / tier margin #7** |
| Material shortages on jobs | #9 | → FG stockout | **Inbound PO late #10** |
| Capacity / scheduling | Hard | Line util | **Pick labor — defer** |

---

## Launch Signal for distributors

### Billing completeness candidate — only when native controls leave a line-level gap

For distributors, the hero story is often not “Job 4412 shipped” but:

> **“You shipped 80 of 100 on line 3 last Tuesday — only 60 were invoiced.”**

| Why it still wins | Distributor nuance |
|---|---|
| Cash stuck in partials | Multi-line orders, split shipments, backorder partials |
| Residual control gap | Native integration fails, summarizes, delays, or obscures line-level shipment ↔ invoice state |
| Meshflow novelty | Independent SO line ↔ shipment line ↔ invoice line control beyond built-in sync/error dashboards |
| ROI | Dollarize unbilled **lines** and aged partials |

**Product name sketch:** *“Bill what you shipped”* or *“Shipment-to-invoice gap”* — not “unbilled jobs.”

### Best **second** product for dist: Backorder + stockout queue (not late jobs)

| Pack | Buyer | Meshflow role |
|---|---|---|
| **Fulfillment Exceptions** | Inside sales / warehouse mgr | Ranked backorders by age × $; stockouts blocking open SO lines |
| **Cash Cycle** (bundle) | Controller | Unbilled lines + past-due AR |
| **Inventory Cash** (later) | Owner / purchasing | Dead stock, excess, GMROI shortlist — mostly ERP, weaker Meshflow |

---

## Recommended roadmap — distributor track

```
LAUNCH (shared spine)
  Shipped-not-invoiced / line-level billing gap
       │
       ├─► + Past-due AR              = Cash Cycle pack
       ├─► + Partial / qty mismatch  = Billing Completeness (critical for dist)
       │
DISTRIBUTOR PACK (follow-on)
       ├─► Backorder aging queue
       ├─► OTIF / fill-rate exceptions
       ├─► Stockouts affecting open orders
       │
LATER
       ├─► Dead / excess inventory
       ├─► SKU / customer margin outliers
       └─► Credit-limit holds · EDI stuck orders
```

**Do not lead with:** job costing, late jobs, capacity scheduling, pick accuracy.

---

## Systems & data model implications

### Typical stack (small distributor)

| Role | Common systems |
|---|---|
| ERP / inventory | NetSuite, Dynamics BC, Epicor, Acumatica, Fishbowl, Cin7 |
| Accounting | Often same ERP module, or QuickBooks |
| WMS | Sometimes native ERP; rarely best-of-breed at $5–30M |
| Pricing | ERP price lists + **Excel** overrides |
| EDI | SPS, TrueCommerce, retailer portals (segment-dependent) |

### Canonical entities (distributor Meshflow)

| Entity | Replaces (mfg) |
|---|---|
| `SalesOrder` + `SalesOrderLine` | Job |
| `Shipment` + `ShipmentLine` | Job shipment |
| `Invoice` + `InvoiceLine` | Invoice |
| `BackorderLine` | Material shortage on job |
| `InventorySnapshot` by SKU/location | WIP |
| `Customer` + credit limit | Same |

**Architecture:** If you sell to distributors, **`SalesOrderLine` / `ShipmentLine` must be first-class** — header-level job model is insufficient.

---

## Discovery questions (distributor-specific)

Add to discovery script when `segment = distribution`:

1. Walk me through a **partial shipment** — how does billing catch up?  
2. Where do **backorders** show up today — ERP report, Excel, sales inbox?  
3. What’s your **fill rate / OTIF** — do you measure it? Who owns it?  
4. How often do customers call about **stockouts or backorder ETAs**?  
5. Shipped-not-invoiced — do you run that report? At **header or line** level?  
6. One system or ERP + QuickBooks?  
7. **Dead inventory** — who decides what to markdown or return to vendor?  
8. EDI or customer portals — where do orders get stuck between ship confirm and invoice?

**Segment tag:** `wholesale_dist` | `industrial_supply` | `hvac_plumbing` | `packaging` | etc.

**Go/no-go for dist Launch Signal:** ≥50% describe **partial-ship billing gaps** or **backorder chaos** that their native integrations/reports do not resolve; source systems provide daily order, shipment, and invoice data.

---

## ICP positioning summary

| If your beachhead is… | Lead problem | Lead ops pack | Avoid |
|---|---|---|---|
| Job shop | Unbilled job ship | Late jobs | SKU backorder depth day 1 |
| Product mfg (PDM-like) | Unbilled SO ship | Fill rate / stockouts | Job language |
| **Small distributor** | **Unbilled / partial line billing** | **Backorders + OTIF** | Jobs, costing, capacity |

**One company, three skins:** Same Meshflow spine (connect ERP/accounting, reconcile lines, rank exceptions) — different **exception catalogs** and copy.

---

## Scoring caveats

- Distributors on **single cloud ERP** with strong native OTIF/backorder dashboards are weaker fit for ops packs.
- Fishbowl/Cin7 customers are not automatically strong merely because finance is separate: both provide native accounting integrations, and Cin7 also integrates commerce. Billing or integration assurance requires demonstrated failures beyond built-in sync/error controls.
- **Line-level** billing completeness is harder to implement than header-level — scores reflect that (ease 3 not 4)  
- Industrial distributors with **vendor-managed inventory** or consignment are edge cases — validate consignment false positives on unbilled  
- Scores are pre-discovery; backorder pain may outrank unbilled in *emotion* even if unbilled wins on Meshflow novelty + cash ROI  

---

## Revision log

| Date | Change |
|---|---|
| 2026-07-17 | Initial distributor ranking; three-way comparison vs job shop and product mfg |
| 2026-07-23 | Add native-integration erosion caveat for Fishbowl/Cin7 split stacks |
