# Meshflow — Pre-Launch Checklist

Phased business-admin checklist for going from zero to first **paid Meshflow customer**. Complete each phase before moving to the next gate.

**Product:** Meshflow — one **Mesh** (up to 3 systems) + all **applicable catalog Signals**. Free discovery + implementation + 2-week trial; **$4,000 activation + $600/mo** only on conversion.

**Not legal or tax advice.** Have an attorney review contracts; consult a CPA for entity and tax setup.

**Track progress:** [pre-launch-checklist.csv](./pre-launch-checklist.csv)

---

## Phase A — Start discovery outreach (do this now)

Goal: Book discovery calls. You are **not** contracting or touching client systems yet.

### Outreach kit

- [ ] **Prospect list** — 20+ companies in ICP ($2M–$40M trades, field service, manufacturing, or distribution); log in [cold-call-tracker.csv](../../../research/cold-call/cold-call-tracker.csv)
- [ ] **Meshflow positioning internalized** — Lead with *ranked exception queues* (unbilled work, AR, membership gaps), **not** dashboards or generic BI
- [ ] **Segment messaging ready** — [gtm-product-mfg-distribution.md](../gtm-product-mfg-distribution.md) and [industry-system-clusters.md](../industry-system-clusters.md)
- [ ] **Cold call kit** — [cold-call-script.md](../../../research/cold-call/cold-call-script.md) + [founder-credibility-quick.md](../../../research/cold-call/founder-credibility-quick.md) (adapt opener for Meshflow)
- [ ] **Discovery script** — [discovery-interview-script.md](../../../research/cold-call/discovery-interview-script.md) (mfg); [discovery-interview-trades.md](../../../research/cold-call/discovery-interview-trades.md) (trades/construction)
- [ ] **Onboarding fit gate** — Score prospects ≥ **7/10** on [v1-scope.md § Onboarding fit gate](../internal-execution-scoping/v1-scope.md) before agreeing to a trial build

### Scheduling & comms

- [ ] **Calendar link** — Calendly, Google Appointment Schedule, or equivalent (30-min discovery)
- [ ] **Email signature** — Name, phone, one-line **Meshflow** description, calendar link
- [ ] **Honest framing** — Discovery is free; trial is free; no pressure to convert

### Product literacy (internal)

- [ ] **Mesh catalog reviewed** — [mesh-catalog.md](../product-scoping/mesh-catalog.md) + [mesh-node-catalog.md](../product-scoping/mesh-node-catalog.md)
- [ ] **Signal catalog reviewed** — [signal-catalog.md](../product-scoping/signal-catalog.md); know which Signals apply to which system roles
- [ ] **Pricing memorized** — Signals: **$4,000** + **$600/mo** · DNA Beta: **$100/mo** · DNA GA target: **$5,000** + **$1,000/mo** ([meshflow-pricing-sheet.md](../terms/meshflow-pricing-sheet.md))
- [ ] **DNA offering reviewed** — [dna-offering.md](../product-scoping/dna-offering.md) fit gate + workflow A→E

**Not required for Phase A:** LLC, domain, business email, AWS, contracts, invoicing, MVP.

---

## Phase B — Before first Meshflow trial

Goal: Look legitimate and be legally/operationally ready when a prospect agrees to system access and a **free Mesh build + 2-week eval**.

### Business structure

- [ ] **Review employment agreement** — AllCloud moonlighting, IP assignment, non-compete (**do this first**)
- [ ] **Form LLC** — North Carolina filing (~$125); obtain EIN from IRS
- [ ] **Business bank account** — Separate from personal; tied to LLC EIN
- [ ] **Domain registered** — e.g. `getmeshflow.io`, `meshflow.com`, or other Meshflow-branded domain
- [ ] **Business email** — `you@yourdomain.com` via Google Workspace or equivalent
- [ ] **Support email planned** — e.g. `support@yourdomain.com` (can alias to inbox until volume warrants split)

