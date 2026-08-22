# hiveflow-platform

Shared platform contracts. Prefer opening **this folder** as the Cursor workspace for config, lake path, or parquet I/O work.

## Default read set

- `src/hiveflow/project_config.py`, `process_config.py`, `config.py`, `secrets_manager.py`
- `src/hiveflow/storage/` (`paths.py`, `parquet.py`)
- `src/hiveflow/entity_registry.py`, `repo_paths.py`
- `tests/`

## Contracts owned here

- Lake layout: `hiveflow.storage.paths` (`raw/` / `silver_stg/` / `silver/` / `gold/dna/` / `governance/`)
- Parquet/JSON I/O: `hiveflow.storage.parquet` (not `hiveflow.ingest.storage`)
- Repo root discovery: `hiveflow.repo_paths.find_project_root()` → root `config.yaml` / `process_config.yaml`
- Connector entity resolution is registered via `entity_registry` — do **not** import `hiveflow.bc` / `qbo` / `qbd` / `silver` from this package

## Do not load

- `packages/hiveflow-portal`, connector client implementations, GTM/business docs (`../hiveflow-business`)
- CDK stacks unless changing naming helpers consumed by infra
