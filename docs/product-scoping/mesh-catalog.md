# Meshflow — Mesh Catalog (samples)

**Purpose:** Sample **Meshes** — named compositions of Mesh nodes from [mesh-node-catalog.md](./mesh-node-catalog.md). Use these as discovery/SOW starting points. They are **patterns**, not locked product SKUs: swap nodes when the client’s stack differs.

**Definitions:**  
| Term | Meaning |
|---|---|
| **Mesh node** | One source system (`SYS-…`) — see [mesh-node-catalog.md](./mesh-node-catalog.md) |
| **Mesh** | A selected node set + semantic join path across systems or full-ERP module domains |
| **Signal** | Insight pack on that Mesh — see [signal-catalog.md](./signal-catalog.md) |

**Status:** Working library of candidate stacks. A+B remains the provisional ICP; BC and NetSuite cross-module Meshes are the leading Phase 1 hypotheses. Fishbowl/Cin7 Meshes are validation-only.

---

## How to read a sample Mesh

| Field | Meaning |
|---|---|
| **Mesh sample ID** | Short label for internal reference (`MESH-…`) — optional on SOW; prefer descriptive name |
| **Nodes** | System IDs from the Mesh node catalog |
| **Join path** | Primary semantic link |
| **Industry tags** | Clusters where this composition is common |
| **Hero Signal** | Usual launch Signal |
| **Strong follow-ons** | Next Signals once hero works |
| **Wave** | When this composition is a priority GTM play |

**SOW tip:** Write the Mesh as node names (`Fishbowl + QuickBooks Online + Excel`) and list System IDs in Section 3 slots — you do not need the `MESH-…` ID on the contract.

**Composition rule:** Discover the system path before composing the Mesh. Split-stack customers use **ops/FSM/commerce/PSA + QuickBooks + Excel**. NetSuite and Business Central customers may use a **single full-ERP node with cross-module join paths**; Excel/satellites are optional extensions, and QuickBooks is usually absent.

---

## Industry tag legend

**A** Dist · **B** Product mfg · **B-js** Job shop · **C** Trades · **D** Field svc · **E** Pro svc · **F** Retail · **G** Logistics · **H** Prop mgmt · **I** Restaurant · **J** Staffing

---

## Sample index

| Sample ID | Display name | Nodes | Industries | Hero Signal | Wave |
|---|---|---|---|---|---|
| `MESH-FB-QB` | Fishbowl + QBO + Excel | `SYS-FISHBOWL` · `SYS-QBO` · `SYS-EXCEL` | **A, B** | Discovery-selected | **Validate only** |
| `MESH-CIN7-QB` | Cin7 + QBO/Xero + commerce | `SYS-CIN7` · `SYS-QBO`/`SYS-XERO` · optional `SYS-SHOPIFY`/`SYS-EXCEL` | **A, B, F** | Discovery-selected | **Validate only** |
| `MESH-NS-INTRA` | NetSuite cross-module | `SYS-NETSUITE` (+ `SYS-EXCEL`/satellite optional) | **A, B** | Discovery-selected | **Phase 1 candidate** |
| `MESH-BC-INTRA` | Business Central cross-module | `SYS-BC` (+ `SYS-EXCEL`/satellite optional) | **A, B, F** | Discovery-selected | **Phase 1 candidate** |
| `MESH-LEGACY-QB` | Legacy job ERP + QBO + Excel | `SYS-JOBBOSS` (or Epicor/Global Shop) · `SYS-QBO` · `SYS-EXCEL` | **B-js** | `SIG-BILL-01` | Later |
| `MESH-ST-QB` | ServiceTitan + QBO + Excel | `SYS-SERVICETITAN` · `SYS-QBO` · `SYS-EXCEL` | **C, D** | `SIG-BILL-01` | **P4** |
| `MESH-JOBBER-QB` | Jobber + QBO + Excel | `SYS-JOBBER` · `SYS-QBO` · `SYS-EXCEL` | **C** | `SIG-BILL-01` | **P4** |
| `MESH-HCP-QB` | Housecall Pro + QBO + Excel | `SYS-HCP` · `SYS-QBO` · `SYS-EXCEL` | **C** | `SIG-BILL-01` | **P4** |
| `MESH-OPTSY-QB` | Optsy + QBO + Excel | `SYS-OPTSY` · `SYS-QBO` · `SYS-EXCEL` | **C** (HVAC) | `SIG-MEM-01` / `SIG-BILL-01` | **P4** |
| `MESH-ACCULYNX-QB` | AccuLynx + QBO + Excel | `SYS-ACCULYNX` · `SYS-QBO` · `SYS-EXCEL` | **C** (roofing) | `SIG-BILL-01` | Later |
| `MESH-SHOPIFY-QB` | Shopify + QBO + Excel | `SYS-SHOPIFY` · `SYS-QBO` · `SYS-EXCEL` | **F** | `SIG-CASH-01` | **P3** |
| `MESH-SQUARE-QB` | Square + QBO + Excel | `SYS-SQUARE` · `SYS-QBO` · `SYS-EXCEL` | **F, C** | `SIG-CASH-01` | **P3** |
| `MESH-SQUARE-GUSTO` | Square + QBO + Gusto | `SYS-SQUARE` · `SYS-QBO` · `SYS-GUSTO` (+ Excel optional) | **F** | `SIG-CASH-01` + `SIG-LABOR-02` | **P3** |
| `MESH-HARVEST-QB` | Harvest + QBO + Excel | `SYS-HARVEST` · `SYS-QBO` · `SYS-EXCEL` | **E** | `SIG-WIP-01` | **P5** |
| `MESH-BQE-QB` | BQE + QBO + Excel | `SYS-BQE` · `SYS-QBO` · `SYS-EXCEL` | **E** | `SIG-WIP-01` | **P5** |
| `MESH-QB-EXCEL` | QuickBooks + Excel only | `SYS-QBO` · `SYS-EXCEL` | **E, J**, thin | `SIG-AR-01` | **P0** |

