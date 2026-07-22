# MAP Meshflow — Statement of Work (SOW)

**Template only — not legal advice.** Replace all `[bracketed]` fields. Have a qualified attorney review before use.

**SOW number:** `[SOW-MESHFLOW-2026-001]`  
**Effective date:** `[Date]`

---

## Parties

**Provider:** `[LLC Legal Name]` ("Provider"), `[State]` LLC  
Address: `[Business Address]`  
Contact: Jeremiah Stephens · `[business email]` · (478) 550-0087

**Client:** `[Client Legal Name]` ("Client")  
Address: `[Client Address]`  
Contact: `[Client Contact Name, Title]` · `[email]` · `[phone]`

---

## 1. Purpose

This Statement of Work defines the scope, deliverables, timeline, and fees for **MAP Meshflow** — Provider's productized offering that connects Client's operational systems and delivers **ranked operational insights** (exception queues, briefings, and metric views) — not a custom BI project or dashboard suite.

This SOW is governed by the **MAP Meshflow Master Services Agreement** ([meshflow-msa-template.md](./meshflow-msa-template.md)) dated `[MSA date]`. If no MSA is signed, `[attach MSA or note: MSA must be executed concurrently]`.

### 1.1 Product model — Meshes and Signals

| Term | Meaning |
|---|---|
| **Mesh** | A named **group of connected source systems** that share a semantic join path (e.g. FSM + QuickBooks + Excel). A Mesh defines *what can be linked*, not every insight Client will receive. |
| **Signal** | A productized **insight pack** for one operational metric or exception type on a Mesh (e.g. Outstanding AR, Membership visit gaps, Closed work not invoiced). Each Signal has a fixed definition, inputs, output shape, and known limitations. |

**Delivery standard:** Meshflow is designed for **rapid deployment** (target **`[2–4]` weeks** to handoff) and **actionable daily/weekly use** by owners, office managers, and controllers. Provider delivers **standard Mesh + Signal templates**. **Client-specific business logic** — custom allocations, proprietary formulas, one-off attribution models, and non-catalog Signals — is **out of scope** unless added via Section 7 change order.

**Industry / Mesh family:** `[e.g. Trades FSM · Manufacturing ERP · Distribution · Custom discovery]`

**Prior trial / discovery:** `[Meshflow trial completed [date] under meshflow-trial-terms / Discovery only [date] / None]`

**Commercial note:** Standard Meshflow path is **free discovery + free Mesh/Signal implementation + free 2-week trial**, then this SOW on conversion. Activation and monthly fees below apply to the **paid subscription**, not to the trial build.

---

## 2. Fees & payment

| Item | Amount | Due |
|---|---|---|
| **Mesh activation** (one-time) | **$4,000** | On SOW signature (conversion to paid) |
| **Monthly subscription** | **$600 / month** | Monthly, Net 15, beginning `[first monthly billing date]` |
| **M4 system** *(only if listed in Section 3)* | **+$1,000** activation · **+$100 / month** | On SOW signature / with monthly |
| **Implementation (standard Mesh)** | **$0** if completed under Meshflow trial; otherwise included at conversion for identical scope | Trial / carry-forward — see below |

**Signals included:** This Mesh fee includes **all catalog Signals** that apply to the systems in Section 3 (see [signal-catalog.md](./signal-catalog.md) — a Signal applies when every required role/System ID is present). Section 4 lists Signal IDs as an **acceptance checklist** (what will be turned on) — **not** a separate price menu. There is **no per-Signal fee**.

**Taxes:** Excluded unless required by law.

**Professional services beyond scope:** `$150`/hour, pre-approved in writing by Client.

**Named users beyond five (5):** **+$25 / user / month** via change order.

**Conversion from trial:** If Client completed a Meshflow trial ([meshflow-trial-terms.md](./meshflow-trial-terms.md)) within **30 days** prior to this SOW on the same Mesh, (a) Mesh activation and monthly subscription apply as stated above; (b) trial discovery, Mesh, and Signal configuration **carry forward** — Client is **not** charged a second implementation fee for identical scope. Activation starts the paid commercial relationship (ongoing refresh, support, and production tenancy under the MSA).

