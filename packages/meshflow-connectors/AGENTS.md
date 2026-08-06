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

## Do not load

- Portal UI (`meshflow-portal`), DNA compile internals unless fixing an ingest→silver contract
- `../meshflow-business`
