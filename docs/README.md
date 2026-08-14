# Meshflow technical docs

Engineering architecture, data-model, and execution specs for the `meshflow` codebase.

**DMaaS (Data Model as a Service)** is the product container: a cloud service that exposes a fully built, governed, continuously updated semantic data model (dimensions, facts, relationships, metrics) through APIs so applications, BI tools, and AI agents can consume structured meaning without building the model themselves. Connect, DNA Engine, and Reporting Engine are capabilities inside DMaaS — see [architecture.md](./architecture.md#product-framing--dmaas).

| Document / folder | Purpose |
|---|---|
| [architecture.md](./architecture.md) | Current-state platform architecture + DMaaS framing |
| [kpi-generator.md](./kpi-generator.md) | KPI Generator portal workflow (draft → review → approve) |
| [dbc-data-model.md](./dbc-data-model.md) | Business Central data model notes |
| [business-central-setup.md](./business-central-setup.md) | BC connector setup |
| [bc-source-documentation-lambdas.md](./bc-source-documentation-lambdas.md) | BC MS Learn source-docs Lambdas (scrape / relationships / tags) |
| [internal-execution-scoping/](./internal-execution-scoping/) | Lake, DNA engine, reconciliation, and related specs |
| [onboarding/hive-flow-ai-domain.md](./onboarding/hive-flow-ai-domain.md) | Domain / DNS onboarding |

Connector operator guides live in [`../onboarding/`](../onboarding/).

Business, GTM, commercial, and product-catalog content lives in the sibling folder [`../../meshflow-business/`](../../meshflow-business/).
