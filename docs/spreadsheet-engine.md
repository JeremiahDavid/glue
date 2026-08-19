# Spreadsheet Engine

Turn uploaded Excel workbooks (`.xlsx`) into governed reference entities: detect tables, infer schema and business meaning with Bedrock, propose deterministic cleaning steps, and materialize approved tables into `silver/reference/` parquet.

The Spreadsheet Engine is a **virtual source** in the Source Browser (`sse`). It is not a lake connector like QBO or Business Central — it produces reference data that operators review and approve before it lands in the lake.

**Portal route:** `/portal/semantics/source-docs` (default source `sse`)

**Engine code:** `packages/meshflow-connectors/src/meshflow/spreadsheet/`

**Portal UI:** `packages/meshflow-portal/src/meshflow/dna/web/portal/spreadsheet_engine/`

**Infrastructure:** `infra/spreadsheet_pipeline.py` (Step Functions + Lambdas in `ReportingStack`)

---

## Operator workflow

```mermaid
flowchart LR
  A[Upload .xlsx] --> B[Parse]
  B --> C[Profile]
  C --> D[Interpret schema]
  D --> E[Propose transforms]
  E --> F[Review]
  F --> G[Approve transformation]
  G --> H[Approve table]
  H --> I[Silver reference parquet]
```

### 1. Upload and analyze

Upload a workbook from the Source Browser. The portal creates a **job**, stores the file, and starts the `spreadsheet_analyze` Step Functions workflow (or runs the pipeline synchronously in local dev).

Pipeline stages:

| Stage | Job status | What happens |
|---|---|---|
| **Parse** | `parsing` → `parsed` | Detect table regions per sheet; normalize headers to snake_case |
| **Profile** | `profiling` → `profiled` | Infer column types, null rates, key candidates |
| **Interpret** | `interpreting` → `interpreted` | Bedrock proposes entity name, grain, schema, relationships |
| **Propose** | `proposing` → `ready` | Propose transformation steps (reuse knowledge, induce, or Bedrock) |

Poll progress at `GET /api/spreadsheet-engine/status?job_id=…`.

### 2. Review proposals

For each detected table the report includes:

- **Schema** — column names, types, keys, business descriptions
- **Transformation** — versioned step list from raw headers to output schema
- **Preview** — bounded sample of source rows and transformed output

Approve or reject the **transformation** first (when steps are present), then approve the **table**. Rejecting a transformation triggers a re-proposal using heuristics and knowledge-base matches.

### 3. Catalog and silver

Approving a table:

1. Writes a **catalog entry** under `governance/spreadsheet_engine/catalog/`
2. Saves or updates a **knowledge entry** (approved transformation + input shape) for future uploads
3. **Materializes** the table to `silver/reference/{entity}/data.parquet`

Stable catalog IDs use `{source_file_slug}__{entity_name}` (for example `price_list__customers`). Legacy job-bound IDs (`{job_id}__{table_id}`) remain as fallbacks.

### 4. Re-upload (reload)

When a workbook matches a prior catalog entry (by `input_shape.shape_hash` or header compatibility), the portal can link the job to that catalog. On reload:

- **Interpret** validates the new file against the approved transformation — **no Bedrock**
- **Propose** finalizes validation — **no Bedrock**
- If validation passes, the operator completes the reload without re-approving schema or transforms

If validation fails, the operator can request a **schema rewrite** (re-run interpret + propose with AI) or a **transformation rewrite** (re-run propose only).

---

## Architecture

```mermaid
flowchart TB
  subgraph portal [Portal]
    UI[Source Browser sse]
    SVC[spreadsheet_engine/service.py]
  end

  subgraph aws [AWS - deployed]
    SFN[Step Functions spreadsheet_analyze]
    L1[parse_handler]
    L2[profile_handler]
    L3[interpret_handler]
    L4[propose_handler]
    BR[Bedrock Runtime]
  end

  subgraph engine [meshflow.spreadsheet]
    PARSER[parser]
    PROF[profiler]
    INTERP[interpret]
    PROP[propose]
    XFORM[transform]
    JOBS[jobs]
  end

  subgraph storage [Lake / local data dir]
    JOBS3[governance/spreadsheet_engine/jobs/]
    CAT[governance/spreadsheet_engine/catalog/]
    KB[governance/spreadsheet_engine/knowledge/]
    SILVER[silver/reference/]
  end

  UI --> SVC
  SVC --> JOBS
  SVC --> SFN
  SFN --> L1 --> L2 --> L3 --> L4
  L1 & L2 & L3 & L4 --> JOBS
  JOBS --> PARSER & PROF & INTERP & PROP
  INTERP & PROP --> BR
  PROP --> XFORM
  JOBS --> JOBS3 & CAT & KB
  JOBS --> SILVER
```

**Package boundaries**

