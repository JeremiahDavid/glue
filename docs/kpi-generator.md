# KPI Generator (portal)

Natural-language KPI drafting in the client portal. Bedrock drafts Athena SQL using Source Browser gold YAML and the production DNA pack as context. **Approved SQL is pinned under governance semver and replayed verbatim** on scheduled refreshes — AI is not invoked again after approval.

**Portal route:** `/portal/dna/kpi-generator` (admin only)

**Code:** `packages/meshflow-portal/src/meshflow/dna/web/portal/kpi_generator/`

---

## Portal tabs

| Tab | Purpose |
|---|---|
| **KPI Generator** | Describe a KPI, run session validation filters, save as a DNA draft |
| **Review Drafts (N)** | Kanban workflow: integrity validation → approve → publish |

The Review Drafts tab shows a count of proposals in the workflow (`pending_review` or `approved`, not yet published).

---

## Operator workflow

```mermaid
flowchart LR
  A[Describe KPI] --> B[Generate]
  B --> C[Optional: validation filters]
  C --> D[Run validation]
  D --> E[Save Draft]
  E --> F[Review Drafts]
  F --> G[Integrity Validation pillar]
  G --> H[Approve pillar]
  H --> I[Publish Approved KPIs toolbar]
  I --> J[Silver or gold refresh materializes tables]
```

### 1. Generate

On the **KPI Generator** tab, send a natural-language request. Bedrock returns a structured draft:

- Layer (`silver` or `gold`), mode, transform id
- Target entity or output id
- Fields, filters, calculation summary
- Athena `SELECT` SQL

The proposal is stored as a **working** session artifact (not yet a governance version).

### 2. Validate (optional)

Use **Validation criteria** to add session-only filters (fact, field, value). **Run validation** executes the SQL in Athena with those predicates wrapped around the query. Validation does **not** change the pinned SQL; it is for spot-checking one invoice, customer, etc.

Filters apply only to the validation run unless the same logic is included in the generated SQL itself.

### 3. Save Draft

**Save Draft** on the proposed calculation card:

- Bumps a new **patch** governance version from the current production pin
- Writes DNA pack at that version with `status: draft`
- Writes SQL pack manifest + exact `.sql` files under that version
- Copies reporting sidecar forward at the same version (when present)
- Appends workflow history (does **not** change `active_version`)
- Moves the proposal to `pending_review` and stores a full `governance_snapshot` (prompt, draft, validation, SQL)

Production portal and scheduled jobs continue to use the **previous** pinned version until a draft is approved.

### 4. Review Drafts (kanban)

Open **Review Drafts**. The board has two pillars; each KPI is its own tile:

| Pillar | Action |
|---|---|
| **Integrity Validation** | Run integrity checks per KPI tile |
| **Approve** | Approve individual KPIs after integrity passes |

Use the toolbar at the top to set the next governance version (patch / minor / major) and click **Publish Approved KPIs** (beside the version field) to materialize all approved KPIs (silver and/or gold refresh).

Approved KPIs appear as a vertical **Ready to publish** list on the right of the toolbar until published. Click a chip to review details; use **×** to remove it from the publish queue (marks the proposal rejected; production pins are unchanged).

Approving one KPI merges only that transform into the **current production** SQL pack — other pending drafts saved to the same draft governance version are **not** promoted.

### 5. Approve

**Approve** on a tile that passed integrity validation:

- Merges only that KPI's SQL into a new production governance version (version from the toolbar)
- Pins `workflow.active_version`
- Moves the KPI to the toolbar **Publish Approved KPIs** queue

### 6. Publish

**Publish Approved KPIs** in the Review Drafts toolbar:

- Runs silver consolidate refresh when any approved KPI is silver-layer
- Runs DNA gold refresh when any approved KPI is gold-layer
- Marks all approved KPIs as `published`

### 7. Reject

**Reject** marks the proposal `rejected`. Production pins are unchanged. The draft version remains in governance history as a draft; it is not promoted.

---

## Proposal statuses