### Customer-facing presence

- [ ] **Landing page** — Meshflow value prop: Mesh + Signals, exception queues, free trial; calendar link
- [ ] **One-pager PDF** — Meshflow positioning (exception queues, not dashboard suite); export from credibility doc or [meshflow-pricing-sheet.md](../terms/meshflow-pricing-sheet.md) intro sections
- [ ] **Pricing one-pager PDF** — [meshflow-pricing-sheet.md](../terms/meshflow-pricing-sheet.md) with `[bracketed]` fields filled

### Legal (templates — attorney review recommended)

- [ ] **Mutual NDA** — Before ERP/FSM exports, QuickBooks access, or sensitive data
- [ ] **Meshflow trial terms signed** — [meshflow-trial-terms.md](../terms/meshflow-trial-terms.md)
- [ ] **Bracket fields filled in trial template** — LLC legal name, address, business email, systems, Signal checklist, go-live/end dates

### AWS & platform (Meshflow production account)

Meshflow runs on provider-owned AWS infrastructure. Before first client data:

- [ ] **Meshflow production AWS account** — Separate from personal; root MFA enabled
- [ ] **Billing alerts** — Thresholds set (e.g. $50 / $100 / $500)
- [ ] **Default region** — `us-east-1` unless client requirement dictates otherwise
- [ ] **Core services provisioned** — S3 (raw + curated per tenant), AWS Glue Data Catalog, Athena, Lambda/EventBridge (ingest + refresh), Secrets Manager, CloudWatch
- [ ] **Tenant isolation** — Dedicated S3 buckets, Meshflow database, and Secrets Manager paths per client; no cross-tenant data commingling
- [ ] **CI/CD deploy path** — GitHub Actions or CodePipeline; production deploys from CI, not engineer laptops
- [ ] **Secrets hygiene** — Connector credentials in Secrets Manager only; no creds in git
- [ ] **Subprocessor list drafted** — Match actual stack for MSA §7 ([meshflow-msa-template.md](../terms/meshflow-msa-template.md))

### Signal delivery channel

- [ ] **Delivery channel chosen** — Email briefing (v1 default), QuickSight, or Meshflow app — fixed at kickoff per trial terms
- [ ] **Transactional email** — SPF/DKIM on domain if delivering Signal briefings via email (e.g. SendGrid, SES, Postmark)
- [ ] **Briefing template** — Ranked exception list + provenance links tested on sample data

### Product / delivery

- [ ] **Meshflow MVP end-to-end** — Source → ingest → entity resolution → published snapshot → Signal delivery on **test tenant**
- [ ] **First playbook ready** — ERP/FSM + QuickBooks column maps per [v1-scope.md](../internal-execution-scoping/v1-scope.md) (P0 system from discovery)
- [ ] **Review queue admin** — Internal tool/process to confirm/reject entity links before Signals go live
- [ ] **Mesh implementation runbook** — Kickoff → access → first publish (target ≤5 business days) → tuning week → go-live
- [ ] **Trial success criteria template** — Agree upfront: Mesh nodes (≤3), Signal checklist, delivery channel, acceptance test (e.g. top 5 queue items are real)
- [ ] **Meshflow SOW draft accessible** — [sow-template-meshflow.md](../terms/sow-template-meshflow.md) for scope reference during trial (signed at conversion, not trial start)

**Not required for Phase B:** Invoicing, Meshflow MSA, E&O insurance (unless prospect requires it).

---

## Phase C — Before first paid Meshflow customer

Goal: Convert trial to **$4,000 activation + $600/mo** without scrambling for paperwork.

### Commercial

- [ ] **Meshflow MSA** — [meshflow-msa-template.md](../terms/meshflow-msa-template.md); all `[brackets]` replaced; subprocessor table matches live stack
- [ ] **Meshflow SOW** — [sow-template-meshflow.md](../terms/sow-template-meshflow.md); Mesh nodes, Signal IDs, delivery channel, dates filled
- [ ] **Pricing sheet (client PDF)** — [meshflow-pricing-sheet.md](../terms/meshflow-pricing-sheet.md)
- [ ] **W-9** — Generated from LLC EIN; ready when controller asks
- [ ] **Attorney review** — Scheduled or completed before first real signature

