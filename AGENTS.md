# Meshflow monorepo — `dna-pipeline-slim` branch

**Branch scope:** QBO / QBD / BC (`dbc`) ingest → bronze/silver → DNA semantic model. Test independently from `main` / `dna-model`.

Open a **single package folder** as the Cursor workspace when possible.

| Task | Open workspace |
|---|---|
| QBO / QBD / BC ingest | `packages/meshflow-connectors` |
| Silver / Glue catalog | `packages/meshflow-lake` |
| DNA compile / semantics / packs | `packages/meshflow-dna` |
| Semantic builder UI | `packages/meshflow-portal` (see `portal/semantics/`) |
| Config / lake paths / parquet I/O | `packages/meshflow-platform` |
| Ingest + DNA CDK | **repo root** (`infra/`, scope `ingest` or `dna`) |

## Pipeline (critical path)

1. **Bronze ingest** — `meshflow-connectors` (`qbo/`, `qbd/`, `bc/`, `ingest/`)
2. **Silver consolidate** — `meshflow-lake` (`silver/`, `catalog/`)
3. **DNA semantic** — `meshflow-dna` (profiling, field semantics, compile/publish)
4. **Semantic builder** — `meshflow-portal` → `dna/web/portal/semantics/`

## Source documentation (ingest + semantics)

| Doc | Purpose |
|---|---|
| `onboarding/quickbooks-online.md` | QBO OAuth, secrets, deploy |
| `onboarding/quickbooks-desktop.md` | QBD QBWC, QWC, SOAP |
| `onboarding/business-central.md` | BC (`dbc`) connector setup |
| `docs/dbc-data-model.md` | BC silver table reference (semantic engine) |
| `docs/business-central-setup.md` | BC API / auth setup |
| `docs/internal-execution-scoping/data-lake-architecture.md` | Bronze/silver layout |
| `docs/internal-execution-scoping/dna-semantic-engine.md` | Semantic init / publish |
| `packages/meshflow-dna/src/meshflow/dna/packs/connector_knowledge/dbc/` | BC semantic hints |
| `packages/meshflow-dna/src/meshflow/dna/packs/connector_knowledge/qbo/` | QBO semantic hints |
| `packages/meshflow-dna/src/meshflow/dna/packs/connector_knowledge/qbd/` | QBD semantic hints |

## Rules

- `meshflow.dna` must not import `meshflow.dna.web`.
- Shared lake I/O: `meshflow.storage.parquet` + `meshflow.storage.paths`.
- Dev install: `.\scripts\install_dev.ps1`
- Marketing site, reporting charts, and global DNS/UI stacks are out of scope on this branch (see `.cursorignore`).

## Deploy (this branch)

```powershell
cdk deploy -c scope=ingest   # bronze + silver refresh + DNA (per company config)
```

See each package's `AGENTS.md` for the default read set.
