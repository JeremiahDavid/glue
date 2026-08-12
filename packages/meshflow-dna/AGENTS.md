# meshflow-dna

DNA semantic engine (compile / validate / publish / governance). Prefer opening **this folder** for pack and gold-pipeline work.

## Default read set

- `src/meshflow/dna/` (everything **except** `web/`, which lives in `meshflow-portal`)
- Packs/schema: `src/meshflow/dna/packs/`, `src/meshflow/dna/schema/`
- Reporting contract: `src/meshflow/dna/reporting.py` (not under `dna.web`)
- Athena SQL packs: `sql_pack.py`, `sql_runtime.py`, `schema/sql-pack-manifest.schema.json`
- `tests/`

## Hard rule

- **`meshflow.dna` must not import `meshflow.dna.web`.** Portal depends on DNA; never the reverse.
- Reporting boilerplate/schema are DNA-owned (`packs/dbc_reporting_boilerplate.yaml`, `schema/reporting-pack.schema.json`)

## Layer contract

- **Silver SQL** (`sql/silver`, mode `add_columns`): derived columns on existing entities; replayed after consolidate.
- **Gold SQL** (`sql/gold`, mode `fact_table` / `kpi`): new tables and KPIs; replayed on DNA refresh.
- Approved SQL is immutable for a semver (sha256 in manifest); refreshes never call Bedrock.

## Do not load

- Portal views/app/Cognito (`meshflow-portal`) unless changing a shared reporting pack field
- Connector ingest clients, `../meshflow-business`

## BC profiling rules

Microsoft APV2 baseline rules for semantic profiling live in
`packs/connector_knowledge/dbc/profiling_rules.yaml`. Regenerate from Learn docs:

```powershell
python scripts/scrape_bc_profiling_rules.py
```

At runtime, init/re-run profiling reads **only** the per-source
`latest_profile.yaml` under governance (`source_semantic_reference/{source}/`).
That file is built once (first init) and rebuilt after each semantic model
publish, by merging documentation + all approved builds for the connector.
