# meshflow-dna

DNA semantic engine (compile / validate / publish / governance). Prefer opening **this folder** for pack and gold-pipeline work.

## Default read set

- `src/meshflow/dna/` (everything **except** `web/`, which lives in `meshflow-portal`)
- Packs/schema: `src/meshflow/dna/packs/`, `src/meshflow/dna/schema/`
- Reporting contract: `src/meshflow/dna/reporting.py` (not under `dna.web`)
- Athena SQL packs: `sql_pack.py`, `sql_runtime.py`, `schema/sql-pack-manifest.schema.json`
- Source docs gold: `source_docs_reference.py`, `source_docs_overlays.py`
- `tests/`

## Hard rule

- **`meshflow.dna` must not import `meshflow.dna.web`.** Portal depends on DNA; never the reverse.
- Reporting boilerplate/schema are DNA-owned (`packs/dbc_reporting_boilerplate.yaml`, `schema/reporting-pack.schema.json`)

## Layer contract

- **Silver SQL** (`sql/silver`, mode `add_columns`): derived columns on existing entities; replayed after consolidate.
- **Gold SQL** (`sql/gold`, mode `fact_table` / `kpi`): new tables and KPIs; replayed on DNA refresh.
- Approved SQL is immutable for a semver (sha256 in manifest); refreshes never call Bedrock.
- DNA refresh Step Functions invokes **publish only** (SQL pack replay, else Python compile fallback). No semantic-init / Semantic Builder gate.

## Do not load

- Portal views/app/Cognito (`meshflow-portal`) unless changing a shared reporting pack field
- Connector ingest clients, `../meshflow-business`
