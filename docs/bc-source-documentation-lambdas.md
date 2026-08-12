# BC source documentation Lambdas

Global Microsoft Learn documentation pipeline for Dynamics 365 Business Central (DBC), plus **per-client gold merge** of overlays. Owned by **meshflow-connectors** (`meshflow.bc.source_docs*`).

| Scope | Stack | Bucket |
|---|---|---|
| Global scrape / relationships / tags / schemas | **SourceDocsStack** (`infra/stacks/source_docs_stack.py`) | `s3://hiveflowai-source-documentation/` |
| Client overlay → gold merge | **DnaStack** (`infra/stacks/dnastack_poc.py`) | Company lake (`meshflow-{company}-{account}-{region}`) |

**Audience:** Internal engineering.

---

## Pipeline

```text
EventBridge (every 14 days)
        |
        v
platform-{env}-bc-source-docs-scrape
        |  writes dbc/entity_properties.yaml
        |  on success, async-invokes ↓
        +------------------+------------------+
        |                                     |
        v                                     v
platform-{env}-bc-source-docs-relationships   platform-{env}-bc-source-docs-tags
        |                                     |
        v                                     v
dbc/entity_relationships.yaml                 dbc/entity_property_tags.yaml

Per client (manual or scheduled invoke):
{company}-{env}-bc-source-docs-gold
        |  reads global dbc/*.yaml
        |  reads client governance/.../dbc/{same filenames} overlays
        |  validates against dbc/schemas/*
        v
governance/source_semantic_reference/dbc/gold/*.yaml
```

| Env example | Scrape | Relationships | Tags | Gold (per company) |
|---|---|---|---|---|
| `dev` / POC | `platform-dev-bc-source-docs-scrape` | `platform-dev-bc-source-docs-relationships` | `platform-dev-bc-source-docs-tags` | `poc-dev-bc-source-docs-gold` |

CDK stack names: `SourceDocsStack-{environment}`, `DnaStack-{company}-{environment}`.

---

## 1. Scrape — `platform-{env}-bc-source-docs-scrape`

| | |
|---|---|
| **Handler** | `meshflow.bc.source_docs_handler.lambda_handler` |
| **Schedule** | EventBridge rate: every **14 days** |
| **Timeout / memory** | 15 min / 512 MB |
| **Writes** | `s3://hiveflowai-source-documentation/dbc/entity_properties.yaml` |

Scrapes Microsoft Learn APV2 resource **Properties** tables for mapped BC entities and publishes a catalog of property name / type / description per silver entity.

After a successful **publish**, it async-invokes (`InvocationType=Event`) the relationships and tags Lambdas. Skip either follow-on with event flags `skip_relationships` or `skip_tags`.

**Manual invoke payload (example):**

```json
{
  "source": "dbc",
  "delay_seconds": 0.35
}
```

**Local scrape (no Lambda):**

```powershell
python scripts/scrape_bc_source_docs.py --output tmp/dbc_entity_properties.yaml
```

---

## 2. Relationships — `platform-{env}-bc-source-docs-relationships`

| | |
|---|---|
| **Handler** | `meshflow.bc.source_docs_relationships_handler.lambda_handler` |
| **Trigger** | Async invoke from scrape after successful publish |
| **Timeout / memory** | 5 min / 512 MB |
| **Reads** | `dbc/entity_properties.yaml` |
| **Writes** | `dbc/entity_relationships.yaml` |
| **Model** | Bedrock Claude Haiku 4.5 (`MESHFLOW_BEDROCK_MODEL_ID`) |

Derives PK / FK relationships from property descriptions:

- Description contains **"unique ID"** → primary key
- Description contains **"ID"** without **"unique"** → foreign key
- On `*_line` / `*_lines` tables, **`documentId`** maps deterministically to the header table (strip trailing `line`/`lines`, then match the plural silver name, e.g. `sales_order_lines` → `sales_orders`)
- Remaining FKs are resolved in **one** Bedrock call (numbered FK descriptions + allowed table names only)

**Output shape (per table):**