**Pricing reference:** [meshflow-pricing-sheet.md](./meshflow-pricing-sheet.md)

---

## 3. Mesh — connected systems

Provider will implement the following **Mesh**. Systems listed here are the only systems in scope for ingest under this SOW.

**Mesh name:** `[e.g. ServiceTitan + QuickBooks Online + Excel]`

**Mesh description:** `[One sentence — e.g. Field service jobs and memberships in Optsy joined to QuickBooks AR/invoices, with optional Excel file drop for holds or spend.]`

| Slot | System ID (from catalog) | System name | Role in Mesh | Integration method | Refresh |
|---|---|---|---|---|---|
| **M1** | `[e.g. SYS-OPTSY]` | `[e.g. Optsy]` | `[Ops / FSM / ERP]` | `[API / scheduled export / file drop]` | `[Daily / Weekly]` |
| **M2** | `[e.g. SYS-QBO]` | `[e.g. QuickBooks Online]` | Accounting / AR / invoices | `[API / scheduled export]` | `[Daily]` |
| **M3** | `[e.g. SYS-EXCEL]` | `[e.g. Excel / Google Sheets / none]` | `[Shadow ops / holds / spend / N/A]` | `[File drop / N/A]` | `[Daily / Weekly / N/A]` |
| **M4** *(optional)* | `[e.g. SYS-GUSTO / none]` | `[e.g. Gusto / none]` | `[Payroll / pricing / N/A]` | `[Export / API / N/A]` | `[As agreed / N/A]` |

**Default Mesh size:** Up to **three (3)** systems (M1–M3). A fourth system (M4) is included only when listed above and priced under Section 2 or Section 7. Systems must appear in [mesh-node-catalog.md](./mesh-node-catalog.md) (or be added there before SOW). Sample compositions: [mesh-catalog.md](./mesh-catalog.md).

Client grants **read-only access** or provides **scheduled exports** sufficient for the refresh cadence above. Client is responsible for internal approvals and credentials.

**File ingest:** If any slot uses Excel/CSV, Client agrees to deliver updated files to the agreed location on the schedule documented at handoff (`[e.g. weekly by Monday 8 AM ET]`).

**Write-back:** Provider does **not** write to, modify, or sync data into Client source systems under this SOW.

---

## 4. Signals — included insight packs (acceptance checklist)

Provider will deliver the Signals checked below. Each Signal is a **catalog template** for this Mesh — not custom analytics. **All applicable catalog Signals for this Mesh are included in the Mesh fee** ([meshflow-pricing-sheet.md](./meshflow-pricing-sheet.md)); this table is an **acceptance checklist**, not a price menu.

### 4.1 Signals to turn on

| Incl. | Signal ID | Signal name | Operational metric / decision | Primary systems used |
|---|---|---|---|---|
| `[x]` | `[SIG-AR-01]` | Outstanding AR | Who owes what — ranked collections list | M2 (+ M1 context if available) |
| `[x]` | `[SIG-MEM-01]` | Membership visit gaps | Active maintenance contracts with no visit in X days | M1 (+ M2 if billing) |
| `[x]` | `[SIG-NEW-01]` | New customer revenue | Revenue from customers first seen in period | M1 and/or M2 |
| `[ ]` | `[SIG-BILL-01]` | Closed work not invoiced | Completed / closed jobs with no matching invoice | M1 ↔ M2 |
| `[ ]` | `[SIG-CO-01]` | Change orders not billed | Approved COs missing from invoice | M1 / Excel ↔ M2 |
| `[ ]` | `[SIG-PART-01]` | Materials missing on invoice | Parts used on job not on invoice | M1 ↔ M2 |
| `[ ]` | `[SIG-MKT-01]` | Marketing spend return | Spend vs new-customer revenue *(thin model)* | Spend sheet / M3 ↔ M2 |
| `[ ]` | `[SIG-___]` | `[Custom catalog ID only — not bespoke]` | `[Metric]` | `[Systems]` |

