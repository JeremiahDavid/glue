# DNA Semantic Engine

Technical specification for **DNA — Semantic Engine**: customer documentation → versioned definition packs → certified gold tables/views → Meshflow web deliverables.

**Audience:** Internal product and engineering.

**Companion docs:**

- [dna-offering.md](../product-scoping/dna-offering.md) — customer-facing offering and workflow
- [dna-kpi-starter-catalog.md](../product-scoping/dna-kpi-starter-catalog.md) — starter KPI IDs
- [dbc-data-model.md](../dbc-data-model.md) — BC join reference
- [ai-boundaries.md](./ai-boundaries.md) — AI guardrails
- [confidence-and-provenance.md](./confidence-and-provenance.md) — provenance model

---

## Purpose

DNA sits **after silver consolidate** and **before downstream deliverables** (web views, exports, optional BYO-BI). It transforms source-faithful silver tables into **customer-approved, version-pinned semantic outputs**.

Signals tier customers may skip DNA entirely. DNA customers get governed semantics — not ad-hoc report SQL.

---

## Pipeline position

```text
bronze ingest → silver consolidate → DNA compile → DNA validate → DNA publish → web / export
```

| Stage | Process key | Writes |
|---|---|---|
| Compile | `dna_compile` | Staging gold Parquet under `gold/dna/_staging/` |
| Validate | `dna_validate` | Test results JSON; blocks publish on failure |
| Publish | `dna_publish` | Production gold under `gold/dna/{output_id}/` + manifest |

Definition packs live at `dna/definition_packs/v{semver}/pack.yaml` in the tenant data bucket (or local `data/` mirror).

---

## Definition pack schema

JSON Schema: [`src/meshflow/dna/schema/definition-pack.schema.json`](../../src/meshflow/dna/schema/definition-pack.schema.json)

Starter example: [`src/meshflow/dna/packs/bc_intra_v1.yaml`](../../src/meshflow/dna/packs/bc_intra_v1.yaml)

### Required sections

| Section | Role |
|---|---|
| `entities` | Grain + silver source table + primary key |
| `joins` | Join paths with cardinality |
| `outputs` | Materialized tables or KPI snapshots to publish |
| `kpis` | Metric definitions (formula type, source output, value column) |
| `tests` | Logic regression tests (not dollar reconciliation) |
| `approval` | Workflow status + approver record |

### Versioning rules

- **Any logic change** (join, filter, formula, grain) → bump `version` semver
- Production refresh pins to the **approved production pack version** — never silently drift
- `changelog[]` records human-readable diffs per version

### Workflow statuses

| Status | Meaning |
|---|---|
| `draft` | AI or internal draft — not publishable |
| `validated` | Human approved semantics — publishable to staging |
| `production` | Customer-signed (or starter pack) — used by scheduled publish |

Promotion: `draft` → `validated` → `production` via [`workflow.py`](../../src/meshflow/dna/workflow.py).

---

## Compiler

Module: [`src/meshflow/dna/compile.py`](../../src/meshflow/dna/compile.py)

Reads silver Parquet (local or S3) and definition pack; writes staging gold tables.

### Build types (v1)

| Build | Behavior |
|---|---|
| `entity_copy` | Subset of columns from silver entity |
| `join` | Left-join per pack join spec; suffix right columns on collision |
| `kpi_aggregate` | Compute KPI snapshot rows from compiled fact tables |

### Output naming

| Artifact | S3 path | Glue table |
|---|---|---|
| Materialized table | `gold/dna/{output_id}/data.parquet` | `dna_{output_id}` |
| KPI snapshot | `gold/dna/kpi_snapshot/data.parquet` | `dna_kpi_snapshot` |

Glue naming uses `dna_catalog_table_name()` in [`project_config.py`](../../src/meshflow/project_config.py) — no source prefix (gold is cross-entity).

---

## Validator

Module: [`src/meshflow/dna/validate.py`](../../src/meshflow/dna/validate.py)

Runs pack `tests[]` against staging outputs. **Does not assert dollar totals.**

| Test type | Asserts |
|---|---|
| `join_orphan_rate` | Orphan left rows ≤ threshold |
| `required_columns` | Output contains named columns |
| `row_count_minimum` | Output row count ≥ minimum |
| `header_line_sum_tolerance` | Reserved for future header/line reconciliation |

Failed validation → publish blocked; alert internal ops (same principle as batch confidence gates).

---

## Publisher

Module: [`src/meshflow/dna/publish.py`](../../src/meshflow/dna/publish.py)

On success:

1. Copy staging → `gold/dna/{output_id}/`
2. Write `gold/dna/manifest.json` with pack version, compiler hash, test results, timestamp
3. Sync Glue tables via [`catalog/glue_schema.py`](../../src/meshflow/catalog/glue_schema.py) `sync_dna_catalog()`

---

## Doc ingestion (AI-assisted)

Module: [`src/meshflow/dna/ingest_docs.py`](../../src/meshflow/dna/ingest_docs.py)

Ingests customer markdown/text/PDF extracts and produces a **draft** definition pack by:

1. Parsing structured sections (`## KPI`, `## Join`, etc.)
2. Merging with industry starter pack template
3. Optional LLM enrichment when `MESHFLOW_DNA_LLM_ENABLED=1` (future — v1 uses rule-based merge)

Human validation required before `validated` status.

---

## Provenance extension

Every KPI surfaced in the web UI includes:

```yaml
definition_id: KPI-REV-01
definition_version: "1.0.0"
pack_id: bc_intra_v1
source_output: out_fact_revenue_lines
published_at: "2026-07-30T06:00:00Z"
```

---

## Process registry

Registered in [`process_config.yaml`](../../process_config.yaml):

| Key | Stage | Slug |
|---|---|---|
| `dna_compile` | gold | dna-compile |
| `dna_validate` | gold | dna-validate |
| `dna_publish` | gold | dna-publish |
| `dna_refresh` | gold | dna-refresh |

CLI: `meshflow-dna compile|validate|publish|promote|draft-from-docs`

---

## CDK deployment (independent stack)

DNA deploys as **`DnaStack-{company}-{environment}`** — separate from `IngestStack`. Enable in `config.yaml`:

```yaml
dna:
  enabled: true
  source: dbc
  pack_id: bc_intra_v1
  schedule:
    hour: 7    # run after ingest (e.g. ingest at 6:00)
    minute: 0
```

```powershell
cd infra
cdk deploy IngestStack-POC-dev   # bronze + silver + catalog
cdk deploy DnaStack-POC-dev     # DNA publish pipeline (optional tier)
```

The DNA stack imports the existing data bucket by name; ingest must be deployed first.

---

## Relationship to reconciliation engine

| Layer | Scope |
|---|---|
| **DNA (v1)** | Intra-ERP / single-source semantic model (BC starter) |
| **Reconciliation engine** | Cross-system entity resolution + exception links |

Signals may eventually read DNA gold tables as inputs instead of re-implementing joins.

---

## Build order

1. Definition pack schema + starter pack
2. Compile / validate / publish (local + S3)
3. Glue catalog sync for `dna_*` tables
4. Doc ingestion + workflow promotion
5. Web UI on gold outputs
6. Independent **DnaStack** with its own Step Functions schedule (not chained to ingest refresh)
