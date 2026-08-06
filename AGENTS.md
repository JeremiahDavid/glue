# Meshflow monorepo

Installable packages live under `packages/`. Prefer opening a **single package folder** as the Cursor workspace to keep context small.

| Task | Open workspace |
|---|---|
| Config, paths, parquet I/O | `packages/meshflow-platform` |
| QBO / QBD / BC ingest | `packages/meshflow-connectors` |
| Silver / Glue catalog | `packages/meshflow-lake` |
| DNA compile / governance / packs | `packages/meshflow-dna` |
| Portal UI / Cognito / charts | `packages/meshflow-portal` |
| CDK deploy / cross-package | **repo root** |

## Rules

- Do not load sibling `../meshflow-business` (GTM, terms, product-scoping) into engineering tasks.
- `meshflow.dna` must not import `meshflow.dna.web`.
- Shared lake I/O: `meshflow.storage.parquet` + `meshflow.storage.paths`.
- Dev install: `.\scripts\install_dev.ps1` (editable install of all packages).
- Technical docs: `docs/`. Operator guides: `onboarding/`.

See each package’s `AGENTS.md` for the default read set.
