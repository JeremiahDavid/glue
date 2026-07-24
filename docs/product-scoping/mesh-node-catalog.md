# Meshflow — Mesh Node Catalog

**Purpose:** Canonical list of **Mesh nodes**—individual **source systems** that can be connected into a Mesh. A Mesh is composed at deal time from 1–4 nodes; a single full-ERP node can expose multiple module domains.

**Definitions (SOW):** See [sow-template-meshflow.md](../terms/sow-template-meshflow.md) §1.1
| Term | Meaning |
|---|---|
| **Mesh node** | One cataloged source system (`SYS-…`) Meshflow can ingest |
| **Mesh** | The selected node set + semantic join path across systems or full-ERP module domains—see [mesh-catalog.md](./mesh-catalog.md) |
| **Signal** | Insight pack that runs on a Mesh (see [signal-catalog.md](./signal-catalog.md)) |

**Companions:** [mesh-catalog.md](./mesh-catalog.md) (sample Meshes) · [signal-catalog.md](./signal-catalog.md) · [industry-system-clusters.md](../industry-system-clusters.md) · [gtm-industry-system-matrix.md](../gtm-industry-system-matrix.md)

**Status:** Product catalog — SOW Section 3 lists concrete systems by **System ID** from this file. Connector build order follows **Build wave**.

---

## How Meshes are composed

```
Mesh (per deal)  =  1–4 Mesh nodes from this catalog
                     usually:  Ops/FSM/Commerce/PSA  +  QuickBooks  +  Excel
                     full ERP: NetSuite or BC cross-module; Excel/satellites optional (not + QB)
```

| Rule | Detail |
|---|---|
| **Default size** | Up to **3** systems (M1–M3); a full-ERP playbook may use one source node with multiple module domains |
| **M4** | Optional extension (payroll, pricing, ads) — only if priced in SOW |
| **Sample Meshes** | Common compositions live in [mesh-catalog.md](./mesh-catalog.md) — starting points, not mandatory SKUs |
| **Accounting gate** | Discover accounting explicitly. QB enables split-stack playbooks; NetSuite/BC enable full-ERP playbooks (`MESH-NS-INTRA` / `MESH-BC-INTRA`), not + QB. If accounting = other, tag `accounting_other` and measure frequency before promising a connector. |
| **New systems** | Add a System ID here **before** putting it on a customer SOW |

---

## How to read a Mesh node

| Field | Meaning |
|---|---|
| **System ID** | Stable ID for SOW / scoring / connectors (`SYS-…`) |
| **Role** | Slot this system usually fills: Accounting · Ops ERP · Full ERP · FSM · Commerce · PSA · Payroll · Shadow · PM · TMS · Other |
| **Industry tags** | Clusters **A–J** where this system commonly appears |
| **Entities exposed** | What Meshflow typically pulls for joins |
| **Integration** | API / export / ODBC / file — working assumption |
| **Build wave** | Connector priority (P0–P5, Later, Defer) |
| **Pairs with** | Roles it usually joins to (ops nodes → Accounting + Shadow; full ERP → no required pair, optional Shadow/satellite) |

---

## Industry tag legend

| Tag | Cluster | Short name |
|---|---|---|
| **A** | Wholesale / distribution | Dist |
| **B** | Product / repetitive manufacturing | Product mfg |
| **B-js** | Job-shop / custom MTO (subset of B) | Job shop |
| **C** | Trades / construction (SMB) | Trades |
| **D** | Field service & equipment | Field svc |
| **E** | Professional services | Pro svc |
| **F** | Retail (multi-channel) | Retail |
| **G** | Logistics / delivery (SMB) | Logistics |
| **H** | Property management (SMB) | Prop mgmt |
| **I** | Restaurants / hospitality | Restaurant |
| **J** | Staffing / light workforce | Staffing |

---

## Index — all Mesh nodes