**Signal count in this SOW (checklist):** `[N]`  
**Definition of "X days" / thresholds:** Documented in Section 10 (Assumptions) and the Signal definitions handoff pack.

### 4.2 Signal output shape (standard)

Unless a Signal's catalog card specifies otherwise, each Signal includes:

| Output | Description |
|---|---|
| **Exception or metric view** | Ranked list and/or period KPI view for the named metric |
| **Drill context** | Key identifiers (customer, job/WO, invoice, dates, $) available from connected systems |
| **Definition card** | Formula, sources, refresh time, confidence notes, known limitations |
| **Morning / weekly briefing slot** *(if subscribed)* | Signal contributes to Client's Meshflow briefing when that channel is enabled |

Provider may deliver Signal views in **`[QuickSight / Meshflow app / email briefing / agreed channel]`**. Channel is fixed at kickoff; changing channel is a change order if it requires rebuild.

---

## 5. Deliverables — in scope

### 5.1 Mesh foundation

| Deliverable | Description |
|---|---|
| Mesh environment | Tenant-scoped ingest and curated model for systems in Section 3 |
| Entity resolution (Mesh-standard) | Customer / job / invoice matching rules for this Mesh family |
| Daily (or agreed) refresh | Automated batch per Section 3 cadence |
| Historical depth | Trailing **`[12 / 24]` months** (or maximum available if less) |
| Systems map & data dictionary | Source → ingest → curated entities used by selected Signals |
| Signal definitions pack | One card per selected Signal (formula, sources, limitations) |
| Client runbook | Access, file-drop instructions, escalation, how to read each Signal |
| Named users | Up to **`[five (5)]`** named users within Client organization |

### 5.2 Implementation services

**Default path:** Mesh and Signal implementation for the systems and checklist in Sections 3–4 was completed under the **Meshflow trial** at **$0**. Under this paid SOW, Provider continues production tenancy, refresh, and support — not a second full build for identical scope.

**If no prior trial:** Provider implements Mesh and Signals under this SOW as part of conversion (still no separate implementation line item beyond Mesh activation).

| Workstream | Included |
|---|---|
| Kickoff & access coordination | Yes |
| Mesh ingest for named systems | Yes |
| Configuration of selected Signals only | Yes |
| QA, UAT support, minor template revisions | Yes |
| Handoff call and documentation | Yes |

**Speed-first rule:** Missing or unsupported source fields result in a Signal marked **limited / N/A** or deferred — not a custom rebuild under this SOW.

**Timeline target:** **`[2–4]` weeks** from kickoff, assuming Client provides system access within **5 business days** of kickoff date `[Kickoff date]`.

**Milestone:** First selected Signal targeted usable by end of **week `[1 / 2]`** (partial history acceptable).

### 5.3 Meetings & support

| Item | Included |
|---|---|
| Kickoff call (~30–45 min) | Yes |
| Mid-implementation check-in (~30 min) | Yes |
| Handoff / acceptance call (~30–45 min) | Yes |
| Email support post-go-live | 1 business day response SLA |
| Named user seats | Up to **`[five (5)]`** |
| Additional seats / Signals / systems | Section 7 change order |

---

## 6. Out of scope

The following are **not** included unless added via Section 7:

| Item | Notes |
|---|---|
| Signals not listed as selected in Section 4.1 | Catalog add via change order |
| Bespoke / non-catalog metrics | Professional services — not Meshflow |
| Client-specific business logic | Allocations, proprietary formulas, custom attribution |
| Full marketing attribution / multi-touch ROAS | Not a standard Signal; thin spend→revenue only if `[SIG-MKT-01]` selected |
| Fourth+ systems beyond Mesh table | Change order |
| Write-back to Optsy, QuickBooks, ERP, CRM, or ads platforms | Never in scope |
| Replacing Client's FSM, price book, or accounting system | Never in scope |
| Real-time / sub-daily refresh | Batch SLA only |
| Audited financials, QoE, tax, or legal advice | Client's advisors |
| Net-new connector R&D for unsupported systems | Scoped after assessment |
| MAP Bedrock dashboard suite | Separate SOW ([../contracts/sow-template-bedrock.md](../contracts/sow-template-bedrock.md)) unless explicitly combined |
| AI Assistant / forecasting | Separate add-on or future product |