| Status | Meaning |
|---|---|
| `working` | Generated on the KPI Generator tab; not saved to governance |
| `pending_review` | Saved as a DNA draft; in Integrity Validation or Approve column |
| `approved` | Pinned to production; listed in toolbar until published |
| `published` | Refresh started; removed from Review Drafts |
| `rejected` | Rejected from Review Drafts; not pinned |

---

## Layer rules (SQL packs)

| Change | Layer | SQL path | Runs when |
|---|---|---|---|
| Column adds on an existing silver entity | `silver` | `sql/silver/enhance__{entity}.sql`, mode `add_columns` | After silver consolidate (connector refresh) |
| New fact table or KPI output | `gold` | `sql/gold/*.sql`, mode `fact_table` or `kpi` | DNA refresh |

### Silver: one enhancement per entity

Each KPI keeps its own **contribution SQL** under `sql/silver/contributions/{entity}/{kpi_id}.sql`. On Save Draft / Approve, contributions for an entity are merged into exactly **one** canonical transform (`enhance__{entity}` → `sql/silver/enhance__{entity}.sql`). Runtime replays only the canonical transform.

Silver contributions must preserve entity grain (no `GROUP BY`, no `SELECT DISTINCT`, no top-level aggregates). Grain-changing logic belongs in the gold layer.

### Pre-approval integrity validation

Review Drafts groups pending KPIs by affected table (silver entity or gold output). Before approval:

1. **Run integrity validation** merges all contributions for the group and checks row count + primary-key checksum against the **raw silver baseline** captured at consolidate time (`silver/{source}/{entity}/_baseline_fingerprint.json`).
2. On failure, the merge repair LLM receives the mismatch and attempts a corrected query.
3. **Approve group** pins production only after integrity passes (silver) or Athena execution succeeds (gold).

This gate validates base-table integrity only — not KPI business correctness.

### Gold: unique grains

Each gold transform declares `grain_columns` in the manifest (sorted dimension keys; `[]` = company total). The pack rejects duplicate `grain_columns` across gold outputs.

Athena SQL should reference Glue table names **without** a database prefix, e.g. `silver_dbc_sales_invoice_lines`, `dna_out_executive_kpis`. The portal normalizes common `silver.` / `gold.` qualifiers before validation.

See also [architecture.md](./architecture.md) (lake layout and layer contract).

---

## Artifacts

**Working / review proposals** (full generator context):

```text
governance/{company}_dna_config/kpi_generator/proposals/{proposal_id}.json
```

**Governance version** (on Save Draft or Approve):

```text
governance/{company}_dna_config/v{semver}/{company}_dna_config.yaml
governance/{company}_dna_config/v{semver}/sql/manifest.yaml
governance/{company}_dna_config/v{semver}/sql/silver/enhance__{entity}.sql
governance/{company}_dna_config/v{semver}/sql/silver/contributions/{entity}/{kpi_id}.sql
governance/{company}_dna_config/v{semver}/sql/gold/*.sql
governance/{company}_dna_config/workflow.json
```

Proposal JSON retains prompt, draft, `last_validation`, `governance_version`, and `governance_snapshot` after save.

---

## Related portal surfaces

| Surface | Role |
|---|---|
| **Source Browser** | Gold YAML reference (`entity_properties`, relationships, tags) reconciled with `latest_profile.yaml` from silver ETL |
| **Pack Registry** (`/portal/governance`) | Version history for all governance saves, including KPI Generator drafts and approvals |

Silver consolidate writes `governance/source_semantic_reference/{source}/latest_profile.yaml`; the source-docs gold job enriches all three gold artifacts with `silver_column`, `in_silver`, and `origin` (relationships also get `silver_FK` / `silver_PK`).

---

## Manual gold refresh

Admins can trigger a DNA Step Functions refresh from the **Gold refresh** card on the KPI Generator page (publish-only: SQL pack replay, else compile fallback). Monthly quota is tracked per client (`dna_manual_refresh` in portal config).

---

## Implementation notes

- **Bedrock budget** shares the portal Config Assist monthly allowance meter.
- **Validation** uses the reporting UI Lambda role (Athena + Glue read on the tenant catalog).
- **Approve** reuses the same persistence path as the former direct “pin SQL” action, but only after explicit review of a saved draft (or approve from Review Drafts for a `pending_review` proposal at its draft version).