```yaml
tables:
  sales_invoice_lines:
    PK: id
    relationships:
      - target: sales_invoices
        PK: id
        FK: documentId
      - target: items
        PK: id
        FK: itemId
```

**Local:**

```powershell
python scripts/build_bc_source_relationships.py --input tmp/dbc_entity_properties.yaml --output tmp/dbc_entity_relationships.yaml
```

---

## 3. Tags — `platform-{env}-bc-source-docs-tags`

| | |
|---|---|
| **Handler** | `meshflow.bc.source_docs_tags_handler.lambda_handler` |
| **Trigger** | Async invoke from scrape after successful publish |
| **Timeout / memory** | 15 min / 1024 MB |
| **Reads** | `dbc/entity_properties.yaml` |
| **Writes** | `dbc/entity_property_tags.yaml` |
| **Model** | Bedrock Claude Haiku 4.5 |

Generates short conceptual tags for each property from its description in parent-entity context (e.g. `order status`, `bill to customer`). Tags are phrases of **5 words or less**.

Currently calls Bedrock **once per entity** (~70 calls for the full DBC catalog). Rough ballpark per full run: **~$0.20–$0.60**, **~4–8 minutes** (worst case approaching the 15‑minute timeout).

**Output shape (mirrors tables catalog, tags instead of type/description):**

```yaml
tables:
- silver_entity: sales_orders
  properties:
  - name: status
    tags:
    - order status
  - name: billToCustomerNumber
    tags:
    - bill to customer
```

**Local:**

```powershell
python scripts/build_bc_source_tags.py --input tmp/dbc_entity_properties.yaml --output tmp/dbc_entity_property_tags.yaml
```

---

## 4. Client gold merge — `{company}-{env}-bc-source-docs-gold`

| | |
|---|---|
| **Handler** | `meshflow.bc.source_docs_gold_handler.lambda_handler` |
| **Stack** | DnaStack (per company) |
| **Timeout / memory** | 5 min / 512 MB |
| **Reads (global)** | `s3://hiveflowai-source-documentation/dbc/{artifact}.yaml` |
| **Reads (client)** | `s3://{lake}/governance/source_semantic_reference/dbc/{artifact}.yaml` overlays |
| **Writes (gold)** | `s3://{lake}/governance/source_semantic_reference/dbc/gold/{artifact}.yaml` |
| **Schemas** | Validates global + overlay + gold; optionally publishes schemas to `dbc/schemas/` |

Gold files use the **same schema** as the global catalogs (`kind: ms_learn_entity_*` without `_overlay`). Merge order: start from global → apply `exclude` → apply `addition`.

### Client overlay layout

Same filenames as global, under the company lake:

```text
governance/source_semantic_reference/dbc/
  entity_properties.yaml          # overlay (kind: *_overlay)
  entity_relationships.yaml
  entity_property_tags.yaml
  gold/
    entity_properties.yaml        # merged (global schema)
    entity_relationships.yaml
    entity_property_tags.yaml
```

### Overlay example (`entity_properties.yaml`)

```yaml
source: dbc
kind: ms_learn_entity_properties_overlay
description: POC customizations for MS Learn tables
exclude:
  tables:
    - aged_accounts_receivables
  properties:
    - silver_entity: sales_orders
      names: [odataEtag]
addition:
  properties:
    - silver_entity: sales_orders
      properties:
        - name: customStatus
          type: string
          description: Client-specific status code
  tables:
    - silver_entity: custom_mapping
      properties:
        - name: id
          type: GUID
          description: Unique ID of the custom mapping
```

### Per-tag excludes (`entity_property_tags.yaml` overlay)

```yaml
source: dbc
kind: ms_learn_entity_property_tags_overlay
exclude:
  tags:
    - silver_entity: sales_orders
      name: status
      tags: [order status]
```

Merge strips the listed tag strings from that property. If the property’s `tags` list becomes empty, the property row is dropped from the tags catalog.

### Manual invoke

```json
{
  "source": "dbc",
  "seed_missing_overlays": true,
  "publish_schemas": true
}
```

**Portal inspector (alongside Semantic Builder):** `/portal/semantics/source-docs`