| Package | Responsibility |
|---|---|
| `meshflow-connectors` | Parse, profile, interpret, propose, transform, jobs, Lambda handlers |
| `meshflow-platform` | S3/local path helpers (`meshflow.storage.paths`) |
| `meshflow-portal` | Upload UI, Step Functions kickoff, approvals, status API |

Connectors depend on platform only for config and storage paths — the engine does not invent ad-hoc S3 key schemes.

---

## Pipeline modules

### Parse (`parser.py`)

`parse_workbook(path)` loads an `.xlsx` workbook with openpyxl (`data_only=True`) and scans each sheet for contiguous table regions.

Detection rules (simplified):

- Skip empty rows; treat two consecutive blank rows as end-of-table
- Require at least two data rows and two non-empty columns
- Header row must look like column labels (not report preamble, phone numbers, long prose)
- Headers are normalized to snake_case (`Customer ID` → `customer_id`)

Output: `spreadsheet_engine_parse` JSON with `tables[]` — each table has `table_id`, sheet coordinates (`header_row`, `data_start_row`, `data_end_row`, `min_col`, `max_col`), `headers`, and `sample_rows`.

### Profile (`profiler.py`)

`profile_tables(parse_payload)` computes per-column statistics from parse samples:

- Inferred type (`string`, `number`, `date`, `email`, `currency`, …)
- Null rate, cardinality, unique ratio
- `likely_key` when uniqueness ≥ 95%
- `key_candidates` at table level

### Interpret (`interpret.py`)

`interpret_tables(parse, profile)` calls Bedrock (Claude Haiku by default) with profiling stats and sample rows. Returns entity proposals: `entity_name`, `purpose`, `grain`, `confidence`, `schema`, `relationships`.

When Bedrock is unavailable or returns invalid JSON, a **heuristic fallback** derives entity name from the sheet title and schema from profiler output (`invoke=False` in tests skips the API call entirely).

### Propose (`propose.py`, `synthesize.py`, `sample.py`)

`propose_transforms(...)` attaches a **transformation spec** to each interpreted table. Proposal priority:

1. **Induced transformation** — for structurally messy layouts (grouped/detail rows, ragged keys), sample rows are cleaned by an oracle model and reverse-engineered into deterministic steps (`group_rows`, `filter_rows`, …). Verification re-applies steps locally and checks row counts.
2. **Bedrock proposal** — full transformation JSON from the LLM when induction does not apply.
3. **Heuristic / knowledge reuse** — match `input_shape.shape_hash` or header similarity against the catalog or knowledge base; reuse prior approved steps when compatibility ≥ 0.8.

`extract_table_sample` reads rows up to a byte budget (default 512 MiB). Oracle prompts use a separate, smaller cap (default 2 MiB) with windowed excerpts via `select_oracle_windows`.

### Transform (`transform.py`)

Transformations are versioned JSON specs applied deterministically to row data:

| Op | Purpose |
|---|---|
| `rename_columns` | Map source headers to schema column names |
| `cast` | Coerce columns to `string`, `number`, `date`, `datetime`, `boolean` |
| `group_rows` | Merge continuation rows (blank key) into the preceding key row |
| `filter_rows` | Keep rows matching a simple expression (`col != null`) |
| `derive_column` | Add computed columns (`first_name + ' ' + last_name`) |

`compute_input_shape` hashes sheet name + normalized headers into `shape_hash` for catalog matching. `apply_transformation` runs steps and projects to `output_shape.schema` when present.

### Materialize (`materialize.py`)

On table approval, `materialize_approved_table` re-reads the full workbook region, applies the approved transformation, and writes parquet to:

```
silver/reference/{entity}/data.parquet
```

Catalog entries record `silver_source`, `silver_entity`, `silver_parquet_key`, and `silver_row_count`.

### Jobs (`jobs.py`)

Central orchestration and persistence:

- `create_job`, `store_upload`, `run_parse`, `run_profile`, `run_interpret`, `run_propose`
- `run_pipeline` — synchronous full pipeline for local dev (`pipeline_handler`)
- Catalog: `save_catalog_entry`, `load_catalog_entry`, `list_catalog_entries`
- Knowledge: `save_knowledge_entry`, `load_knowledge_matches`
- Approvals: `approve_transformation`, `approve_table`, `complete_reload`
- Reload: `run_reload_prepare`, `run_reload_finalize`, `request_schema_rewrite`

Lambda handlers in `handlers.py` wrap the `run_*` functions for Step Functions.

---

## Storage layout

All paths are defined in `meshflow.storage.paths` under `governance/spreadsheet_engine/`:

```
governance/spreadsheet_engine/
  jobs/{job_id}/
    job.json              # job metadata and status
    upload/{filename}     # original .xlsx
    parse.json            # parse output
    profile.json          # profile output
    report.json           # interpreted + proposed tables
    tables/{table_id}.json
  catalog/{catalog_id}.json
  knowledge/{knowledge_id}.json
```

