"""Mermaid sources for platform admin architecture diagrams."""

from __future__ import annotations

INFRASTRUCTURE_MERMAID = """
flowchart TB
  subgraph Users["Users"]
    Visitor["Public visitors"]
    PortalUser["Portal users"]
    GlobalAdmin["Platform admins"]
  end

  subgraph External["External systems"]
    SQ["Squarespace"]
    QBO["QuickBooks Online"]
    QBD["QuickBooks Desktop + QBWC"]
    Entra["Microsoft Entra ID"]
    BC["Dynamics 365 Business Central"]
  end

  subgraph DNS["GlobalDnsStack"]
    R53["Route 53 hive-flow-ai.com"]
    ACM["ACM certificates"]
    CD_APEX["API GW domain apex / www"]
    CD_POC["API GW domain poc"]
    CD_ADMIN["API GW domain admin"]
  end

  SQ -->|"NS delegated"| R53
  R53 --> ACM
  ACM --> CD_APEX
  ACM --> CD_POC
  ACM --> CD_ADMIN

  subgraph Platform["Platform UI plane"]
    subgraph GlobalUI["GlobalUiStack"]
      GAPI["API Gateway meshflow-global-ui"]
      GLAM["Lambda global-ui MESHFLOW_UI_MODE=global"]
      COG["Cognito portal pool"]
      SES["SES noreply@hive-flow-ai.com"]
    end

    subgraph Reporting["ReportingStack"]
      RAPI["API Gateway meshflow-reporting"]
      RLAM["Lambda reporting-ui MESHFLOW_UI_MODE=reporting"]
    end

    subgraph PlatformAdmin["PlatformAdminStack"]
      AAPI["API Gateway meshflow-platform-admin"]
      ALAM["Lambda admin-ui MESHFLOW_UI_MODE=admin"]
      ACOG["Cognito GlobalAdmin pool"]
    end

    subgraph SourceDocs["SourceDocsStack"]
      SDL["Source-docs Lambdas scrape / relationships / tags"]
      SDB["S3 hiveflowai-source-documentation"]
    end
  end

  Visitor -->|"hive-flow-ai.com"| CD_APEX
  PortalUser -->|"/portal"| CD_APEX
  PortalUser -->|"poc.hive-flow-ai.com"| CD_POC
  GlobalAdmin -->|"admin.hive-flow-ai.com"| CD_ADMIN

  CD_APEX --> GAPI --> GLAM
  CD_POC --> RAPI --> RLAM
  CD_ADMIN --> AAPI --> ALAM

  GLAM --> COG
  GLAM --> SES
  RLAM --> COG
  ALAM --> ACOG
  ALAM -->|"invoke"| SDL
  SDL --> SDB

  subgraph Company["Company data plane"]
    subgraph Ingest["IngestStack"]
      EB_ING["EventBridge schedules"]
      SF_CONN["Step Functions connector pipelines"]
      L_ING["Ingest / silver Lambdas"]
      LAKE["S3 data lake raw / silver / gold"]
      GLUE["Glue catalog"]
      ATH["Athena"]
    end

    subgraph DNA["DnaStack"]
      EB_DNA["EventBridge DNA schedule"]
      SF_DNA["Step Functions dna-refresh"]
      L_DNA["Lambda dna-publish"]
    end
  end

  QBO -->|"OAuth2"| SF_CONN
  Entra --> BC
  BC -->|"OData"| SF_CONN
  QBD -->|"SOAP"| L_ING

  EB_ING --> SF_CONN --> L_ING --> LAKE
  L_ING --> GLUE --> ATH
  EB_DNA --> SF_DNA --> L_DNA -->|"gold/dna"| LAKE
  RLAM -->|"read gold"| LAKE
""".strip()

PIPELINE_MERMAID = """
flowchart LR
  subgraph scheduled["Scheduled data refresh"]
    Sources["Sources BC / QBO / QBD"] --> Bronze["Bronze raw S3"]
    Bronze --> Silver["Silver consolidate"]
    Silver --> Compile["Compile pinned DNA pack"]
    Compile --> Gold["Gold semantic layer"]
    Gold --> Portal["Client portal reads gold"]
  end

  subgraph ondemand["On-demand requirement updates"]
    Docs["Customer docs"] --> DNAEngine["DNA Engine"]
    Docs --> ReportingEngine["Reporting Engine"]
    DNAEngine --> DNAPack["DNA yaml / md"]
    ReportingEngine --> ReportingPack["Reporting yaml / md"]
    DNAPack --> DNACode["SQL / Python semantics"]
    ReportingPack --> UICode["Portal layout code"]
  end

  DNACode -.->|"pins pack"| Compile
  UICode -.->|"binds to gold"| Portal
""".strip()