---

## 7. Change orders

Changes to Mesh systems, Signal selection, thresholds, delivery channel, or timeline require a **written change order** signed by both parties, including description, fee (if any), and schedule impact.

**Professional services rate:** **`$150`/hour** unless otherwise quoted.

Common triggers: add system to Mesh · add catalog Signal · change "X days" / $ thresholds after acceptance · custom logic · expedited timeline · history beyond agreed depth.

---

## 8. Client responsibilities

Client agrees to:

1. Designate **`[Primary contact name]`** as primary contact with authority to grant access and approve deliverables  
2. Provide read-only access or scheduled exports for all Mesh systems within **5 business days** of kickoff  
3. Maintain file-drop discipline for any file-based Mesh slot  
4. Participate in kickoff, mid-implementation, and handoff calls  
5. Review deliverables and provide consolidated feedback within **5 business days** of each milestone  
6. Provide a list of up to **`[five (5)]`** named users at kickoff  
7. Agree threshold defaults in Section 10 (e.g. membership gap days, "new customer" definition)  
8. Not use Meshflow output for regulatory filings, audited financials, or safety-critical decisions without independent verification  
9. Accept that Meshflow delivers **catalog Mesh + Signal templates** — not bespoke analytics  

**Delay:** Provider timeline extends day-for-day for Client delays in access, feedback, file drops, or approvals.

---

## 9. Acceptance criteria

Implementation is **accepted** when all of the following are true:

- [ ] All **named Mesh systems** refresh on the agreed cadence (or documented manual process)  
- [ ] Each **selected Signal** is published to Client's delivery channel  
- [ ] Each Signal matches its **definition card** (or is marked limited/N/A with documented cause)  
- [ ] Systems map, data dictionary, and Signal definitions pack delivered  
- [ ] Named users provisioned per Client list  
- [ ] Handoff call completed with Client primary contact  

Client will confirm acceptance in writing (email sufficient) within **5 business days** of handoff. If Client does not respond with specific deficiencies within that period, deliverables are deemed accepted.

---

## 10. Assumptions & known limitations

Filled from discovery. These bind Signal behavior:

| Topic | Assumption | Client acknowledgment |
|---|---|---|
| Accounting SoR | `[QuickBooks Online / Desktop]` is system of record for AR/invoices | `[Yes]` |
| Ops SoR | `[Optsy / …]` is system of record for jobs / memberships | `[Yes]` |
| Membership gap threshold | No visit in **`[X]`** days = exception | `[Yes]` |
| New customer definition | `[First invoice in period / First job / First customer create]` | `[Yes]` |
| Marketing Signal (if any) | Thin model: `[monthly spend in Excel]` ÷ new-customer revenue — **not** multi-touch GA attribution | `[Yes / N/A]` |
| Closed-not-invoiced (if any) | Job "complete/closed" status field = `[field name]` | `[Yes / N/A]` |
| File drop | Client owns weekly discipline for `[file name]` | `[Yes / N/A]` |
| Sync caveat | Native Optsy↔QB (or similar) sync may exist; Meshflow **reconciles and ranks**, it does not replace sync | `[Yes]` |

Provider does not warrant integration with every variant of Client's software. Feasibility assessed during discovery dated `[discovery date]`.

---

## 11. Term & termination

**Implementation term:** `[Kickoff date]` through acceptance (estimated `[Target handoff date]`).

**Subscription term:** Month-to-month beginning `[first monthly billing date]`, governed by MSA termination provisions. Subscription covers Mesh refresh and **all applicable catalog Signals** for this Mesh.

