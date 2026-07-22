# Industry × Source System Clusters

**Purpose:** Lump small businesses by **shared source systems** so connector development prioritizes platforms that **span the most industries** — while keeping **QuickBooks + Excel** as the universal layer.

**Companion (full GTM strategy):** [gtm-industry-system-matrix.md](./gtm-industry-system-matrix.md)  
**Canonical product nodes:** [mesh-node-catalog.md](./mesh-node-catalog.md) · [mesh-catalog.md](./mesh-catalog.md) (samples) · [signal-catalog.md](./signal-catalog.md)

**Product spine:** AI-assisted meshflow links multiple systems → trusted operational facts → ranked exceptions (not dashboards).

**Status:** Pre-discovery — validate system frequency in interviews before locking build order.

---

## Design rules

1. **Every customer gets QB + Excel** (slot U1 + U2) — architecture assumption, not upsell.
2. **Third slot = ops system of record** — varies by cluster; drives playbook choice.
3. **Prioritize connectors by cross-cluster span** — NetSuite before JobBOSS; Shopify before Toast.
4. **One spine SKU across clusters** — fulfillment/billing/cash completeness; **wording and entities** change per pack.
5. **Job shop is not the center** — custom MTO shops are a subset of clusters B and C, not a separate universe.

---

## Universal layer (build first — all industries)

| ID | System | Integration | What meshflow pulls |
|---|---|---|---|
| **U1** | **QuickBooks Online** | API | Customers, invoices, payments, AR aging, deposits, GL summary |
| **U1b** | **QuickBooks Desktop** | Scheduled export | Same semantic model as QBO |
| **U2** | **Excel / Google Sheets** | Templated file drop | Shadow ops: holds, allocations, hot lists, manual recon sheets |

**Interview gate:** If accounting ≠ QuickBooks, tag `accounting_other` — v1 playbook TBD or decline.

---

## System-first clusters (connector playbooks)

Industries are grouped by **which ops system they share** — this is the primary driver of **development priority**.

### Playbook 1: `netsuite_qb_excel` — **P1 ops connector**

**System:** NetSuite (+ QBO + Excel)

| Industries in this playbook | Cluster ref |
|---|---|
| Wholesale / industrial **distribution** | A |
| **Product / repetitive manufacturing** | B |
| Hybrid mfg with distributor customers | B |
| Some **professional services** (project NS) | E |
| Larger **multi-channel retail** with ERP | F |
| Light **logistics / 3PL** with NS | G |
| **Staffing** (mid SMB) | J |

**Why P1:** Cloud API; dense **A+B beachhead**; same entity model (SO, item fulfillment, invoice); spans **5+ industry labels** in your target list.

**Hero Signal:** Unbilled / incomplete billing (ship ↔ invoice ↔ QB).

---

### Playbook 2: `bc_qb_excel` — **P2 ops connector**

**System:** Microsoft Dynamics 365 Business Central (+ QBO + Excel)

| Industries | Cluster ref |
|---|---|
| Distribution (especially EU-influenced US SMB) | A |
| Product manufacturing | B |
| Some retail with inventory ERP | F |

**Why P2:** Strong overlap with NetSuite clusters; second playbook for customers without NS.

---

### Playbook 3: `fishbowl_cin7_qb_excel` — **P2b downmarket**

**System:** Fishbowl, Cin7 (+ QBO + Excel)

| Industries | Cluster ref |
|---|---|
| Distribution without NS | A |
| Product mfg / light assembly | B |
| Inventory-heavy SMB | A, B |

**Why P2b:** Same spine as NS; often ODBC/export; downmarket from NS/BC.

---

### Playbook 4: `shopify_qb_excel` — **P3 retail / DTC**

**System:** Shopify (POS + online) (+ QBO + Excel)

| Industries | Cluster ref |
|---|---|
| **Multi-channel retail** | F |
| DTC product brands (often also cluster B mentally) | B, F |
| Some wholesale portal sellers | F |

**Hero Signal:** **Cash recon + channel inventory** — not unbilled shipment (see [retail-problem-opportunity-ranking.md](./retail-problem-opportunity-ranking.md)).

