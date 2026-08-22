# meshflow-lake

Silver_stg consolidation and Glue/Athena catalog. Prefer opening **this folder** for unpack / consolidate / catalog work.

## Default read set

- `src/meshflow/silver/`
- `src/meshflow/catalog/`
- `tests/`

## Contracts

- Read/write via `meshflow.storage.parquet` and `meshflow.storage.paths`
- Entity/table naming must stay aligned with connector entity bundles and `project_config` catalog helpers
- Consolidate writes **silver_stg** only. Pinned DNA silver/gold SQL lives in `meshflow.dna.sql_runtime` and is replayed by the DNA Glue job, not this package.
- Do not import portal UI modules

## Layer note

- **Ingest consolidate** → `silver_stg/` (connector entity tables)
- **Column additions** belonging to DNA → silver SQL pack (DNA Glue job → `silver/` for pack entities only)
- **New fact/cube tables** → gold (DNA Glue job), not silver_stg consolidate

## Do not load

- `meshflow-portal`, GTM/business docs, connector SOAP/OAuth client details unless changing unpack inputs