**Job statuses:** `uploaded` → `parsing` → `parsed` → `profiling` → `profiled` → `interpreting` → `interpreted` → `proposing` → `ready` (or `error`).

With `MESHFLOW_S3_BUCKET` set, artifacts are written to S3. Otherwise `MESHFLOW_DATA_DIR` (default `data/`) is used for local development.

---

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `MESHFLOW_S3_BUCKET` | (empty) | S3 bucket for job artifacts; empty → local `MESHFLOW_DATA_DIR` |
| `MESHFLOW_DATA_DIR` | `data` | Local filesystem root when not using S3 |
| `MESHFLOW_BEDROCK_MODEL_ID` | `us.anthropic.claude-haiku-4-5-20251001-v1:0` | Model for interpret / propose / synthesize |
| `MESHFLOW_SPREADSHEET_STATE_MACHINE_ARN` | (derived) | Override Step Functions ARN in portal |
| `MESHFLOW_SPREADSHEET_MAX_SAMPLE_BYTES` | `536870912` (512 MiB) | Max raw sample size for induction |
| `MESHFLOW_SPREADSHEET_ORACLE_PROMPT_BYTES` | `2097152` (2 MiB) | Max bytes sent to oracle / synthesize prompts |
| `AWS_REGION` / `AWS_DEFAULT_REGION` | `us-east-2` | Bedrock and Step Functions region |

---

## Local development

```powershell
# From repo root — editable install of all packages
.\scripts\install_dev.ps1

# Run tests (no Bedrock; invoke=False in unit tests)
cd packages/meshflow-connectors
pytest tests/test_spreadsheet_engine.py -v
```

Minimal local pipeline:

```python
import os
from pathlib import Path

os.environ["MESHFLOW_DATA_DIR"] = "/tmp/meshflow-data"

from meshflow.spreadsheet.jobs import (
    create_job, store_upload, run_pipeline, load_report,
)

workbook = Path("sample.xlsx")
job = create_job(filename=workbook.name, username="dev")
store_upload(job["job_id"], filename=workbook.name, body=workbook.read_bytes())
run_pipeline(job["job_id"])
report = load_report(job["job_id"])
```

Or call stages individually: `run_parse` → `run_profile` → `run_interpret` → `run_propose`.

Use `meshflow.spreadsheet.handlers.pipeline_handler` as a single Lambda entry point for dev convenience.

---

## Deployed infrastructure

`create_spreadsheet_pipeline` in `infra/spreadsheet_pipeline.py` provisions:

| Resource | Handler / name |
|---|---|
| Parse Lambda | `meshflow.spreadsheet.handlers.parse_handler` |
| Profile Lambda | `meshflow.spreadsheet.handlers.profile_handler` |
| Interpret Lambda | `meshflow.spreadsheet.handlers.interpret_handler` |
| Propose Lambda | `meshflow.spreadsheet.handlers.propose_handler` |
| State machine | `{company}-{env}-all-spreadsheet_analyze` |

Chain: **Parse → Profile → Interpret → Propose**. Interpret and propose Lambdas need Bedrock invoke permissions. All Lambdas read/write the data bucket.

---

## Portal API

| Endpoint | Method | Purpose |
|---|---|---|
| `/portal/semantics/source-docs` | GET/POST | Main UI (source `sse`); form actions for upload, approve, reject, chat |
| `/api/spreadsheet-engine/status` | GET | Job status and pipeline stage progress (`job_id` query param) |

Form actions (POST to the source-docs page) include upload, approve/reject transformation, approve table, complete reload, schema rewrite, and table chat. See `spreadsheet_engine/service.py` for the full action surface.

---

## Design notes

**Deterministic replay.** Approved transformations are stored in the catalog and knowledge base. Re-uploads validate against them without calling AI when shapes match. Silver materialization always replays the stored steps — Bedrock is not invoked after approval.

**Messy spreadsheets.** Price lists and similar exports often use grouped rows (item on one line, unit of measure and price on the next). The profiler flags these via `key_candidates` with high null rates; `needs_structural_cleaning` triggers the induce path (`group_rows` + `coalesce_columns`).

**Source Browser integration.** `sse` is registered as a virtual reference source alongside connector sources (`dbc`, etc.). Spreadsheet Engine does not use the MS Learn source-docs gold pipeline — it owns its catalog under `governance/spreadsheet_engine/`.

**Tests.** `packages/meshflow-connectors/tests/test_spreadsheet_engine.py` covers parsing (including report preambles), profiling, transforms, catalog approval, silver materialization, reload validation, and grouped-row induction. Portal rendering tests live in `packages/meshflow-portal/tests/test_spreadsheet_engine.py`.
