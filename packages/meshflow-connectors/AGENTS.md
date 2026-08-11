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
- Client overlays + gold merge: `meshflow.bc.source_docs_gold` writes
  `governance/source_semantic_reference/{source}/gold/` in the company lake bucket

## Do not load

- Portal UI (`meshflow-portal`), DNA compile internals unless fixing an ingest→silver contract
- `../meshflow-business`

## BC source documentation

Refresh Microsoft Learn APV2 Properties tables locally:

```powershell
python scripts/scrape_bc_source_docs.py --output tmp/dbc_entity_properties.yaml
```

Derive PK/FK relationships from the published properties catalog
(`s3://hiveflowai-source-documentation/dbc/entity_properties.yaml`):

```powershell
python scripts/build_bc_source_relationships.py --input tmp/dbc_entity_properties.yaml --output tmp/dbc_entity_relationships.yaml
```

Publishes `s3://hiveflowai-source-documentation/dbc/entity_relationships.yaml` when run without `--input`.
Logic lives in `meshflow.bc.source_docs_relationships`.

Generate conceptual property tags:

```powershell
python scripts/build_bc_source_tags.py --input tmp/dbc_entity_properties.yaml --output tmp/dbc_entity_property_tags.yaml
```

Publishes `s3://hiveflowai-source-documentation/dbc/entity_property_tags.yaml` when run without `--input`.
Logic lives in `meshflow.bc.source_docs_tags`.

Merge global catalogs with client `exclude`/`addition` overlays into lake gold:

```powershell
$env:MESHFLOW_S3_BUCKET = "meshflow-poc-749794722426-us-east-2"
python scripts/build_bc_source_docs_gold.py --seed-missing-overlays --publish-schemas
```

Writes `governance/source_semantic_reference/dbc/gold/*.yaml`. Schemas:
`s3://hiveflowai-source-documentation/dbc/schemas/` (also in `meshflow.bc.source_docs_schemas`).

SourceDocsStack Lambdas (dev example):

- `platform-dev-bc-source-docs-scrape` — biweekly MS Learn scrape
- `platform-dev-bc-source-docs-relationships` — async follow-on after a successful scrape publish
- `platform-dev-bc-source-docs-tags` — async follow-on that tags each property from descriptions

DnaStack (per company):

- `{company}-dev-bc-source-docs-gold` — merge global + client overlays → gold