### Invoicing & payments

- [ ] **Invoicing tool** — Stripe Invoicing, Wave (free), or QuickBooks Simple Start
- [ ] **Invoice template** — LLC legal name, address, EIN; line items: Mesh activation ($4,000), monthly subscription ($600); Net 15
- [ ] **Payment method tested** — ACH/card → business bank account
- [ ] **Conversion invoice ready** — $4,000 activation due on SOW signature; monthly billing start date documented

### Risk & compliance

- [ ] **E&O / professional liability insurance** — ~$500–1,500/yr; certificate available on request (MSA §11)
- [ ] **Data handling in MSA** — Client owns data; Provider processes; delete/return on termination (trial terms §5 aligned)
- [ ] **Subprocessor list finalized** — AWS services + email/delivery provider; notify process defined

### Post-conversion delivery

- [ ] **Onboarding checklist** — Access confirmation, kickoff recap, refresh schedule, named users (≤5), handoff doc
- [ ] **Support channel live** — `[support email]` in MSA §12; 1 business day response SLA documented
- [ ] **Tuning → steady-state plan** — Days 6–10 false-positive fixes per [v1-scope.md](../internal-execution-scoping/v1-scope.md); client admin for review queue identified

---

## Phase gates (don't skip)

| Gate | Requirement | If you skip it |
|---|---|---|
| **A → discovery calls** | Phase A complete | Low risk — research only |
| **B → Meshflow trial** | LLC, NDA, Meshflow trial terms, domain/email, AWS MVP, delivery channel | Liability exposure; can't deliver Signals; looks unprepared |
| **C → paid contract** | Meshflow MSA, Meshflow SOW, invoicing, W-9 | Controller blocks payment; no enforceable Mesh/Signal scope |

---

## Quick reference: what to send when

| Moment | Send |
|---|---|
| After discovery interest | One-pager PDF + [meshflow-pricing-sheet.md](../terms/meshflow-pricing-sheet.md) (or PDF) + calendar link |
| They ask "how much?" | [meshflow-pricing-sheet.md](../terms/meshflow-pricing-sheet.md) — emphasize **$0 trial** |
| Trial agreed | Mutual NDA + [meshflow-trial-terms.md](../terms/meshflow-trial-terms.md) |
| Trial converts | [meshflow-msa-template.md](../terms/meshflow-msa-template.md) + [sow-template-meshflow.md](../terms/sow-template-meshflow.md) + **$4,000** activation invoice |
| Monthly ongoing | **$600/mo** invoice (Net 15) |

**Use Meshflow contracts only** — [../terms/](../terms/) (trial, MSA, SOW, pricing).

---

## Meshflow commercial sequence (reminder)

```
Discovery ($0)  →  Free Mesh + Signal build ($0)  →  2-week trial ($0)
                                                      ├─ Convert → MSA + SOW → $4,000 + $600/mo
                                                      └─ Walk away → $0
```

---

## Related

| File | Purpose |
|---|---|
| [pre-launch-checklist.csv](./pre-launch-checklist.csv) | Trackable task list |
| [../terms/](../terms/) | Meshflow trial, MSA, SOW, pricing |
| [../internal-execution-scoping/v1-scope.md](../internal-execution-scoping/v1-scope.md) | v1 scope, fit gate, onboarding timeline |
| [../gtm-product-mfg-distribution.md](../gtm-product-mfg-distribution.md) | Segment messaging and launch SKUs |

---

## Revision log

| Date | Change |
|---|---|
| 2026-07-22 | Initial Meshflow business-admin pre-launch checklist |
| 2026-07-22 | Removed MAP and legacy product references |