| System ID | Name | Role | Industry tags | Wave |
|---|---|---|---|---|
| `SYS-QBO` | QuickBooks Online | Accounting | **A–J** | **P0** |
| `SYS-QBD` | QuickBooks Desktop | Accounting | **A–J** | **P0** |
| `SYS-EXCEL` | Excel / Google Sheets | Shadow | **A–J** | **P0** |
| `SYS-FISHBOWL` | Fishbowl | Ops ERP | **A, B** | **Validate only** |
| `SYS-CIN7` | Cin7 | Ops / commerce hub | **A, B, F** | **Validate only** |
| `SYS-NETSUITE` | NetSuite | Full ERP | **A, B, E, F, G, J** | **Phase 1 candidate** |
| `SYS-BC` | Dynamics 365 Business Central | Full ERP | **A, B, F**, some **C** | **Phase 1 candidate** |
| `SYS-ACUMATICA` | Acumatica | Full ERP | **A, B** | Later |
| `SYS-EPICOR` | Epicor | Ops ERP | **B, B-js** | Later |
| `SYS-JOBBOSS` | JobBOSS / E2 | Ops ERP | **B-js** | Later |
| `SYS-GLOBALSHOP` | Global Shop | Ops ERP | **B-js** | Later |
| `SYS-SAGE100` | Sage 100 / Sage 100 Contractor | Ops ERP | **B-js, C** | Later |
| `SYS-SERVICETITAN` | ServiceTitan | FSM | **C, D** | **P4** |
| `SYS-JOBBER` | Jobber | FSM | **C**, home services | **P4** |
| `SYS-HCP` | Housecall Pro | FSM | **C** | **P4** |
| `SYS-OPTSY` | Optsy | FSM | **C** (HVAC) | **P4** |
| `SYS-ACCULYNX` | AccuLynx | FSM | **C** (roofing) | Later |
| `SYS-SERVICEFUSION` | Service Fusion | FSM | **C, D** | Later |
| `SYS-FIELDEDGE` | FieldEdge | FSM | **D** | Later |
| `SYS-SHOPIFY` | Shopify | Commerce | **F**, some **B** DTC | **P3** |
| `SYS-SQUARE` | Square | Commerce | **F, C, D, I** | **P3** |
| `SYS-LIGHTSPEED` | Lightspeed | Commerce | **F** | **P5** |
| `SYS-CLOVER` | Clover | Commerce | **F** | **P5** |
| `SYS-HARVEST` | Harvest | PSA | **E** | **P5** |
| `SYS-BQE` | BQE Core | PSA | **E** | **P5** |
| `SYS-MAVENLINK` | Mavenlink / Kantata | PSA | **E** | Later |
| `SYS-GUSTO` | Gusto | Payroll | **F, C, E, J** | **P3** (w/ Square labor) |
| `SYS-ADP` | ADP | Payroll | Broad | Later |
| `SYS-APPFOLIO` | AppFolio | PM | **H** | Defer |
| `SYS-BUILDIUM` | Buildium | PM | **H** | Defer |
| `SYS-RENTMANAGER` | Rent Manager | PM | **H** | Defer |
| `SYS-TOAST` | Toast | Commerce | **I** | Defer |
| `SYS-MAGAYA` | Magaya / TMS lite | TMS | **G** | Defer |
| `SYS-XERO` | Xero | Accounting | Broad (non-US skew) | Later / other |
| `SYS-SAGE-INTACCT` | Sage Intacct | Accounting | Mid-market | Later |
| `SYS-PROFITRHINO` | Profit Rhino | Other (pricing) | **C** | Optional M4 |
| `SYS-GA4` | Google Analytics 4 | Other (marketing) | **F, C** | Optional M4 — weak |

---

## Catalog by role

### Accounting (almost always M2)

#### `SYS-QBO` — QuickBooks Online

| | |
|---|---|
| **Role** | Accounting |
| **Industry tags** | **A–J** (broad, not assumed for every ICP account) |
| **Entities** | Customers, invoices, payments, AR aging, deposits, vendors, expenses |
| **Integration** | API |
| **Build wave** | **P0** |
| **Pairs with** | Every ops / FSM / commerce / PSA / shadow node |
| **Notes** | Spine dependency for almost all Signals |

#### `SYS-QBD` — QuickBooks Desktop

| | |
|---|---|
| **Role** | Accounting |
| **Industry tags** | **A–J** (legacy SMB) |
| **Entities** | Same semantic model as QBO |
| **Integration** | Scheduled export |
| **Build wave** | **P0** |
| **Notes** | Same Signal definitions as QBO once mapped |

#### `SYS-XERO` — Xero

| | |
|---|---|
| **Role** | Accounting |
| **Industry tags** | Broad; less US SMB default |
| **Build wave** | Later |
| **Notes** | Tag `accounting_other` until connector exists |

#### `SYS-SAGE-INTACCT` — Sage Intacct

| | |
|---|---|
| **Role** | Accounting |
| **Industry tags** | Mid-market up |
| **Build wave** | Later |
| **Notes** | Longer sales; overlaps NetSuite customers |

