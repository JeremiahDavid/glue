# meshflow-lake

Silver consolidation and Glue/Athena catalog. Prefer opening **this folder** for unpack / consolidate / catalog work.

## Default read set

- `src/meshflow/silver/`
- `src/meshflow/catalog/`
- `tests/`

## Contracts

- Read/write via `meshflow.storage.parquet` and `meshflow.storage.paths`
- Entity/table naming must stay aligned with connector entity bundles and `project_config` catalog helpers
- Do not import portal UI modules

## Do not load

- `meshflow-portal`, GTM/business docs, connector SOAP/OAuth client details unless changing unpack inputs