If Client terminates during implementation after work begins **under a paid SOW**, Client pays activation fees due under Section 2 and any approved change orders; Provider delivers work product completed to date. *(Trial-period walk-away is governed by the Meshflow trial agreement — no activation owed.)*

---

## 12. Order of precedence

In conflict: **MSA** controls except where this SOW specifies Mesh/Signal scope and fees. This SOW + MSA constitute the full agreement for this engagement.

---

## Signatures

By signing, both parties agree to the scope, fees, and terms above.

**Provider — `[LLC Legal Name]`**

Signature: ___________________________  
Name: Jeremiah Stephens  
Title: `[Manager / Member]`  
Date: _______________

**Client — `[Client Legal Name]`**

Signature: ___________________________  
Name: `[Client Contact Name]`  
Title: `[Title]`  
Date: _______________

---

## Appendix A — Mesh nodes & sample Meshes (compose in Section 3)

**Mesh nodes (canonical):** [mesh-node-catalog.md](./mesh-node-catalog.md) — source systems tagged by industry.  
**Sample Meshes:** [mesh-catalog.md](./mesh-catalog.md) — common compositions (patterns, not mandatory SKUs).

*Common System IDs:*

| System ID | Name | Role | Industry tags | Wave |
|---|---|---|---|---|
| `SYS-QBO` / `SYS-QBD` | QuickBooks Online / Desktop | Accounting | **A–J** | P0 |
| `SYS-EXCEL` | Excel / Google Sheets | Shadow | **A–J** | P0 |
| `SYS-NETSUITE` | NetSuite | Ops ERP | **A, B** (+…) | P1 |
| `SYS-BC` | Dynamics 365 BC | Ops ERP | **A, B, F** | P2 |
| `SYS-FISHBOWL` / `SYS-CIN7` | Fishbowl / Cin7 | Ops ERP | **A, B** | P2b |
| `SYS-SERVICETITAN` | ServiceTitan | FSM | **C, D** | P4 |
| `SYS-JOBBER` / `SYS-HCP` / `SYS-OPTSY` | Jobber / HCP / Optsy | FSM | **C** | P4 |
| `SYS-SHOPIFY` | Shopify | Commerce | **F** | P3 |
| `SYS-SQUARE` | Square | Commerce | **F, C** | P3 |
| `SYS-HARVEST` / `SYS-BQE` | Harvest / BQE | PSA | **E** | P5 |
| `SYS-GUSTO` | Gusto | Payroll (M4) | **F, C** | P3 |

*Sample Meshes (optional starting point):* `MESH-NS-QB` · `MESH-ST-QB` · `MESH-OPTSY-QB` · `MESH-SHOPIFY-QB` · `MESH-QB-EXCEL` — see full cards in mesh-catalog.

---

## Appendix B — Signal catalog (reference; select in Section 4)

**Canonical catalog:** [signal-catalog.md](./signal-catalog.md) — full Signal nodes; **Requires** = system roles/IDs.

*Common selections:*

| Signal ID | Name | Requires (roles) | Meshflow strength | Notes |
|---|---|---|---|---|
| `SIG-AR-01` | Outstanding AR | Accounting (QB) | High (easy) | Bundle with ops context when M1 present |
| `SIG-BILL-01` | Closed work / shipped not invoiced | Ops ERP or FSM or PSA + QB | **Core spine** | Hero when sync/holds leave gaps |
| `SIG-BILL-02` | Partial / under-invoiced lines | Ops ERP + QB | High | Dist / multi-line mfg |
| `SIG-MEM-01` | Membership visit gaps | FSM + QB | High | Needs agreement + last visit |
| `SIG-MEM-02` | Membership billing gaps | FSM + QB | High | Renewals / wrong plan bill |
| `SIG-NEW-01` | New customer revenue | Customers + invoices | Med–High | Lock "new" definition in §10 |
| `SIG-CO-01` | Change orders not billed | FSM (+ Excel) + QB | High | Often needs Excel |
| `SIG-PART-01` | Materials missing on invoice | FSM + QB | High | Parts/truck stock |
| `SIG-LABOR-01` | Labor missing on invoice | FSM or PSA + QB | High | T&M underbill |
| `SIG-CASH-01` | POS/sales vs QB deposits | Commerce + QB | High | Retail hero |
| `SIG-MARGIN-01` | Customer / job margin outliers | Ops/FSM + QB + cost | Med | Cost completeness hard |
| `SIG-MKT-01` | Marketing spend return | Excel spend + QB | **Weak** | Not full GA ROAS; use sparingly |