**Why P3 (not P1):** Different hero SKU; POS competition; still huge TAM for wave 2.

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
| **Product manufacturing** | `netsuite_qb_excel` | bc, fishbowl | **5** |
| **Small distribution** | `netsuite_qb_excel` | fishbowl, bc | **5** |
| **Retail (multi-channel)** | `shopify_qb_excel` | square, bc | **3–4** |
| **Construction / trades** | `servicetitan_qb_excel` | jobber, square | **5** |
| **Property management** | `appfolio_buildium` | qb only | **2–3** defer |
| **Professional services** | `psa_qb_excel` | **qb+excel only** | **4** |
| **Logistics / 3PL** | `tms_spreadsheet` | netsuite | **3** defer |
| **Field service** | `servicetitan_qb_excel` | jobber | **5** |
| **Staffing** | `netsuite_qb_excel` | qb+excel | **4** |
| **Job shop (custom mfg)** | netsuite OR legacy ERP | **not headline ICP** | **4** if ERP↔QB split |

---

## Connector build order (development priority)

Based on **industries touched × API quality × spine fit**:

```
PHASE 0 — Universal (every customer)
  ├── QuickBooks Online API
  ├── QuickBooks Desktop export playbook
  └── Excel/Sheets template ingest (holds, allocations, recon)

PHASE 1 — Beachhead (product mfg + distribution)
  └── NetSuite API playbook
      Entities: customer, SO, item fulfillment, invoice line
      Spine SKU: unbilled / incomplete billing

PHASE 2 — Same spine, alternate ERP
  ├── Dynamics 365 Business Central
  └── Fishbowl OR Cin7 (pick one downmarket)

PHASE 3 — Wave 2 vertical (pick ONE based on discovery)
  ├── ServiceTitan (trades + field service)  OR
  └── Shopify (multi-channel retail)

PHASE 4 — Expand
  ├── Square (+ Gusto for labor SKU)
  ├── Jobber / Housecall Pro
  └── PSA (Harvest / BQE)

DEFER
  ├── AppFolio / Buildium (property mgmt)
  ├── Toast (restaurant)
  └── TMS variants (logistics)
```

**Rule:** Max **one new ops family per quarter** after Phase 0.

---

## Industries you asked about — honest fit

### Retail
- **Fit:** Multi-channel + QB split → **strong** for cash recon, inventory mismatch, labor %.
- **Playbook:** Shopify or Square + QB + Excel.
- **Detail:** [retail-problem-opportunity-ranking.md](./Industry-opportunities/retail-problem-opportunity-ranking.md)

### Construction / trades
- **Fit:** **Excellent** — completed work not invoiced; change orders; QB almost always separate.
- **Playbook:** ServiceTitan or Jobber + QB + Excel.
- **Wave:** 2 (after NS beachhead) unless discovery pulls you here first.
- **Detail:** [trades-construction-problem-opportunity-ranking.md](./Industry-opportunities/trades-construction-problem-opportunity-ranking.md)

### Property management
- **Fit:** **Moderate-defer** — AppFolio/Buildium often owns rent roll; pain is delinquency, turns, vendor bills — different SKU.
- **Playbook:** Defer unless interviews show heavy QB + spreadsheet reconciliation outside PM tool.

### Professional services
- **Fit:** **Good** — unbilled hours/WIP; often **QB + Excel only** for v1 without PSA API.
- **Playbook:** Start `qb_excel` unbilled time template; add Harvest/BQE when repeated.

### Logistics
- **Fit:** **Moderate-defer** — billing on scans/contracts; TMS specialization; less universal QB+Excel+ERP pattern at SMB size.
- **Playbook:** Defer; revisit for NS-using small 3PLs only.

---

## One spine, many packs (GTM product shape)

```
                    ┌─────────────────────────────┐
                    │  SPINE: Cash / billing      │
                    │  completeness exceptions    │
                    │  (QB + Excel + ops event)   │
                    └──────────────┬──────────────┘
                                   │
     ┌─────────────┬───────────────┼───────────────┬─────────────┐
     ▼             ▼               ▼               ▼             ▼
  dist pack    product_mfg     trades pack      retail pack    pro_svc pack
  (NS)         (NS)            (ServiceTitan)   (Shopify)      (QB+Excel)
  backorder    fill/FG         job complete     cash recon     unbilled WIP
  OTIF         unbilled ship    not invoiced     channel inv    hours
```

**External message (all clusters):**  
*We connect how work gets done to QuickBooks and show what’s costing you money today.*

**Never lead with:** job shop, data platform, analytics, AI chat.

---

## Discovery fields (log on every call)

| Field | Example values |
|---|---|
| `cluster` | A, B, C, D, E, F, G, H, I, J |
| `playbook` | netsuite_qb_excel, shopify_qb_excel, … |
| `accounting` | qbo, qbd, other |
| `ops_system` | netsuite, bc, shopify, square, servicetitan, appfolio, other |
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
