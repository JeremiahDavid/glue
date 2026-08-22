# hiveflow-lake

Silver_stg consolidation and Glue/Athena catalog. Prefer opening **this folder** for unpack / consolidate / catalog work.

## Default read set

- `src/hiveflow/silver/`
- `src/hiveflow/catalog/`
- `tests/`

## Contracts

- Read/write via `hiveflow.storage.parquet` and `hiveflow.storage.paths`
- Entity/table naming must stay aligned with connector entity bundles and `project_config` catalog helpers
- Consolidate writes **silver_stg** only. Pinned DNA silver/gold SQL lives in `hiveflow.dna.sql_runtime` and is replayed by the DNA Glue job, not this package.
- Do not import portal UI modules

## Layer note

- **Ingest consolidate** → `silver_stg/` (connector entity tables)
- **Column additions** belonging to DNA → silver SQL pack (DNA Glue job → `silver/` for pack entities only)
- **New fact/cube tables** → gold (DNA Glue job), not silver_stg consolidate

## Do not load

- `hiveflow-portal`, GTM/business docs, connector SOAP/OAuth client details unless changing unpack inputs
