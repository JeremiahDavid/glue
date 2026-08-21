# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

**meshflow** is the engineering monorepo for **HiveFlowAI**, a **DMaaS (Data Model as a Service)** platform: it exposes a governed, continuously updated semantic data model (dimensions, facts, relationships, metrics) through APIs so BI tools and AI agents can consume structured meaning without building the model themselves. Three capabilities: **Connect** (source ingest), **DNA Engine** (semantic modeling/governance), **Reporting Engine** (NL reports and portal).

First/reference connector: QuickBooks Online. Also supports QuickBooks Desktop (via Web Connector/SOAP) and Dynamics 365 Business Central (OData). Deploys to AWS via CDK — raw data lands in S3, ingest runs on scheduled Lambda/Step Functions/Glue.

Business/GTM/commercial docs live in the sibling repo `../meshflow-business/` — never load that into engineering tasks.

## Setup

One shared virtualenv for the whole workspace, from repo root:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
.\scripts\install_dev.ps1
```

This does an editable install of every package in `packages/` (platform → connectors → lake → dna → portal → meshflow[dev]) plus AWS CDK libs and pytest. There is no per-package venv; always work from the repo-root `.venv`.

## Tests

Run from repo root (pytest is configured at the root `pyproject.toml` with `testpaths` covering `tests/` and every package's `tests/`):

```powershell
pytest
```

Scope to one package (after activating `.venv`):

```powershell
cd packages/meshflow-connectors
pytest tests/test_spreadsheet_engine.py -v
pytest tests/test_spreadsheet_engine.py::test_name -v   # single test
```

Tests that touch AI (Bedrock, the KPI Generator, Spreadsheet Engine interpret/propose) pass `invoke=False` or otherwise stub the model call — no live Bedrock calls in unit tests.

There is no configured linter/formatter/type-checker (no ruff/black/mypy config in this repo) — don't assume one exists.

## CDK / deploy

```powershell
cdk bootstrap
cdk deploy IngestStack-POC-dev          # one target
cdk deploy --all                        # every non-prod target (prod excluded by default)
cdk deploy -c company=POC -c environment=dev
cdk deploy -c scope=platform GlobalUiStack-dev      # UI/reporting only — skips ingest/DNA, synths much faster
```

CDK entry is `infra/app.py`; scopes are `all` | `ingest` | `platform` (`MESHFLOW_CDK_SCOPE` env or `-c scope=`). `prod` stacks are **not synthesized unless `MESHFLOW_ENVIRONMENT=prod`** is explicitly set, and the active AWS account must match `config.yaml`'s configured `aws.account` for that environment — this is a deliberate guardrail against deploying prod resources into a dev account. See [README.md](README.md) for the full deploy walkthrough (secrets creation, OAuth, per-connector deploy commands).

## Monorepo layout and package boundaries

This is a `packages/*` workspace where each package owns a layer of the data lake / product stack. **Prefer opening a single package folder as the editor workspace** to keep context small — each has its own `AGENTS.md` with a "default read set" and a "do not load" list; read the relevant one before working in that package.

| Package | Owns | Depends on |
|---|---|---|
| `meshflow-platform` | Config (`project_config`, `process_config`), Secrets Manager, lake path layout (`meshflow.storage.paths`), Parquet/JSON I/O (`meshflow.storage.parquet`), entity registry, repo-root discovery | nothing else in-repo |
| `meshflow-connectors` | Source connectors (`bc/`, `qbo/`, `qbd/`), ingest orchestration (`ingest/`), Spreadsheet Engine (`spreadsheet/`) | platform only |
| `meshflow-lake` | Silver_stg consolidation (`silver/`), Glue/Athena catalog (`catalog/`) | platform only |
| `meshflow-dna` | DNA semantic engine: compile/validate/publish/governance, packs, Athena SQL packs, source-docs scrape/gold pipeline | platform (not connectors, not portal) |
| `meshflow-portal` | Portal UI, Cognito auth, charts, reporting surfaces (`src/meshflow/dna/web/`) | dna + platform |
| `meshflow` | Thin CLI entrypoints (`cli.py`) wrapping the other packages | all of the above |

**Hard architectural rule: `meshflow.dna` must never import `meshflow.dna.web`.** Portal (`dna.web`, now physically in the `meshflow-portal` package) depends on DNA; the dependency never goes the other direction. This is enforced by convention, not tooling, so watch for it when adding imports.

Other cross-package rules worth knowing:
- Connectors register entity resolvers via `meshflow.entity_registry`; platform never imports connector-specific modules (`bc`/`qbo`/`qbd`/`silver`).
- Raw S3 key layout is defined once in platform's `storage.paths` — don't invent new key schemes in connectors or lake.
- BC MS Learn source documentation lives in `meshflow-dna` (`meshflow.dna.source_docs*`), even though BC ingest itself lives in connectors.

## Data lake layers (the core mental model)

```
raw/{qbo|qbd|dbc}/{run_id}/{entity}/data.parquet + manifest.json     # connector bronze landing
silver_stg/{source}/{entity}/data.parquet                            # ingest consolidate output — full catalog
silver/{source}/{entity}/data.parquet                                 # DNA-owned — pack entities only
gold/dna/{output_id}/data.parquet                                     # DNA-owned — facts/KPIs
governance/{company}_dna_config/v{semver}/...                         # pinned DNA config + SQL packs
```

- **Ingest consolidate** (meshflow-lake) writes `silver_stg/` only — the full connector entity catalog, one Parquet file per entity, nested QBO/BC fields JSON-encoded as string columns for schema stability.
- **DNA Glue job** (`dna-apply`) copies only pack-referenced entities from `silver_stg` into `silver/`, replays pinned Athena SQL (silver column-adds, then gold facts/KPIs), and writes `gold/dna/*`. Approved SQL is pinned by governance semver (sha256'd in the manifest) and replayed **verbatim** on every scheduled refresh — Bedrock/AI is never called during a refresh, only when a human is drafting a new KPI.
- Silver SQL preserves entity grain (no `GROUP BY`/aggregates); grain-changing logic belongs in gold. At most one canonical silver transform (`enhance__{entity}`) per entity, one unique `grain_columns` set per gold output.
- Connector schedule (bronze + silver_stg) and DNA refresh (silver + gold) are separate Step Functions/EventBridge schedules (06:00 / 07:00 UTC in POC/dev) — see [docs/architecture.md](docs/architecture.md) for the full diagram and CDK stack table.

Two governed authoring flows build on this layered contract and are documented in depth — read the linked doc before working on either:
- **[KPI Generator](docs/kpi-generator.md)** (`meshflow-portal`, `/portal/dna/kpi-generator`) — NL-driven drafting of silver/gold Athena SQL, with a draft → integrity-validate → approve → publish governance workflow.
- **[Spreadsheet Engine](docs/spreadsheet-engine.md)** (`meshflow-connectors` engine + `meshflow-portal` UI) — turns uploaded `.xlsx` workbooks into governed `silver/reference/` entities via parse → profile → interpret (Bedrock) → propose/approve → materialize, then DNA proposes lake joins deterministically (no AI) from grain/keys.

## Configuration

Deployment settings live in root **`config.yaml`** (gitignored secrets, not this file) supporting multiple companies × environments; see [README.md](README.md#configuration) for the full schema. No credentials are ever stored in `config.yaml` — OAuth tokens and app secrets live only in AWS Secrets Manager, created locally via `python scripts/create_secrets.py --file secrets/....yaml`. `secrets/` and `data/` are gitignored.

`MESHFLOW_COMPANY` / `MESHFLOW_ENVIRONMENT` env vars (or CDK `-c company=... -c environment=...`) override `config.yaml`'s `default:` block.
