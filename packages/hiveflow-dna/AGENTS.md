# meshflow-dna

DNA semantic engine (compile / validate / publish / governance). Prefer opening **this folder** for pack and gold-pipeline work.

## Default read set

- `src/meshflow/dna/` (everything **except** `web/`, which lives in `meshflow-portal`)
- Packs/schema: `src/meshflow/dna/packs/`, `src/meshflow/dna/schema/`
- Reporting contract: `src/meshflow/dna/reporting.py` (not under `dna.web`)
- Athena SQL packs: `sql_pack.py`, `sql_runtime.py`, `schema/sql-pack-manifest.schema.json`
- Source docs: `source_docs/` subpackage (`scrape`, `gold`, `overlays`, `handlers/`, `schemas/`)
- `tests/`

## Hard rule

- **`meshflow.dna` must not import `meshflow.dna.web`.** Portal depends on DNA; never the reverse.
- Reporting boilerplate/schema are DNA-owned (`packs/dbc_reporting_boilerplate.yaml`, `schema/reporting-pack.schema.json`)

## Layer contract

- **Silver SQL** (`sql/silver`, mode `add_columns`): per-KPI contributions under `sql/silver/contributions/{entity}/` merge into one canonical `enhance__{entity}` transform per silver entity; replayed by the DNA Glue job from `silver_stg_*` into `silver/`.
- **Gold SQL** (`sql/gold`, mode `fact_table` / `kpi`): new tables and KPIs with unique `grain_columns`; replayed on the same DNA Glue job after silver.
- **Guardrails** (`silver_enhancement.py`, `sql_pack._validate_pack`): silver preserves entity grain; at most one silver transform per `target_entity`; no duplicate gold grains.
- Approved SQL is immutable for a semver (sha256 in manifest); refreshes never call Bedrock.
- DNA refresh Step Functions starts the **dna_apply Glue job** (copy pack-referenced `silver_stg` entities into `silver/`, silver SQL, gold SQL or Python compile fallback). Lambda `dna_publish` remains for governance seed / init-client / compile-validate.
- DNA `silver/` holds only pack entities: silver SQL `target_entity`s and tables gold SQL reads. Ingest `silver_stg/` stays the full catalog.

## Do not load

- Portal views/app/Cognito (`meshflow-portal`) unless changing a shared reporting pack field
- Connector ingest clients, `../meshflow-business`
