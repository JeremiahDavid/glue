# Industry × Source System Clusters

**Purpose:** Group small and mid-sized businesses by **shared system families** so connector development follows validated account reach and pain—not an assumed universal stack.

**Companion (full GTM strategy):** [gtm-industry-system-matrix.md](./gtm-industry-system-matrix.md)  
**Canonical product nodes:** [mesh-node-catalog.md](./product-scoping/mesh-node-catalog.md) · [mesh-catalog.md](./product-scoping/mesh-catalog.md) (samples) · [signal-catalog.md](./product-scoping/signal-catalog.md)

**Product spine:** AI-assisted meshflow links source systems or full-ERP module domains → trusted operational facts → ranked exceptions (not dashboards).

**Status:** Pre-discovery—**A+B remains the provisional ICP; BC and NetSuite are the leading Phase 1 candidates.** Split-stack Fishbowl/Cin7 paths require native-integration gap validation.

---

## Design rules

1. **Do not assume accounting system from industry alone.** Capture QBO/QBD, NetSuite, BC, and other explicitly.
2. **Full ERP path:** NetSuite / Business Central / Acumatica usually **replace** QB. Use `MESH-NS-INTRA` / `MESH-BC-INTRA`; Excel/satellites are optional, and NS/BC + QB is not the default.
3. **Excel is nearly universal** (slot U2) — shadow holds, allocations, recon.
4. **Third slot = ops system of record** when accounting is QB — Fishbowl, Cin7, ServiceTitan, Shopify, etc.
5. **Prioritize the first connector by reachable accounts × pain × willingness to pay × access × repeatability.** Complementary-stack novelty is one input, not the decision.
6. **One spine SKU across clusters** — fulfillment/billing/cash completeness; **wording and entities** change per pack.
7. **Job shop is not the center** — custom MTO shops are a subset of clusters B and C, not a separate universe.

---

## Shared foundation and accounting paths

| ID | System | Integration | What meshflow pulls |
|---|---|---|---|
| **U1** | **QuickBooks Online** | API | Customers, invoices, payments, AR aging, deposits, GL summary |
| **U1b** | **QuickBooks Desktop** | Scheduled export | Same semantic model as QBO |
| **U2** | **Excel / Google Sheets** | Templated file drop | Shadow ops: holds, allocations, hot lists, manual recon sheets |

**Interview gate:**
- Accounting = QB → evaluate the split-stack playbook and actual ops system.
- Accounting = NetSuite / BC → evaluate cross-module operational-control pain plus Excel/satellite workflows; do not disqualify merely because billing is in-system.
- Accounting = other → tag `accounting_other`; measure frequency before deciding whether it changes the ICP.

---

## System-first clusters (connector playbooks)

Industries are grouped by shared system family, but **development priority** also requires recurring pain, reachable accounts, willingness to pay, and feasible access.

### Validation path A: `fishbowl_qb_excel` — **native integration already present**

**System:** Fishbowl (+ QBO + Excel)

| Industries in this playbook | Cluster ref |
|---|---|
| Wholesale / industrial **distribution** | A |
| **Product / repetitive manufacturing** | B |
| Inventory-heavy SMB without full ERP | A, B |

**Why validation-only:** Fishbowl already exports fulfilled orders, invoices/bills, COGS, inventory adjustments, and accounting entries to QBO. The connection itself is not Meshflow value. Proceed only when customers show recurring failed/waiting exports, mapping or reconciliation discrepancies, or operational queues Fishbowl does not resolve.

**Hero Signal:** Unbilled / incomplete billing (ship ↔ QB invoice).

---

### Validation path A2: `cin7_qb_excel` — **native accounting/commerce hub already present**

**System:** Cin7 (+ QBO + Excel)

| Industries | Cluster ref |
|---|---|
| Distribution without Fishbowl | A |
| Product mfg / light assembly | B |

**Why validation-only:** Cin7 connects QBO/Xero and channels such as Shopify, including invoices, payments, credits, COGS, inventory, and order flows. Test only integration assurance, tax/COGS/payout reconciliation, and operational exceptions that Cin7's sync dashboards do not already solve.

---

### Candidates B/C: `bc_intra` / `netsuite_intra` — **full-ERP Phase 1 candidates**

**System:** NetSuite or Business Central cross-module; Excel/satellites optional and QB absent by default

| Industries | Cluster ref |
|---|---|
| Distribution / product mfg on full ERP | A, B |
| Some pro services / multi-channel retail / light 3PL / staffing with NS | E, F, G, J |

**Why candidates:** NS/BC are full ERPs and usually replace QuickBooks, but native reporting does not eliminate cross-module operational-control needs. Test recurring, packaged problems involving order → fulfillment → invoice → payment, inventory, purchasing, margin, multi-entity state, historical snapshots, and critical Excel/satellite workflows. Avoid generic custom-reporting projects. Dual-run NS/BC + QB remains exceptional.

**Candidate launch Signals:** Billing completeness, partial fulfillment/invoice mismatch, backorder or OTIF risk, inventory exceptions, and margin leakage—select the first package from discovery.

---

### Playbook 4: `shopify_qb_excel` — **P3 retail / DTC**