- Reads the three gold YAML files for the client/source
- Admins can **Remove** tables / relationships / tags (writes overlay `exclude`), **Undo** pending excludes, then **Submit changes** to run gold merge and snapshot overlays+gold under `versions/vN`
- **Version history** at the bottom supports Restore (rewrites live overlays + gold; records a new restored version)
- When gold is empty, **Build Semantic Model** invokes `{company}-{env}-bc-source-docs-gold`

**Local:**

```powershell
$env:MESHFLOW_S3_BUCKET = "meshflow-poc-749794722426-us-east-2"
python scripts/build_bc_source_docs_gold.py --seed-missing-overlays --publish-schemas
```

Publish schemas only:

```powershell
python scripts/publish_bc_source_docs_schemas.py
```

---

## Schemas (global accountability)

JSON Schema contracts live in-package at `meshflow.bc.source_docs_schemas/` and are published to:

`s3://hiveflowai-source-documentation/dbc/schemas/`

| File | Validates |
|---|---|
| `entity_properties.schema.json` | Global + gold properties catalogs |
| `entity_properties.overlay.schema.json` | Client properties overlay |
| `entity_relationships.schema.json` | Global + gold relationships |
| `entity_relationships.overlay.schema.json` | Client relationships overlay |
| `entity_property_tags.schema.json` | Global + gold tags |
| `entity_property_tags.overlay.schema.json` | Client tags overlay |

---

## S3 object keys

| Key | Kind | Produced by |
|---|---|---|
| `dbc/entity_properties.yaml` | `ms_learn_entity_properties` | scrape |
| `dbc/entity_relationships.yaml` | `ms_learn_entity_relationships` | relationships |
| `dbc/entity_property_tags.yaml` | `ms_learn_entity_property_tags` | tags |
| `dbc/schemas/*.schema.json` | JSON Schema | `publish_source_docs_schemas` / gold job |
| `{lake}/governance/.../dbc/*.yaml` | `*_overlay` | client (or gold job seed) |
| `{lake}/governance/.../dbc/gold/*.yaml` | global kinds | gold merge |
| `{lake}/governance/.../dbc/versions/manifest.yaml` | version index | portal submit / restore |
| `{lake}/governance/.../dbc/versions/vN/{overlays,gold}/*.yaml` | snapshot | portal submit / restore |

Env overrides (optional):

- `MESHFLOW_SOURCE_DOCS_BUCKET`
- `MESHFLOW_SOURCE_DOCS_OBJECT_KEY`
- `MESHFLOW_SOURCE_DOCS_RELATIONSHIPS_OBJECT_KEY`
- `MESHFLOW_SOURCE_DOCS_TAGS_OBJECT_KEY`
- `MESHFLOW_SOURCE_DOCS_RELATIONSHIPS_FUNCTION`
- `MESHFLOW_SOURCE_DOCS_TAGS_FUNCTION`
- `MESHFLOW_BEDROCK_MODEL_ID`
- `MESHFLOW_S3_BUCKET` (client lake; gold Lambda)

---

## Deploy

```powershell
cdk deploy SourceDocsStack-dev
cdk deploy DnaStack-POC-dev
```

Code package: shared meshflow Lambda bundle (`lambda_bundle.meshflow_lambda_runtime`, profile `full`).

---

## Code map

| Concern | Module |
|---|---|
| Scrape + catalog build | `packages/meshflow-connectors/src/meshflow/bc/source_docs.py` |
| Scrape Lambda entry | `.../source_docs_handler.py` |
| Relationships | `.../source_docs_relationships.py` (+ `_handler.py`) |
| Property tags | `.../source_docs_tags.py` (+ `_handler.py`) |
| JSON Schema | `.../source_docs_schema.py` + `source_docs_schemas/` |
| Overlay merge | `.../source_docs_merge.py` |
| Gold job | `.../source_docs_gold.py` (+ `_handler.py`) |
| Path helpers | `meshflow.storage.paths` (`governance_source_docs_*`) |
| CDK (global) | `infra/stacks/source_docs_stack.py` |
| CDK (client gold) | `infra/stacks/dnastack_poc.py` |
| Package notes | `packages/meshflow-connectors/AGENTS.md` |
