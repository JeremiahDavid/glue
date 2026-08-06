# meshflow-dna

DNA semantic engine (compile / validate / publish / governance). Prefer opening **this folder** for pack and gold-pipeline work.

## Default read set

- `src/meshflow/dna/` (everything **except** `web/`, which lives in `meshflow-portal`)
- Packs/schema: `src/meshflow/dna/packs/`, `src/meshflow/dna/schema/`
- Reporting contract: `src/meshflow/dna/reporting.py` (not under `dna.web`)
- `tests/`

## Hard rule

- **`meshflow.dna` must not import `meshflow.dna.web`.** Portal depends on DNA; never the reverse.
- Reporting boilerplate/schema are DNA-owned (`packs/dbc_reporting_boilerplate.yaml`, `schema/reporting-pack.schema.json`)

## Do not load

- Portal views/app/Cognito (`meshflow-portal`) unless changing a shared reporting pack field
- Connector ingest clients, `../meshflow-business`
