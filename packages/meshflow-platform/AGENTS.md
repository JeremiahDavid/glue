# meshflow-platform

Shared platform contracts. Prefer opening **this folder** as the Cursor workspace for config, lake path, or parquet I/O work.

## Default read set

- `src/meshflow/project_config.py`, `process_config.py`, `config.py`, `secrets_manager.py`
- `src/meshflow/storage/` (`paths.py`, `parquet.py`)
- `src/meshflow/entity_registry.py`, `repo_paths.py`
- `tests/`

## Contracts owned here

- Lake layout: `meshflow.storage.paths` (`raw/` / `silver/` / `gold/dna/` / `governance/`)
- Parquet/JSON I/O: `meshflow.storage.parquet` (not `meshflow.ingest.storage`)
- Repo root discovery: `meshflow.repo_paths.find_project_root()` → root `config.yaml` / `process_config.yaml`
- Connector entity resolution is registered via `entity_registry` — do **not** import `meshflow.bc` / `qbo` / `qbd` / `silver` from this package

## Do not load

- `packages/meshflow-portal`, connector client implementations, GTM/business docs (`../meshflow-business`)
- CDK stacks unless changing naming helpers consumed by infra