**System:** Shopify (POS + online) (+ QBO + Excel)

| Industries | Cluster ref |
|---|---|
| **Multi-channel retail** | F |
| DTC product brands (often also cluster B mentally) | B, F |
| Some wholesale portal sellers | F |

**Hero Signal:** **Cash recon + channel inventory**—not unbilled shipment (see [retail-problem-opportunity-ranking.md](./Industry-opportunities/retail-problem-opportunity-ranking.md)).

**Why post-A+B:** Different hero SKU; POS competition; still huge TAM for wave 2.

---

### Playbook 5: `square_qb_excel` (+ optional Gusto)

**System:** Square (+ QBO + Excel; + Gusto for labor Signal)

| Industries | Cluster ref |
|---|---|
| Single/multi-location **retail** | F |
| **Trades** (small) | C |
| **Field service** lite | D |
| Restaurants (defer spine) | I |
| Events, mobile vendors | — |

**Why P3:** Massive reach; overlaps retail + trades; labor % SKU pairs with Gusto.

---

### Playbook 6: `servicetitan_qb_excel` — **P4 trades / field**

**System:** ServiceTitan (+ QBO + Excel)

| Industries | Cluster ref |
|---|---|
| **HVAC, plumbing, electrical** (commercial/resi) | C |
| **Field service & equipment repair** | D |

**Hero Signal:** Completed job / WO not invoiced; unbilled WIP milestones.

**Why P4:** Huge TAM but **different entity model** from NS — separate playbook after A+B proven.

---

### Playbook 7: `jobber_hcp_qb_excel`

**System:** Jobber, Housecall Pro (+ QBO + Excel)

| Industries | Cluster ref |
|---|---|
| Smaller **trades** | C |
| **Landscaping**, pest, cleaning | C, landscaping |

**Why P4:** Downmarket trades; same spine as ServiceTitan.

---

### Playbook 8: `psa_qb_excel`

**System:** Harvest, BQE Core, Mavenlink (+ QBO + Excel)

| Industries | Cluster ref |
|---|---|
| **Professional services** — agencies, consultancies, engineering | E |

**Hero Signal:** Unbilled WIP / hours not invoiced.

**Why P5:** Often **QB + Excel only** sufficient for v1; add PSA when repeat pain validates.

---

### Playbook 9: `appfolio_buildium` — **defer v1**

**System:** AppFolio, Buildium (property management)

| Industries | Cluster ref |
|---|---|
| **Property management** (residential, small commercial) | H |

**Why defer:** Rent billing often **inside PM software**; less ERP↔QB fragmentation; different spine (delinquency, turn, maintenance) — see defer section below.

---

### Playbook 10: `tms_spreadsheet` — **defer v1**

**System:** Spreadsheets + TMS lite (Magaya, etc.)

| Industries | Cluster ref |
|---|---|
| **Logistics**, freight broker lite, small 3PL | G |

**Why defer:** Specialized; contract billing; smaller $5–30M sweet spot overlap with A+B.

---

## Industry → playbook quick map

| Industry (your list) | Primary playbook | Secondary | Spine strength |
|---|---|---|---|
| **Product manufacturing** | **Primary hypothesis:** BC or NetSuite cross-module | Fishbowl/Cin7 only if native-integration gap validates | **5** |
| **Small distribution** | **Primary hypothesis:** BC or NetSuite cross-module | Fishbowl/Cin7 only if native-integration gap validates | **5** |
| **Retail (multi-channel)** | `shopify_qb_excel` | square, bc_intra | **3–4** |
| **Construction / trades** | `servicetitan_qb_excel` | jobber, square | **5** |
| **Property management** | `appfolio_buildium` | qb only | **2–3** defer |
| **Professional services** | `psa_qb_excel` | **qb+excel only** | **4** |
| **Logistics / 3PL** | `tms_spreadsheet` | netsuite_intra | **3** defer |
| **Field service** | `servicetitan_qb_excel` | jobber | **5** |
| **Staffing** | `qb_excel` | netsuite_intra | **4** |
| **Job shop (custom mfg)** | legacy ERP + QB | **not headline ICP** | **4** if ERP↔QB split |

---

## Connector selection sequence

The first system family is selected from evidence, not assigned in advance:

```
FOUNDATION — Reusable across candidates
  ├── Canonical order / fulfillment / invoice / payment / inventory model
  ├── Ranked-exception engine + provenance + historical snapshots
  ├── Excel/Sheets template ingest
  └── Retain existing QBO ingest

DISCOVERY GATE — A+B product mfg / distribution
  ├── Business Central cross-module (+ optional Excel / satellites)
  ├── NetSuite cross-module (+ optional Excel / satellites)
  └── Fishbowl/Cin7 only with measured native-integration or control gap

PHASE 1 — Build ONE validated family
  └── Require reachable design partner + recurring dollarized Signal

PHASE 2 — Add the next A+B family only after repeatable paid delivery

PHASE 3 — Wave 2 vertical (pick ONE based on discovery)
  ├── ServiceTitan (trades + field service)  OR
  └── Shopify (multi-channel retail)

PHASE 4 — Expand
  ├── Square (+ Gusto for labor SKU)
  ├── Jobber / Housecall Pro
  └── PSA (Harvest / BQE)

DEFER
  ├── NS/BC + QB dual-run (migration / multi-entity only)
  ├── AppFolio / Buildium (property mgmt)
  ├── Toast (restaurant)
  └── TMS variants (logistics)
```

