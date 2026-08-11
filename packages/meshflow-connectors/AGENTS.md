# meshflow-connectors

Source connectors and ingest orchestration. Prefer opening **this folder** for QBO / QBD / Business Central ingest work.

## Default read set

- `src/meshflow/bc/`, `qbo/`, `qbd/`
- `src/meshflow/ingest/`
- `src/meshflow/lambda_handler.py`
- `tests/`

## Contracts

- Depend on **platform** only for config, secrets, and `storage.parquet` / `storage.paths`
- Register entity resolvers in each connector’s `entities.py` via `meshflow.entity_registry`
- Raw landing layout is defined by platform path helpers — do not invent new S3 key schemes here
- Global connector docs (MS Learn Properties scrape) live in `meshflow.bc.source_docs` and
  publish to `s3://hiveflowai-source-documentation/{source}/` (biweekly CDK schedule)

## Do not load

- Portal UI (`meshflow-portal`), DNA compile internals unless fixing an ingest→silver contract
- `../meshflow-business`

## BC source documentation

Refresh Microsoft Learn APV2 Properties tables locally:

```powershell
python scripts/scrape_bc_source_docs.py --output tmp/dbc_entity_properties.yaml
```

Scheduled Lambda: `meshflow.bc.source_docs_handler.lambda_handler` (SourceDocsStack).
