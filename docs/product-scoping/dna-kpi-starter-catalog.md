# DNA — KPI Starter Catalog (BC intra)

**Purpose:** Canonical starter KPIs for Business Central DNA packs. IDs mirror the Signal catalog pattern (`KPI-*`).

**Starter pack:** [`src/meshflow/dna/packs/bc_intra_v1.yaml`](../../src/meshflow/dna/packs/bc_intra_v1.yaml) (v1.1.0)

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
| `KPI-ORD-02` | Order bookings | Sum of order line amounts by order date | `out_fact_order_lines` | currency |
| `KPI-ORD-03` | Order line count | Count of order lines by order date | `out_fact_order_lines` | count |
| `KPI-GP-01` | Gross profit | Sum of line gross profit (net − cost) | `out_fact_revenue_lines` | currency |
| `KPI-GM-01` | Gross margin | Gross profit ÷ net sales revenue | ratio of `KPI-GP-01` / `KPI-REV-01` | percent |
| `KPI-BKL-01` | Backlog amount | Outstanding order line value (open orders) | `out_fact_order_lines` | currency |
| `KPI-BKL-02` | Backlog line count | Count of open order lines | `out_fact_order_lines` | count |
| `KPI-BKL-03` | Open order count | Distinct open sales orders | `out_fact_order_lines` | count |
| `KPI-REV-01-YoY` | Net sales revenue CY vs PY by customer | Period compare vs prior year | `out_rev_by_customer_period` | currency (thousands) |

---

## Executive compare KPIs (MTD / QTD / YTD)

Company-total YoY comparisons published to `out_executive_kpis`:

| Base measure | MTD | QTD | YTD |
|---|---|---|---|
| Invoice revenue | `KPI-REV-YoY-MTD` | `KPI-REV-YoY-QTD` | `KPI-REV-YoY-YTD` |
| Invoice count | `KPI-INV-YoY-MTD` | `KPI-INV-YoY-QTD` | `KPI-INV-YoY-YTD` |
| Order bookings | `KPI-ORD-YoY-MTD` | `KPI-ORD-YoY-QTD` | `KPI-ORD-YoY-YTD` |
| Order lines | `KPI-ORDLN-YoY-MTD` | `KPI-ORDLN-YoY-QTD` | `KPI-ORDLN-YoY-YTD` |
| Gross profit | `KPI-GP-YoY-MTD` | `KPI-GP-YoY-QTD` | `KPI-GP-YoY-YTD` |
| Gross margin | `KPI-GM-YoY-MTD` | `KPI-GM-YoY-QTD` | `KPI-GM-YoY-YTD` |

Pipeline point-in-time KPIs in `out_executive_snapshot`: `KPI-BKL-01`, `KPI-BKL-02`, `KPI-BKL-03`.

YTD ranking outputs (top 10): `out_top_customers_ytd`, `out_top_items_ytd`, `out_top_customers_margin_ytd`, `out_top_items_margin_ytd`.

---

## Expansion KPIs (documented — add in customer packs)

| ID | Name | Notes | Sell posture |
|---|---|---|---|
| `KPI-DSO-01` | Days sales outstanding | Requires AR + revenue period logic | Follow-on |
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
- **Formula type** (sum, count, count_distinct, avg, ratio, period_compare)
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