---

### Shadow ops (almost always M3)

#### `SYS-EXCEL` — Excel / Google Sheets

| | |
|---|---|
| **Role** | Shadow |
| **Industry tags** | **A–J** |
| **Entities** | Holds, allocations, CO lists, price lists, membership rosters, recon sheets, spend |
| **Integration** | Templated file drop |
| **Build wave** | **P0** |
| **Notes** | First-class source — not a failure state |

---

### Ops ERP (typical M1 — mfg / distribution; pairs with QuickBooks)

#### `SYS-FISHBOWL` — Fishbowl · `SYS-CIN7` — Cin7

| | |
|---|---|
| **Role** | Ops ERP |
| **Industry tags** | **A, B** |
| **Entities** | Inventory, SO, shipments |
| **Integration** | Often ODBC / export; Cin7 more API-friendly |
| **Build wave** | **Validate only** — native accounting integrations cover core transaction flow |
| **Pairs with** | `SYS-QBO`/`SYS-QBD` + `SYS-EXCEL` |
| **Hero Signals** | `SIG-BILL-01`, `SIG-BILL-02`, `SIG-BO-01`, `SIG-OTIF-01`, `SIG-STOCK-01` |
| **Notes** | Fishbowl exports fulfilled transactions and accounting entries to QBO. Cin7 connects QBO/Xero and commerce channels such as Shopify. Require evidence of recurring integration-control or operational gaps beyond their built-in sync/error tooling. |

#### `SYS-EPICOR` · `SYS-JOBBOSS` · `SYS-GLOBALSHOP` · `SYS-SAGE100`

| | |
|---|---|
| **Role** | Ops ERP (legacy / job-centric) |
| **Industry tags** | **B-js**, some **B**, Sage 100 also **C** |
| **Entities** | Jobs, WOs, shipments, costing (variable quality) |
| **Integration** | File / ODBC — access friction |
| **Build wave** | Later — not headline beachhead |
| **Pairs with** | `SYS-QBO`/`SYS-QBD` + `SYS-EXCEL` |
| **Hero Signals** | `SIG-BILL-01` when QB is separate |

---

### Full ERP (ops + accounting — usually replaces QuickBooks)

#### `SYS-NETSUITE` — NetSuite

| | |
|---|---|
| **Role** | Full ERP |
| **Industry tags** | **A, B**, some **E, F, G, J** |
| **Entities** | Customers, SO, SO lines, item fulfillment / shipments, items, inventory, invoices, AR |
| **Integration** | Cloud API |
| **Build wave** | **Phase 1 candidate** — choose one of NetSuite, BC, or split-stack; do not build all |
| **Pairs with** | No second node required; `SYS-EXCEL`/satellites optional. **Do not** assume `SYS-QBO`—NS usually replaces QB. |
| **Hero Signals** | Discovery-selected cross-module pack: `SIG-BILL-01`, `SIG-BILL-02`, `SIG-BO-01`, `SIG-OTIF-01`, `SIG-STOCK-01`, or margin |
| **Notes** | Sample Mesh: `MESH-NS-INTRA`. Dual-run NS+QB only for migration / multi-entity—see deferred in mesh-catalog. |

#### `SYS-BC` — Dynamics 365 Business Central

| | |
|---|---|
| **Role** | Full ERP |
| **Industry tags** | **A, B, F**, some **C** |
| **Entities** | Same family as NetSuite (SO / ship / inventory / invoices / AR) |
| **Integration** | SaaS API |
| **Build wave** | **Phase 1 candidate** — choose one of BC, NetSuite, or split-stack; do not build all |
| **Pairs with** | No second node required; `SYS-EXCEL`/satellites optional. **Do not** assume `SYS-QBO`. |
| **Hero Signals** | Same as NetSuite family |
| **Notes** | Sample Mesh: `MESH-BC-INTRA` |

#### `SYS-ACUMATICA` — Acumatica

| | |
|---|---|
| **Role** | Full ERP |
| **Industry tags** | **A, B** |
| **Build wave** | Later |
| **Pairs with** | `SYS-EXCEL` (default); same anti-pattern as NS/BC + QB |

---

### Field service / trades FSM (typical M1 — trades)

#### `SYS-SERVICETITAN` — ServiceTitan