---

## Appendix C — Example filled scope (HVAC / Optsy — remove or replace)

*Illustrative only — delete before send unless this is the deal.*

| Field | Example |
|---|---|
| Mesh | Optsy + QuickBooks Online + Excel (`SYS-OPTSY` + `SYS-QBO` + `SYS-EXCEL`) |
| Signals | `SIG-MEM-01`, `SIG-AR-01`, `SIG-NEW-01` |
| Deferred | `SIG-MKT-01` (GA ROAS) unless Client accepts thin spend→revenue model |
| Probe | `SIG-BILL-01` if discovery finds closed jobs without QB invoices |

---

## Internal checklist (remove before sending)

- [ ] All `[brackets]` replaced  
- [ ] MSA executed or attached  
- [ ] System IDs from catalog and all slots named with integration method  
- [ ] Signal checklist completed; matches applicable catalog Signals for this Mesh  
- [ ] Pricing per [meshflow-pricing-sheet.md](./meshflow-pricing-sheet.md) ($4,000 / $600; M4 if any)  
- [ ] Section 10 assumptions filled from discovery  
- [ ] Delivery channel chosen  
- [ ] Kickoff and target handoff dates set  
- [ ] Appendices trimmed or marked "reference"  
- [ ] First invoice (Mesh activation $4,000) ready on **conversion** (not at trial kickoff)  
- [ ] Signals are catalog IDs only — no bespoke promises  

---

## Related internal docs

| Document | Purpose |
|---|---|
| [meshflow-msa-template.md](./meshflow-msa-template.md) | **Meshflow MSA** — sign with Meshflow SOW at paid conversion |
| [sow-template-meshflow.md](./sow-template-meshflow.md) | **Meshflow SOW** — Mesh + Signals |
| [meshflow-pricing-sheet.md](./meshflow-pricing-sheet.md) | **Meshflow pricing** — flat Mesh $4,000 / $600 |
| [../contracts/sow-template-bedrock.md](../contracts/sow-template-bedrock.md) | Legacy dashboard-suite SKU (separate product) |
| [../contracts/msa-template.md](../contracts/msa-template.md) | Legacy Bedrock / general MAP MSA |
| [../contracts/map-pricing-sheet.md](../contracts/map-pricing-sheet.md) | Legacy Bedrock pricing |
| [mesh-node-catalog.md](./mesh-node-catalog.md) | **Mesh nodes** (`SYS-…`) + industry tags |
| [mesh-catalog.md](./mesh-catalog.md) | **Sample Meshes** (compositions) |
| [signal-catalog.md](./signal-catalog.md) | **Canonical Signal nodes** + Mesh compatibility |
| [gtm-industry-system-matrix.md](./gtm-industry-system-matrix.md) | Spine SKU + industry clusters |
| [industry-system-clusters.md](./industry-system-clusters.md) | Mesh playbooks / connector order |
| [Industry-opportunities/trades-construction-problem-opportunity-ranking.md](./Industry-opportunities/trades-construction-problem-opportunity-ranking.md) | Trades Signal ranking |
| [internal-execution-scoping/reconciliation-engine.md](./internal-execution-scoping/reconciliation-engine.md) | Engine behind Mesh joins |
| [../product-pillars.md](../product-pillars.md) | Outcomes over dashboards |
