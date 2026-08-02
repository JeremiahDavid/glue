# HiveFlowAI custom domain (hive-flow-ai.com)

Route 53, ACM TLS, and API Gateway custom domain for the HiveFlowAI UI are provisioned by **`UiStack-POC-dev`** when `ui.domain` is set in `config.yaml`.

## Current config

```yaml
ui:
  domain:
    zone_name: hive-flow-ai.com
    primary_hostname: hive-flow-ai.com
    alternate_hostnames:
      - www
    create_hosted_zone: true
```

This creates:

- Route 53 public hosted zone for `hive-flow-ai.com`
- ACM certificate (DNS-validated) for apex + `www.hive-flow-ai.com`
- API Gateway custom domain mappings (no `/prod` prefix in URLs)
- Alias A records pointing at API Gateway

## Squarespace → Route 53 delegation

DNS is currently at Squarespace. CDK creates a **new Route 53 hosted zone**. You must delegate the domain to AWS:

1. Deploy the stack:
   ```powershell
   cdk deploy UiStack-POC-dev
   ```
2. Copy the **`Route53NameServers`** output (four nameserver hostnames).
3. In **Squarespace** → Domains → `hive-flow-ai.com` → DNS / Nameservers:
   - Switch from Squarespace nameservers to **Custom nameservers**
   - Enter all four Route 53 nameservers from the stack output
4. Wait for propagation (often 15–60 minutes; up to 48 hours).

After delegation:

- ACM certificate validation completes automatically (validation records are in Route 53).
- `https://hive-flow-ai.com/` and `https://www.hive-flow-ai.com/` serve the HiveFlowAI app.
- Client portal: `https://hive-flow-ai.com/portal/login`

## Stack outputs

| Output | Meaning |
|---|---|
| `PrimarySiteUrl` | Main branded URL (`https://hive-flow-ai.com/`) |
| `Route53NameServers` | NS records to set at Squarespace |
| `ApiGatewayUrl` | Default `execute-api` URL (fallback during cutover) |
| `ReportingWebUrl` | Same as primary site URL when domain is configured |

## Reusing an existing hosted zone

If you already created a Route 53 zone manually, set:

```yaml
ui:
  domain:
    zone_name: hive-flow-ai.com
    primary_hostname: hive-flow-ai.com
    alternate_hostnames: [www]
    create_hosted_zone: false
    hosted_zone_id: Z1234567890ABC
```

## Squarespace email / other records

Delegating nameservers to Route 53 **moves all DNS** to AWS. Before cutover:

- Export any Squarespace DNS records you still need (email MX, verification TXT, etc.).
- Recreate them in the Route 53 hosted zone (Console or future CDK records).

## Portal credentials

Custom domain does not change portal auth. Ensure Secrets Manager secret `meshflow-poc-portal-dev` exists (see [dna-semantic-engine.md](../internal-execution-scoping/dna-semantic-engine.md)).

## Branding assets

Logo and symbol PNGs are served from the branding bucket configured in `config.yaml`:

```yaml
ui:
  branding:
    bucket: hive-flow-ai-branding
    symbol_key: "HiveFlowAI Symbol.png"
    logo_key: "HiveFlowAI Logo.png"
```

UiStack grants the UI Lambda read access to that bucket. `/static/hiveflowai-symbol.png` and `/static/hiveflowai-logo.png` load from S3 in AWS; local dev falls back to bundled files under `src/meshflow/dna/web/static/`.

Sync local copies after updating S3:

```powershell
aws s3 cp "s3://hive-flow-ai-branding/HiveFlowAI Symbol.png" src/meshflow/dna/web/static/hiveflowai-symbol.png
aws s3 cp "s3://hive-flow-ai-branding/HiveFlowAI Logo.png" src/meshflow/dna/web/static/hiveflowai-logo.png
```