| | |
|---|---|
| **Role** | FSM |
| **Industry tags** | **C, D** |
| **Entities** | Jobs/WOs, status/complete, customers, memberships, job materials/labor, invoices (if used) |
| **Integration** | API |
| **Build wave** | **P4** (wave 2) |
| **Pairs with** | `SYS-QBO`/`SYS-QBD` + `SYS-EXCEL` |
| **Hero Signals** | `SIG-BILL-01`, `SIG-CO-01`, `SIG-PART-01`, `SIG-LABOR-01`, `SIG-MEM-01` |

#### `SYS-JOBBER` — Jobber · `SYS-HCP` — Housecall Pro

| | |
|---|---|
| **Role** | FSM |
| **Industry tags** | **C** (Jobber also landscaping/pest/cleaning adjacent) |
| **Build wave** | **P4** |
| **Notes** | Downmarket trades; thinner data than ServiceTitan |

#### `SYS-OPTSY` — Optsy

| | |
|---|---|
| **Role** | FSM |
| **Industry tags** | **C** (HVAC / membership-heavy) |
| **Build wave** | **P4** |
| **Strong Signals** | `SIG-MEM-01`, `SIG-MEM-02`, `SIG-BILL-01`, `SIG-AR-01` |

#### `SYS-ACCULYNX` · `SYS-SERVICEFUSION` · `SYS-FIELDEDGE`

| | |
|---|---|
| **Role** | FSM |
| **Industry tags** | AccuLynx **C** roofing · Service Fusion **C, D** · FieldEdge **D** |
| **Build wave** | Later |

---

### Commerce / POS (typical M1 — retail)

#### `SYS-SHOPIFY` — Shopify

| | |
|---|---|
| **Role** | Commerce |
| **Industry tags** | **F**, some **B** (DTC) |
| **Entities** | Orders, line items, refunds, inventory by channel, customers, payouts |
| **Integration** | API |
| **Build wave** | **P3** |
| **Hero Signals** | `SIG-CASH-01`, `SIG-INV-02` (not unbilled ship) |

#### `SYS-SQUARE` — Square

| | |
|---|---|
| **Role** | Commerce |
| **Industry tags** | **F, C** (small), **D** lite, **I** |
| **Entities** | Payments, batches, fees, items, locations |
| **Integration** | API |
| **Build wave** | **P3** |
| **Hero Signals** | `SIG-CASH-01`; with `SYS-GUSTO` → `SIG-LABOR-02` |

#### `SYS-LIGHTSPEED` · `SYS-CLOVER`

| | |
|---|---|
| **Role** | Commerce |
| **Industry tags** | **F** |
| **Build wave** | **P5** |

#### `SYS-TOAST` — Toast

| | |
|---|---|
| **Role** | Commerce |
| **Industry tags** | **I** |
| **Build wave** | **Defer** — weak fulfillment↔invoice spine |

---

### Professional services (PSA)

#### `SYS-HARVEST` · `SYS-BQE` · `SYS-MAVENLINK`

| | |
|---|---|
| **Role** | PSA |
| **Industry tags** | **E** |
| **Entities** | Time, projects, WIP, clients |
| **Build wave** | Harvest/BQE **P5**; Mavenlink Later |
| **Hero Signals** | `SIG-WIP-01` |
| **Notes** | Often start with QB + Excel only, add PSA when pain repeats |

---

### Payroll (optional M4)

#### `SYS-GUSTO` — Gusto

| | |
|---|---|
| **Role** | Payroll |
| **Industry tags** | **F, C, E, J** |
| **Build wave** | **P3** when paired for labor % |
| **Enables** | `SIG-LABOR-02` |

#### `SYS-ADP` — ADP

| | |
|---|---|
| **Role** | Payroll |
| **Build wave** | Later |

---

### Property management (defer)

#### `SYS-APPFOLIO` · `SYS-BUILDIUM` · `SYS-RENTMANAGER`

| | |
|---|---|
| **Role** | PM |
| **Industry tags** | **H** |
| **Build wave** | **Defer** — rent billing often inside PM tool; different spine |

---

### Logistics (defer)

#### `SYS-MAGAYA` — Magaya / TMS lite

| | |
|---|---|
| **Role** | TMS |
| **Industry tags** | **G** |
| **Build wave** | **Defer** — prefer NetSuite path if present |

---

### Optional extensions (M4)

#### `SYS-PROFITRHINO` — Profit Rhino

| | |
|---|---|
| **Role** | Other (pricing) |
| **Industry tags** | **C** |
| **Notes** | Only when Mesh allows M4 and SOW prices it |

