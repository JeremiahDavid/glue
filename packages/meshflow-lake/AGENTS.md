# meshflow-lake

Silver consolidation and Glue/Athena catalog. Prefer opening **this folder** for unpack / consolidate / catalog work.

## Default read set

- `src/meshflow/silver/`
- `src/meshflow/catalog/`
- `tests/`

## Contracts

- Read/write via `meshflow.storage.parquet` and `meshflow.storage.paths`
- Entity/table naming must stay aligned with connector entity bundles and `project_config` catalog helpers
- After consolidate, the Lambda may replay pinned **silver** Athena SQL from the DNA governance pack (column additions). That path lives in `meshflow.dna.sql_runtime` and must not invent SQL at refresh time.
- Do not import portal UI modules

## Layer note

- **Column additions** belonging to DNA → silver SQL pack (post-consolidate)
- **New fact/cube tables** → gold (DNA refresh), not silver consolidate

## Do not load

- `meshflow-portal`, GTM/business docs, connector SOAP/OAuth client details unless changing unpack inputs