**Rule:** Max **one new system family per quarter** after the foundation. Do not build both NetSuite and BC simultaneously.

---

## Industries you asked about — honest fit

### Retail
- **Fit:** Multi-channel + QB split → **strong** for cash recon, inventory mismatch, labor %.
- **Playbook:** Shopify or Square + QB + Excel.
- **Detail:** [retail-problem-opportunity-ranking.md](./Industry-opportunities/retail-problem-opportunity-ranking.md)

### Construction / trades
- **Fit:** **Excellent** — completed work not invoiced; change orders; QB almost always separate.
- **Playbook:** ServiceTitan or Jobber + QB + Excel.
- **Wave:** 2 (after the selected A+B family is validated) unless discovery pulls you here first.
- **Detail:** [trades-construction-problem-opportunity-ranking.md](./Industry-opportunities/trades-construction-problem-opportunity-ranking.md)

### Property management
- **Fit:** **Moderate-defer** — AppFolio/Buildium often owns rent roll; pain is delinquency, turns, vendor bills — different SKU.
- **Playbook:** Defer unless interviews show heavy QB + spreadsheet reconciliation outside PM tool.

### Professional services
- **Fit:** **Good** — unbilled hours/WIP; often **QB + Excel only** for v1 without PSA API.
- **Playbook:** Start `qb_excel` unbilled time template; add Harvest/BQE when repeated.

### Logistics
- **Fit:** **Moderate-defer** — billing on scans/contracts; TMS specialization; less universal QB+Excel+ERP pattern at SMB size.
- **Playbook:** Defer; revisit for NS-using small 3PLs only (`netsuite_intra`).

---

## One spine, many packs (GTM product shape)

```
                    ┌─────────────────────────────┐
                    │  SPINE: Cash / billing      │
                    │  completeness exceptions    │
                    │  (ops event ↔ books)        │
                    └──────────────┬──────────────┘
                                   │
     ┌─────────────┬───────────────┼───────────────┬─────────────┐
     ▼             ▼               ▼               ▼             ▼
  dist pack    product_mfg     trades pack      retail pack    pro_svc pack
  (Fishbowl)   (Fishbowl)      (ServiceTitan)   (Shopify)      (QB+Excel)
  backorder    fill/FG         job complete     cash recon     unbilled WIP
  OTIF         unbilled ship    not invoiced     channel inv    hours
```

**External message (all clusters):**  
*We connect how work gets done to your books and show what’s costing you money today.*

**Never lead with:** job shop, data platform, analytics, AI chat.

---

## Discovery fields (log on every call)

| Field | Example values |
|---|---|
| `cluster` | A, B, C, D, E, F, G, H, I, J |
| `playbook` | fishbowl_qb_excel, cin7_qb_excel, netsuite_intra, bc_intra, shopify_qb_excel, … |
| `accounting` | qbo, qbd, netsuite, bc, other |
| `ops_system` | fishbowl, cin7, netsuite, bc, shopify, square, servicetitan, appfolio, other |
| `excel_critical` | y/n + description |
| `spine_pain_1_5` | 1–5 |
| `recon_hours_week` | number estimate |

---

## Related problem rankings

| Industry focus | Document |
|---|---|
| Job shop (legacy narrow) | [job-shop-manufacturing-problem-opportunity-ranking.md](./Industry-opportunities/job-shop-manufacturing-problem-opportunity-ranking.md) |
| Product mfg (broad) | [smaller-manufacturing-problem-opportunity-ranking.md](./Industry-opportunities/smaller-manufacturing-problem-opportunity-ranking.md) |
| Small distribution | [small-distribution-problem-opportunity-ranking.md](./Industry-opportunities/small-distribution-problem-opportunity-ranking.md) |
| Retail | [retail-problem-opportunity-ranking.md](./Industry-opportunities/retail-problem-opportunity-ranking.md) |
| Trades / construction | [trades-construction-problem-opportunity-ranking.md](./Industry-opportunities/trades-construction-problem-opportunity-ranking.md) |
| Mfg + dist GTM SKUs | [gtm-product-mfg-distribution.md](./gtm-product-mfg-distribution.md) |

---

## Revision log

| Date | Change |
|---|---|
| 2026-07-18 | Initial industry-system-clusters — system-first playbooks, build order, industry map |
| 2026-07-20 | Link trades/construction problem ranking; fix Industry-opportunities paths |
| 2026-07-23 | Beachhead → Fishbowl/Cin7 + QB; NS/BC = full ERP (+ Excel), not + QB |
| 2026-07-23 | Retain A+B ICP but reopen Phase 1 family; elevate BC/NetSuite cross-module Signals to discovery candidates |
| 2026-07-23 | Downgrade Fishbowl/Cin7 to validation-only because native accounting and commerce integrations erode the original seam |
