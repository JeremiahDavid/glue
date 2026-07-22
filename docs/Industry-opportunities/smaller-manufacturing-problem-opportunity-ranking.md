# Smaller Manufacturing — Problem Opportunity Ranking (Pre-Discovery)

**Scope:** Smaller manufacturing companies broadly ($5M–$50M band as a working hypothesis) — not limited to job shops. Includes:

| Mode | What it looks like | Example archetype |
|---|---|---|
| **Job shop / MTO** | Custom or high-mix; work orders; quote→job→ship | Machine shop, fabricator |
| **Product / repetitive / MTS–ATO** | Catalog SKUs; inventory; automated or semi-continuous lines | **[PDM US, LLC](https://pdmus.com/)** — insulated copper linesets & tubing for HVAC/R |
| **Hybrid** | Mix of catalog + custom | Many mid-market plants |

**Companion (narrow ICP):** [job-shop-manufacturing-problem-opportunity-ranking.md](./job-shop-manufacturing-problem-opportunity-ranking.md)

**Purpose:** Show how rankings **shift** when Meshflow targets “small manufacturers” generally — using PDM-like plants as the contrast case — and what that means for Launch Signal choice.

**Status:** Pre-discovery hypothesis. PDM is used as a **public archetype** (integrated product manufacturer selling catalog goods via distributors), not as a researched customer.

---

## What changes when you leave pure job shop

Job-shop Meshflow thinking centers on **jobs**. Broader small manufacturing centers on **SKUs, inventory, yield, and fulfillment**.

| Dimension | Job shop | Product / repetitive (PDM-like) |
|---|---|---|
| Unit of work | Job / work order | Production run + sales order / SKU |
| Primary promise | Custom due date per job | Lead time, fill rate, distributor OTIF |
| Margin truth | Job cost vs quote | SKU / customer / channel margin; metal/commodity cost |
| Cash leak shape | Shipped job not invoiced | Shipped SO / lineset not invoiced; credit holds; EDI gaps |
| Ops fire | Late jobs, shortages on unique BOMs | Stockouts, overstock, scrap/yield, line downtime |
| Systems | JobBOSS / E2 / Epicor + QB | Often stronger ERP (or industry ERP) + WMS-lite + QB/accounting; more automated shop floor |
| Excel shadow | Capacity, hot list, shortages | Pricing sheets, copper cost, distributor allocations |

**Implication:** The **unbilled shipment** problem still exists and often remains a strong Meshflow wedge — but inventory, fill-rate, and **SKU/customer margin** rise in importance, while **quote-vs-actual job costing** and **late custom jobs** fall for plants like PDM.

---

## PDM US as a calibration example

From public information, PDM US LLC (Rock Hill, SC):

- Manufactures **insulated / non-insulated copper tubing and linesets** for HVAC/R (mini-splits, VRF, heat pumps)
- **Catalog product** business with distributors (credit apps, reps across Americas)
- Emphasizes **fully integrated, automated production** (own copper + insulation)
- Expanding capacity / casting — capital- and process-intensive, not one-off job shop

**Likely pain hierarchy (hypothesis — not confirmed):**

1. Working capital in **finished goods + copper** (price volatility, overstock vs stockout)  
2. **Distributor fill rate / OTIF** and order completeness  
3. **Ship → invoice → collect** cash cycle (especially multi-line / multi-SKU orders)  
4. **Margin by SKU / customer / channel** under copper cost swings  
5. Yield / scrap / quality cost (process) — often inside MES/ERP, harder Meshflow story  
6. Classic “Job 4412 late” — **much less central** than in a fab shop  

Use this as a reminder: “small manufacturer” ≠ “job shop.”

---

## How to read the scores

Same scale as the job-shop doc:

| Score | **Business importance** | **Ease of implementation** |
|---|---|---|
| 5 | Acute cash/EBITDA | Days to value; clean definition |
| 1 | Rarely budget-worthy alone | MES-heavy or unreliable fields |

**Meshflow novelty (1–5):** Requires cross-system reconciliation.

**Launch score** = `(Importance × 2) + Ease + Meshflow novelty`

Scores below are for the **broader small-manufacturer average**, with notes where **product/MTS** (PDM-like) diverges from **job shop**.

---

## Ranked catalog — generalized small manufacturing

### Tier A — Strong launch candidates (broader ICP)

| Rank | Problem | Imp. | Ease | Meshflow | Launch | vs job shop | Notes for PDM-like plants |
|---|---|---|---|---|---|---|---|
| **1** | **Shipped / fulfilled but not invoiced** | 5 | 4 | 5 | **18** | **Same #1** | Still hero Signal — SO/shipment lines ↔ invoices; may be cleaner IDs than jobs if ERP is stronger |
| **2** | **Past-due AR — ranked collections** | 5 | 5 | 2 | **17** | Same | Distributor credit + terms; still weak solo Meshflow story |
| **3** | **Fill rate / stockouts on active SKUs** | 5 | 3 | 2 | **15** | **↑ from Tier C** | Replaces “late jobs” as top *ops* emotion for MTS/product plants |
| **4** | **Partial ship / under-invoiced order lines** | 4 | 3 | 5 | **16** | Similar | Multi-SKU lineset orders → line-level billing completeness matters more |

### Tier B — Strong follow-ons / mode-dependent

| Rank | Problem | Imp. | Ease | Meshflow | Launch | vs job shop | Notes |
|---|---|---|---|---|---|---|---|
| **5** | **Slow / obsolete / excess finished goods** | 4 | 4 | 1 | **13** | **↑ Imp** | Copper/FG inventory is cash; ERP-native but owners feel it weekly |
| **6** | **SKU / customer / channel margin outliers** | 5 | 2 | 3 | **15** | Replaces job margin | Commodity cost + price lists; still definition-hard |
| **7** | **Open order OTIF / late sales orders** | 4 | 3 | 2 | **13** | Late *jobs* → late *orders* | Promise date on SO, not job routing |
| **8** | **Customer identity chaos (ERP ↔ accounting)** | 3 | 4 | 5 | **15** | Same enabler | Distributor name variants still messy |
| **9** | **Raw material / commodity cost vs sell price gap** | 4 | 2 | 3 | **13** | **New** | Copper price vs catalog pricing — high for PDM-like; needs cost + price sources |
| **10** | **Unbilled / incomplete EDI or distributor portal orders** | 3 | 2 | 4 | **12** | **New** | If they sell via EDI/portals — gap between ship confirm and invoice |

### Tier C — Still real; weaker Meshflow v1 or mode-specific

| Rank | Problem | Imp. | Ease | Meshflow | Launch | vs job shop |
|---|---|---|---|---|---|---|
| **11** | Supplier / inbound PO late | 3 | 3 | 2 | **11** | Similar |
| **12** | Yield / scrap / process variance | 4 | 1 | 1 | **10** | **↑ Imp for process**; ease still kills Meshflow v1 |
| **13** | Job-level quote vs actual | 2 | 2 | 3 | **9** | **↓↓** — often irrelevant for catalog MTS |
| **14** | Late custom jobs (routing-level) | 2 | 2 | 2 | **8** | **↓↓** — not the unit of planning |
| **15** | Capacity vs infinite backlog (finite scheduling) | 3 | 1 | 1 | **8** | Still hard; different flavor (line utilization) |
| **16** | Cash application / unmatched payments | 4 | 2 | 4 | **14** | Same crowded category |
| **17** | Change-order leakage | 2 | 2 | 4 | **10** | **↓** — contractor problem, not PDM |

---

## Side-by-side: what moves when you generalize

| Problem | Job-shop rank | Broader small mfg | Direction | Why |
|---|---|---|---|---|
| Unbilled shipments | **#1 launch** | **#1 launch** | Stable | Universal cash leak when ops ≠ billing system |
| Past-due AR | #2 | #2 | Stable | Universal; still poor solo Meshflow Signal |
| Late jobs | #3 | Falls to ~#14 | **Down** | Jobs aren't the planning object in MTS |
| Fill rate / stockouts | Tier C (#10-ish) | **#3** | **Up** | Catalog + distributors live/die on availability |
| Slow / obsolete inventory | #10 (imp 3) | **#5** (imp 4) | **Up** | FG + commodity inventory = working capital |
| Job / quote margin | #7 | Falls / reframes | **Down / morph** | Becomes **SKU/customer/channel margin** |
| Material shortages on jobs | #9 | Morphs to inbound + FG stockout | Shift | Less “this job blocked,” more “this SKU OOS” |
| Yield / scrap | Barely listed | Enters Tier C with high imp | **Up for process** | Hard for Meshflow; MES territory |
| Change orders | #15 | Deprioritized | **Down** | Not PDM-like |

**Bottom line:** Expanding ICP **does not kill** the unbilled-shipment launch — it **strengthens** the case that the first product is a **cash / billing-completeness** Signal that travels across manufacturing modes. What changes is the **second and third** products: inventory/fill-rate and SKU margin instead of late-job and job-cost packs.

---

## Recommended launch under a broader ICP

### Still recommend: Unbilled / incomplete billing as SKU #1

Reasons that survive generalization:

1. **Mode-agnostic:** Jobs *or* sales-order lines — same Meshflow pattern (fulfillment event ↔ invoice)  
2. **Cross-system novelty:** Strongest when warehouse/ERP ≠ QuickBooks/accounting  
3. **ROI in week 1:** Dollarize the queue  
4. **PDM-plausible:** Distributor multi-line shipments + credit/terms create exactly this gap  
5. **Roadmap stays coherent:** Cash Cycle → Billing Completeness → then **mode-specific** packs

### What *not* to assume for PDM-like buyers

| Don't lead with | Lead with instead |
|---|---|
| “Late jobs on the shop floor” | “Orders that shipped incomplete or unbilled” |
| “Quote vs actual on Job 4412” | “Which SKUs/customers are underwater after copper cost” |
| “Material shortage on custom BOM” | “Stockouts and excess on A-movers” |
| JobBOSS-only playbooks | Order + shipment + invoice + inventory snapshot |

---

## Dual-track product roadmap (if ICP includes both modes)

```
SHARED SPINE (launch)
  Unbilled / incomplete billing  →  + AR = Cash Cycle
                                 →  + Partial lines = Billing Completeness

MODE PACK — Job shop
  Late jobs · Job margin · Quote variance · Job shortages

MODE PACK — Product / repetitive (PDM-like)
  Fill rate / stockouts · Excess FG · SKU/customer margin · Commodity cost gap
```

**Architecture implication:** Canonical model needs **both** `Job` and `SalesOrderLine` / `ShipmentLine` early if you market to “small manufacturing” generally — not job-only entities.

---

## Discovery questions (add for non–job-shop manufacturers)

Ask in addition to the job-shop list:

1. Are you primarily **make-to-order custom**, **make-to-stock catalog**, or hybrid?  
2. Who do you sell to — end users, OEMs, or **distributors**?  
3. Where does finished-goods inventory live, and how painful are stockouts vs excess?  
4. How do copper / commodity / raw material price moves show up in margin?  
5. Is shipping and invoicing in the **same system**?  
6. Do you use EDI or distributor portals — where do orders get stuck between ship and bill?  
7. What does Monday morning look like for the plant manager vs the controller?

**Segment tag every interview:** `job_shop` | `product_mts` | `hybrid` — don't average scores blindly.

---

## ICP decision for Meshflow GTM

| Strategy | Pros | Cons |
|---|---|---|
| **A. Stay job-shop first** | Sharper messaging, simpler data model, clearer playbooks | Smaller TAM; may miss plants like PDM |
| **B. Broad “small manufacturing”** | Larger TAM; unbilled Signal still works | Diluted messaging; need SO+inventory entities sooner |
| **C. Cash-leakage Signal, two skins** | One product story (“stop leaving money on the dock”); two definition packs | Requires disciplined segmentation in sales |

**Recommendation:** Keep **launch problem** = unbilled/incomplete billing (shared). Choose **primary beachhead** (job shop vs product mfg) for messaging and first playbooks — don't pretend one ops dashboard fits PDM and a 40-person fab equally.

If PDM-like companies are in the target list, treat them as **product/repetitive** discovery cohort and re-score inventory/fill-rate after 5 interviews in that segment.

---

## Scoring caveats

- PDM used as **public archetype only** — not a diligence target or confirmed stack  
- Broader scores are a **blend**; always segment interviews before locking roadmap  
- Process/MES-heavy plants may have less Excel chaos but **harder** access / stronger incumbent ERP analytics  
- Commodity manufacturers may care more about **cost & inventory** than billing gaps — validate before assuming #1 still wins in that cohort  

---

## Revision log

| Date | Change |
|---|---|
| 2026-07-17 | Initial generalized ranking; PDM US as product/MTS calibration; dual-track roadmap |