---

## Sample cards

### `MESH-FB-QB` / `MESH-CIN7-QB` — Native-integrated split stacks ★ Validate only

| | |
|---|---|
| **Nodes** | Fishbowl + QBO, or Cin7 + QBO/Xero (+ Shopify/Excel when material) |
| **Join path** | Native order / fulfillment / inventory → accounting transaction flow; optional commerce → Cin7 → accounting chain |
| **Industry tags** | **A, B** |
| **Hero Signal** | None assumed. Test integration assurance, billing/tax/COGS reconciliation, or an unsolved operational queue. |
| **Strong follow-ons** | Only Signals that native integration and system reports do not already operationalize |
| **Wave** | **Validate only** — no connector hardening without measured recurring failures and dollar exposure |
| **SOW name** | Native Integration Assurance *(only if discovery validates)* |
| **Notes** | Fishbowl and Cin7 already provide accounting integrations; Cin7 also integrates commerce channels. Do not sell basic connectivity. Built-in sync status/error tools further narrow the wedge. |

---

### `MESH-NS-INTRA` — NetSuite cross-module

| | |
|---|---|
| **Nodes** | M1 `SYS-NETSUITE`; optional M2 `SYS-EXCEL` or satellite (no QB by default) |
| **Join path** | Sales order / item fulfillment / shipment ↔ invoice / credit / payment across NetSuite transaction domains; optional shadow holds |
| **Industry tags** | **A, B** (also touches E/F/G/J when NS is present) |
| **Hero Signal** | Discovery-selected: billing completeness, OTIF/backorder, inventory, or margin exception |
| **Strong follow-ons** | `SIG-BILL-02`, `SIG-AR-01`, `SIG-BO-01`, `SIG-OTIF-01`, `SIG-STOCK-01` |
| **Wave** | **Phase 1 candidate** — do not build in parallel with BC |
| **SOW name** | NetSuite Cross-Module Operational Control |
| **Notes** | NetSuite usually **replaces** QB. Value must come from repeatable cross-module facts, historical state, ranked exceptions, or optional Excel/satellite workflows—not generic custom reporting. |

---

### `MESH-BC-INTRA` — Business Central cross-module

| | |
|---|---|
| **Nodes** | M1 `SYS-BC`; optional M2 `SYS-EXCEL` or satellite (no QB by default) |
| **Join path** | Sales order / posted shipment ↔ invoice / credit / payment across BC domains; optional shadow workflows |
| **Industry tags** | **A, B, F** |
| **Hero Signal** | Discovery-selected: billing completeness, OTIF/backorder, inventory, or margin exception |
| **Wave** | **Phase 1 candidate** — do not build in parallel with NetSuite |
| **Notes** | BC replaces QB; do not assume a QB node. Test packaged cross-module operational-control needs and Excel/satellite workflows. |

---