#### `SYS-GA4` — Google Analytics 4

| | |
|---|---|
| **Role** | Other (marketing) |
| **Industry tags** | **F, C** |
| **Notes** | Weak for Meshflow; thin spend→revenue only via Excel spend + `SIG-MKT-01` |

---

## Industry × system heat map

**Legend:** ●●● = primary · ●● = common · ● = sometimes · — = rare

| Industry | QBO/QBD | Excel | Fishbowl/Cin7 | NetSuite | BC | ServiceTitan/Jobber | Shopify | Square | PSA | AppFolio |
|---|---|---|---|---|---|---|---|---|---|---|
| **A Dist** | ●●● | ●●● | ●●● | ●● | ●● | — | ● | — | — | — |
| **B Product mfg** | ●●● | ●●● | ●● | ●● | ●● | — | ● | — | — | — |
| **B-js Job shop** | ●●● | ●●● | ● | ● | ● | — | — | — | — | — |
| **C Trades** | ●●● | ●●● | — | ● | ● | ●●● | — | ●● | — | — |
| **D Field svc** | ●●● | ●● | — | ● | — | ●●● | — | ● | — | — |
| **E Pro svc** | ●●● | ●●● | — | ● | — | — | — | — | ●●● | — |
| **F Retail** | ●●● | ●● | — | ● | ●● | — | ●●● | ●●● | — | — |
| **G Logistics** | ●● | ●●● | — | ● | — | — | — | — | — | — |
| **H Prop mgmt** | ●● | ●● | — | — | — | — | — | — | — | ●●● |
| **I Restaurant** | ●● | ● | — | — | — | — | — | ●● | — | — |
| **J Staffing** | ●●● | ●●● | — | ● | — | — | — | — | ● | — |

*Heat = prevalence in the industry, not co-occurrence. NetSuite/BC customers usually do **not** also run QB.*

---

## Connector build order (nodes)

```
FOUNDATION   SYS-QBO (existing) · SYS-QBD · SYS-EXCEL · canonical model
CANDIDATES   SYS-BC                       ← full-ERP A+B
             SYS-NETSUITE                 ← full-ERP A+B
VALIDATE     SYS-FISHBOWL or SYS-CIN7     ← only if native-integration gap is material
PHASE 1      Choose exactly one candidate family after segmented discovery
P3   SYS-SHOPIFY · SYS-SQUARE · SYS-GUSTO
P4   SYS-SERVICETITAN or SYS-JOBBER       ← pick one trades stack
P5   SYS-HARVEST / SYS-BQE · SYS-LIGHTSPEED
—    Legacy ERP, AccuLynx, PM, TMS, Toast
```

**Rule:** Max **one new ops-system family per quarter** after P0.

---

## SOW usage

1. Choose **1–4 System IDs** from this catalog (or start from a sample in [mesh-catalog.md](./mesh-catalog.md)); a one-node Mesh is valid only for a cataloged full-ERP cross-module playbook.
2. List them in SOW Section 3 as M1–M4 with integration method + refresh.  
3. Name the Mesh descriptively (`ServiceTitan + QuickBooks Online + Excel`).  
4. Select Signals whose required roles/systems are covered ([signal-catalog.md](./signal-catalog.md)).  
5. New vendor not listed → add a System ID here first.

---

## Related

- [mesh-catalog.md](./mesh-catalog.md) — sample Meshes composed from these nodes
- [signal-catalog.md](./signal-catalog.md)
- [industry-system-clusters.md](../industry-system-clusters.md)
- [sow-template-meshflow.md](../terms/sow-template-meshflow.md)

---

## Revision log

| Date | Change |
|---|---|
| 2026-07-20 | Initial catalog (prebuilt Mesh packages) |
| 2026-07-20 | Reframe: source system / Mesh nodes only |
| 2026-07-20 | Renamed to **mesh-node-catalog**; sample Meshes moved to mesh-catalog.md |
| 2026-07-21 | Wedge → Signal; links to signal-catalog.md |
| 2026-07-23 | NS/BC → Full ERP (not + QB); Fishbowl/Cin7 = A+B beachhead |
| 2026-07-23 | Retain A+B ICP; reopen Phase 1 node family across split-stack, BC, and NetSuite candidates |
| 2026-07-23 | Downgrade Fishbowl/Cin7 nodes to validation-only after confirming native accounting/commerce integration coverage |
