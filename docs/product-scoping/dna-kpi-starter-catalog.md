# DNA — KPI Starter Catalog (BC intra)

**Purpose:** Canonical starter KPIs for Business Central DNA packs. IDs mirror the Signal catalog pattern (`KPI-*`).

**Starter pack:** [`src/meshflow/dna/packs/bc_intra_v1.yaml`](../../src/meshflow/dna/packs/bc_intra_v1.yaml)

**Companion:** [dna-offering.md](./dna-offering.md) · [dbc-data-model.md](../dbc-data-model.md)

---

## Catalog index

| ID | Name | Formula | Source output | Unit |
|---|---|---|---|---|
| `KPI-REV-01` | Net sales revenue | Sum of invoice line amounts | `out_fact_revenue_lines` | currency |
| `KPI-INV-01` | Invoice line count | Count of invoice lines | `out_fact_revenue_lines` | count |
| `KPI-CUST-01` | Active invoiced customers | Distinct customers on invoice lines | `out_fact_revenue_lines` | count |
| `KPI-SHIP-01` | Shipped quantity | Sum of shipment line quantities | `ent_sales_shipment_lines` | quantity |
| `KPI-ORD-01` | Open order line quantity | Sum of sales order line quantities | `ent_sales_order_lines` | quantity |

---

## Expansion KPIs (documented — add in customer packs)

| ID | Name | Notes | Sell posture |
|---|---|---|---|
| `KPI-DSO-01` | Days sales outstanding | Requires AR + revenue period logic | Follow-on |
| `KPI-MARGIN-01` | Line gross margin | Requires cost on invoice lines or item ledger | Follow-on |
| `KPI-S2I-01` | Ship-to-invoice lag (avg days) | Join shipment → invoice by order | Hero adjacency |
| `KPI-FILL-01` | Fill rate | Order line qty vs shipped qty | Distribution pack |
| `KPI-BO-01` | Backorder line quantity | Open order lines with outstanding qty | Distribution pack |
| `KPI-GL-01` | GL revenue (posted) | `general_ledger_entries` filter by account | Controller cross-check |

Custom KPIs use `KPI-CUSTOM-nn` or customer-prefixed IDs in the DNA file. No per-KPI cap — scope is bounded by documented requirements and self-service submission.

---

## Definition card fields (customer-facing)

Each KPI in the portal shows:

- **ID** and **name**
- Plain-language **definition**
- **Formula type** (sum, count, count_distinct, avg)
- **Source output** and grain
- **Pack version** and **as-of** refresh timestamp
- **Known limitations** from pack

---

## Cross-reference to Signals

| Signal | DNA KPI / output relationship |
|---|---|
| `SIG-BILL-01` | Can consume `out_fact_revenue_lines` + shipment joins (future) |
| `SIG-BILL-02` | Line-level ship ↔ invoice — extend pack with `KPI-S2I-01` |
| `SIG-BO-01` | `KPI-BO-01` on order lines |
| `SIG-AR-01` | `KPI-DSO-01` + customer dimension |

Signals remain the **action layer**; DNA is the **certified semantic layer** underneath.