### `MESH-LEGACY-QB` — Legacy job ERP + QBO + Excel

| | |
|---|---|
| **Nodes** | M1 `SYS-JOBBOSS` / `SYS-EPICOR` / `SYS-GLOBALSHOP` / `SYS-SAGE100` · M2 QB · M3 Excel |
| **Join path** | Job / ship complete ↔ QB invoice |
| **Industry tags** | **B-js**, some **B**, Sage also **C** |
| **Hero Signal** | `SIG-BILL-01` |
| **Wave** | Later |
| **Notes** | Access friction (file/ODBC); opportunistic when discovery pulls it |

---

### `MESH-ST-QB` — ServiceTitan + QBO + Excel

| | |
|---|---|
| **Nodes** | M1 `SYS-SERVICETITAN` · M2 QB · M3 Excel |
| **Join path** | Job / WO complete ↔ QB invoice; membership ↔ visit |
| **Industry tags** | **C, D** |
| **Hero Signal** | `SIG-BILL-01` |
| **Strong follow-ons** | `SIG-CO-01`, `SIG-PART-01`, `SIG-LABOR-01`, `SIG-MEM-01`, `SIG-AR-01` |
| **Wave** | **P4** |
| **SOW name** | ServiceTitan + QuickBooks Online + Excel |

---

### `MESH-JOBBER-QB` / `MESH-HCP-QB` — Jobber or Housecall Pro + QBO + Excel

| | |
|---|---|
| **Nodes** | M1 `SYS-JOBBER` or `SYS-HCP` · M2 QB · M3 Excel |
| **Join path** | Same as ServiceTitan (often thinner data) |
| **Industry tags** | **C** |
| **Hero Signal** | `SIG-BILL-01` |
| **Wave** | **P4** |
| **Notes** | Downmarket trades / home services |

---

### `MESH-OPTSY-QB` — Optsy + QBO + Excel

| | |
|---|---|
| **Nodes** | M1 `SYS-OPTSY` · M2 QB · M3 Excel |
| **Join path** | Job / membership ↔ QB invoice & AR |
| **Industry tags** | **C** (HVAC / membership-heavy) |
| **Hero Signal** | `SIG-MEM-01` or `SIG-BILL-01` (probe both in discovery) |
| **Strong follow-ons** | `SIG-MEM-02`, `SIG-AR-01`, `SIG-NEW-01` |
| **Wave** | **P4** |
| **SOW name** | Optsy + QuickBooks Online + Excel |

---

### `MESH-ACCULYNX-QB` — AccuLynx + QBO + Excel

| | |
|---|---|
| **Nodes** | M1 `SYS-ACCULYNX` · M2 QB · M3 Excel |
| **Join path** | Job / WO ↔ invoice; CO-heavy roofing |
| **Industry tags** | **C** (roofing) |
| **Hero Signal** | `SIG-BILL-01` |
| **Follow-ons** | `SIG-CO-01`, `SIG-BILL-03` |
| **Wave** | Later |

---

### `MESH-SHOPIFY-QB` — Shopify + QBO + Excel

| | |
|---|---|
| **Nodes** | M1 `SYS-SHOPIFY` · M2 QB · M3 Excel |
| **Join path** | Order / channel sales ↔ deposits & cash; channel inventory |
| **Industry tags** | **F**, some **B** DTC |
| **Hero Signal** | `SIG-CASH-01` |
| **Strong follow-ons** | `SIG-INV-02`, `SIG-MARGIN-04`, `SIG-AR-01` (if B2B) |
| **Wave** | **P3** |
| **Notes** | Different hero than ERP/FSM Meshes — not unbilled ship |

---

### `MESH-SQUARE-QB` — Square + QBO + Excel

| | |
|---|---|
| **Nodes** | M1 `SYS-SQUARE` · M2 QB · M3 Excel |
| **Join path** | POS batch ↔ QB deposit |
| **Industry tags** | **F**, small **C**, lite **D**, **I** (weak spine) |
| **Hero Signal** | `SIG-CASH-01` |
| **Wave** | **P3** |

---

### `MESH-SQUARE-GUSTO` — Square + QBO + Gusto

| | |
|---|---|
| **Nodes** | M1 `SYS-SQUARE` · M2 `SYS-QBO` · M4 `SYS-GUSTO` (Excel optional as M3) |
| **Join path** | POS ↔ deposit; payroll hours ↔ sales by location/day |
| **Industry tags** | **F** |
| **Hero Signal** | `SIG-CASH-01` + `SIG-LABOR-02` |
| **Wave** | **P3** |
| **Notes** | Example of intentional M4; price fourth system in SOW |

