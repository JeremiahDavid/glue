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
  `governance/source_semantic_reference/{source}/gold/` (no builder steps/gates)


## Do not load

- Connector clients (`bc`/`qbo`/`qbd` ingest), silver unpack internals, CDK stacks
- `../meshflow-business` (pricing/GTM belong outside this repo)
