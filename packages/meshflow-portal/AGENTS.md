# meshflow-portal

Portal UI, Cognito auth, charts, and reporting surfaces (former `dna/web`). Prefer opening **this folder** for UI work.

## Default read set

- `src/meshflow/dna/web/` (`app.py`, `portal/`, `charts/`, `public/`, `theme.py`, static assets)
- `tests/`

## Contracts

- May import DNA engine + platform (`meshflow.dna.*`, `meshflow.storage.*`, `meshflow.project_config`)
- Reporting pack **load/save/schema** live in `meshflow.dna.reporting` — keep UI rendering here
- Do not add DNA→web imports from the DNA package
- Gold source-docs inspector: `/portal/semantics/source-docs` reads
  `governance/source_semantic_reference/{source}/gold/` and lets admins
  write client overlay excludes, submit gold merge, and restore version snapshots
- KPI Generator: `/portal/dna/kpi-generator` — NL → Athena SQL, manual gold refresh,
  save DNA draft → review → approve ([docs](../../docs/kpi-generator.md))
  approve pins exact SQL under `governance/.../sql/`; refreshes replay verbatim
- Platform admin (`MESHFLOW_UI_MODE=admin`): `dna/web/admin/` — multi-source job
  registry at `admin.hive-flow-ai.com` (GlobalAdmin Cognito pool, separate from client portal)


## Do not load

- Connector clients (`bc`/`qbo`/`qbd` ingest), silver unpack internals, CDK stacks
- `../meshflow-business` (pricing/GTM belong outside this repo)