---

### `MESH-HARVEST-QB` / `MESH-BQE-QB` — PSA + QBO + Excel

| | |
|---|---|
| **Nodes** | M1 `SYS-HARVEST` or `SYS-BQE` · M2 QB · M3 Excel |
| **Join path** | Time / WIP / project ↔ QB invoice |
| **Industry tags** | **E** |
| **Hero Signal** | `SIG-WIP-01` |
| **Follow-ons** | `SIG-AR-01`, `SIG-NEW-01` |
| **Wave** | **P5** |
| **Notes** | Often start on `MESH-QB-EXCEL` first, add PSA when pain repeats |

---

### `MESH-QB-EXCEL` — QuickBooks + Excel only

| | |
|---|---|
| **Nodes** | M2 `SYS-QBO`/`SYS-QBD` · M3 `SYS-EXCEL` (no ops M1) |
| **Join path** | AR, cash, shadow-ops Excel ↔ QB facts |
| **Industry tags** | **E, J**, thin **C**, early pilots |
| **Hero Signal** | `SIG-AR-01`; templated unbilled time → `SIG-WIP-01` |
| **Wave** | **P0** (always available) |
| **Notes** | Weakest Meshflow novelty alone — land then add an ops node |

---

## By industry (quick pick)

| Industry | Start with sample | Alternate |
|---|---|---|
| **A Dist** | **Primary hypothesis:** `MESH-BC-INTRA` or `MESH-NS-INTRA` | `MESH-FB-QB` / `MESH-CIN7-QB` only after native-gap validation |
| **B Product mfg** | **Primary hypothesis:** `MESH-BC-INTRA` or `MESH-NS-INTRA` | `MESH-FB-QB` / `MESH-CIN7-QB` only after native-gap validation |
| **B-js Job shop** | `MESH-LEGACY-QB` | `MESH-QB-EXCEL` |
| **C Trades** | `MESH-ST-QB` | `MESH-JOBBER-QB`, `MESH-OPTSY-QB`, `MESH-HCP-QB` |
| **D Field svc** | `MESH-ST-QB` | `MESH-JOBBER-QB` |
| **E Pro svc** | `MESH-QB-EXCEL` → `MESH-HARVEST-QB` | `MESH-BQE-QB` |
| **F Retail** | `MESH-SHOPIFY-QB` | `MESH-SQUARE-QB`, `MESH-SQUARE-GUSTO` |
| **G / H / I** | Prefer defer — or `MESH-QB-EXCEL` / full-ERP Excel mesh if stack fits | See node catalog |

---

## Deferred compositions (do not lead)

| Pattern | Nodes | Why defer |
|---|---|---|
| NetSuite + QB (+ Excel) | `SYS-NETSUITE` + QB | Rare: migration dual-run, parent/sub, or acquisition — not the default NS stack |
| Business Central + QB (+ Excel) | `SYS-BC` + QB | Same as NS — BC usually replaces QB |
| AppFolio/Buildium + QB | `SYS-APPFOLIO` / `SYS-BUILDIUM` + QB | Different spine (rent / delinquency) |
| Toast + QB | `SYS-TOAST` + QB | Weak fulfillment↔invoice gap |
| TMS + spreadsheets | `SYS-MAGAYA` + Excel + QB | Specialized; small ICP overlap |

Add formal sample cards only when discovery validates a repeatable play.

---

## Related

- [mesh-node-catalog.md](./mesh-node-catalog.md) — all Mesh nodes (`SYS-…`)
- [signal-catalog.md](./signal-catalog.md) — Signals and required roles
- [sow-template-meshflow.md](../terms/sow-template-meshflow.md)

---

## Revision log

| Date | Change |
|---|---|
| 2026-07-20 | Initial sample Mesh catalog (compositions from Mesh nodes) |
| 2026-07-21 | Hero/follow-on Wedge → Signal (`SIG-*`) |
| 2026-07-23 | Beachhead → Fishbowl/Cin7 + QB; NS/BC are full ERP (+ Excel), not + QB |
| 2026-07-23 | Keep A+B ICP but reopen Phase 1 Mesh across split-stack, BC, and NetSuite candidates |
| 2026-07-23 | Downgrade Fishbowl/Cin7 Meshes to validation-only because native integrations cover the original connectivity seam |
