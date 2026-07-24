# MAP Meshflow — Master Services Agreement (MSA)

**Template only — not legal advice.** Replace all `[bracketed]` fields. Have a qualified attorney review before use.

This MSA governs Client's use of **MAP Meshflow** ("**Meshflow**") and related services. **Specific Mesh systems, Signals, fees, and deliverables** for each engagement are defined in one or more **Statements of Work (SOWs)** signed by both parties. The first Meshflow SOW is typically [sow-template-meshflow.md](./sow-template-meshflow.md).

**Effective date:** `[Date]`

---

## Parties

**Provider:** `[LLC Legal Name]` ("Provider"), `[State]` LLC  
Address: `[Business Address]`  
Contact: Jeremiah Stephens · `[business email]` · (478) 550-0087

**Client:** `[Client Legal Name]` ("Client")  
Address: `[Client Address]`  
Contact: `[Client Contact Name, Title]` · `[email]`

---

## 1. Services

1.1 **Product.** Provider offers **MAP Meshflow** — a hosted product that connects Client's operational and financial systems into a **Mesh**, reconciles entities across those systems, and delivers **Signals**: ranked exception queues, briefings, and metric views — not a custom BI project, dashboard suite, or open-ended analytics engagement.

1.1.1 **Mesh.** A Mesh is a named set of connected source systems—or one cataloged full ERP with cross-module semantic join paths—typically up to three systems and optionally a fourth if stated in a SOW. The Mesh defines *what can be linked*.

1.1.2 **Signal.** A Signal is a productized insight pack for one operational metric or exception type on a Mesh (for example, closed work not invoiced, outstanding AR, or membership visit gaps). Each Signal has a fixed catalog definition, inputs, output shape, and known limitations.

1.2 **Statements of Work.** Provider performs Mesh activation, Signal configuration, and support as described in each SOW. SOWs typically include a **Mesh activation fee**, a **monthly Mesh subscription** (covering refresh and **all applicable catalog Signals** for that Mesh), named systems, a Signal turn-on checklist, delivery channel, and timelines. Optional add-ons (fourth system, second Mesh, extra seats, non-catalog work) are stated in the SOW or a change order.

1.2.1 **Standardized product — not custom consulting.** Meshflow is a **productized, catalog-based** offering optimized for **fast time-to-value** (typically **2–4 weeks** to handoff). Provider delivers **standard Mesh and Signal templates** from Provider's catalogs — not client-specific business logic, proprietary formulas, bespoke attribution models, or non-catalog metrics unless expressly added via change order or a separate professional services engagement.

1.2.2 **Read-only.** Unless a SOW expressly states otherwise, Provider's services are **read-only** with respect to Client source systems. Provider does not write to, modify, or sync data into Client's ERP, FSM, accounting, CRM, or other operational systems.

1.3 **Order of precedence.** If this MSA and a SOW conflict on **fees, scope, deliverables, Mesh/Signal selection, or timeline**, the **SOW controls**. For all other matters, this MSA controls.

1.4 **Prior trial or discovery work.** Provider's standard Meshflow offer includes **free discovery, free Mesh/Signal implementation, and a free 2-week evaluation trial** under a separate trial agreement ([meshflow-trial-terms.md](./meshflow-trial-terms.md)). If Client completed that trial (or documented discovery) before signing this MSA and an initial Meshflow SOW, Provider carries forward configuration for the same Mesh and Signals. Client pays **Mesh activation and monthly subscription** on conversion as stated in the SOW; Client does **not** pay a second implementation fee for identical trial scope.

1.5 **Changes.** Changes to SOW scope — including Mesh systems, Signal selection, thresholds, delivery channel, or timeline — require a written **change order** signed by both parties.

1.6 **Legacy products.** Older MAP **Bedrock** (dashboard suite) materials may exist in Provider's contract archive. This MSA is for **Meshflow** engagements only unless the parties agree in writing to combine products.

---

## 2. Fees & payment

2.1 **Fees.** Client pays fees stated in each SOW. The standard commercial model after a successful free trial is a one-time **Mesh activation** and a recurring **monthly Mesh subscription** that includes Mesh refresh and **all catalog Signals applicable to that Mesh** (no per-Signal fee). Discovery and standard Mesh/Signal implementation for the evaluation trial are **$0** under the trial agreement; activation and subscription apply only on conversion to a paid SOW. Optional fees (e.g. fourth system, second Mesh, seats beyond five, professional services) appear only when stated in the SOW or a change order. List prices are published in [meshflow-pricing-sheet.md](./meshflow-pricing-sheet.md) unless the SOW states otherwise.

2.2 **Invoicing.** Provider invoices Client per the SOW. Unless stated otherwise: **Net 15** from invoice date.

2.3 **Taxes.** Fees exclude taxes. Client pays applicable sales, use, or VAT taxes unless Client provides a valid exemption certificate.

2.4 **Late payment.** Overdue amounts accrue interest at **1.5% per month** (or the maximum allowed by law, if lower). Provider may suspend services after **15 days** written notice of non-payment.

2.5 **Professional services.** Work outside SOW scope is billed at **$150/hour** unless a change order states a different rate.

2.6 **No refunds.** Activation fees are non-refundable once implementation begins, except as required by law or expressly stated in a SOW.

---

## 3. Term & termination

3.1 **MSA term.** This MSA begins on the effective date and continues until terminated under this Section 3.

3.2 **Subscription term.** Monthly subscriptions renew **month-to-month** until terminated. The initial subscription start date is stated in the applicable SOW.

3.3 **Termination for convenience.** Either party may terminate the **subscription** on **30 days' written notice**. Termination does not relieve Client of payment obligations for fees accrued before the effective termination date.

3.4 **Termination for cause.** Either party may terminate on **15 days' written notice** if the other party materially breaches and fails to cure within that period. Provider may terminate immediately if Client fails to pay undisputed fees within **30 days** of notice.

3.5 **Effect of termination.**

- Client access to Meshflow (Mesh refresh and Signal delivery) ends on the termination effective date (or as otherwise agreed for wind-down).
- Client pays all outstanding fees through the end of the notice period.
- Provider will handle Client data per **Section 5.4**.
- Sections that by nature should survive (confidentiality, data, IP, disclaimers, liability, general) survive termination.

3.6 **Implementation in progress.** If Client terminates during an active Meshflow SOW after work has begun, Client pays activation fees due under the SOW and any approved change orders; Provider delivers work product completed to date in Provider's standard format.

---

## 4. Client responsibilities

Client will:

- Designate a primary contact authorized to approve scope and grant system access
- Provide timely **read-only access** or scheduled exports to all Mesh systems named in the SOW
- Maintain accuracy of credentials, file drops (if any), and internal approvals
- Use Meshflow for lawful internal business purposes only
- Not use Meshflow output for regulatory filings, audited financials, tax positions, or safety-critical decisions without independent verification
- Not reverse-engineer, resell, or sublicense the platform except as expressly permitted
- Provide and maintain a written list of authorized named users (maximum **five (5)** under a standard Meshflow SOW, unless a SOW or change order states otherwise)
- Accept that Meshflow delivers **catalog Mesh + Signal templates** — missing or unsupported source fields may result in a Signal marked limited / N/A rather than a custom rebuild

Client is responsible for its source systems, network connectivity, file-drop discipline, and internal users' actions.

---

## 5. Data & confidentiality

5.1 **Client data ownership.** Client retains all right, title, and interest in **Client Data** — data Client provides or that is extracted from Client's systems for Meshflow.

5.2 **Provider use.** Provider processes Client Data **solely** to deliver the services, maintain and improve Meshflow (using **aggregated, anonymized** data only — never Client-identifiable content), and comply with law.

5.3 **Security.** Provider implements reasonable administrative, technical, and organizational measures appropriate to the nature of the services. No method of transmission or storage is 100% secure.

5.4 **Return & deletion.** Within **30 days** of subscription termination (or sooner if Client requests), Provider will delete Client Data from production systems, except: (a) backups on normal rotation not exceeding **90 days**; (b) data Provider must retain by law; (c) aggregated anonymized data. Upon request before shutdown, Provider will supply a standard export of Signal definition cards and then-current exception lists Client can access in the agreed delivery channel.

5.5 **Confidentiality.** Each party ("Receiving Party") will protect the other party's non-public information ("Confidential Information") with at least reasonable care and use it only to perform under this MSA. Exclusions: information that is public without breach, already known, independently developed, or rightfully received from a third party.

5.6 **Compelled disclosure.** Receiving Party may disclose Confidential Information when required by law, with notice to the other party when legally permitted.

**NDA:** `[If separate mutual NDA signed, reference date: ______ and note which document controls confidentiality if both apply.]`

---

## 6. Intellectual property

6.1 **Provider IP.** Provider retains all rights in Meshflow, including platform software, connectors, entity-resolution and reconciliation logic, Mesh and Signal catalog templates, definition packs, documentation frameworks, and know-how developed before or outside Client-specific configuration ("**Provider IP**").

6.2 **License to Client.** During an active subscription and subject to payment, Provider grants Client a **non-exclusive, non-transferable** license to access Meshflow for Client's internal business purposes — including viewing and acting on Signals delivered via the channel stated in the SOW. Unless a SOW or change order states otherwise, Client may designate up to **five (5)** named users. Provider provisions access only for users Client names in writing and only within that cap.

6.2.1 **Additional seats.** Requests for more than five named users require a written change order and may incur additional fees at Provider's then-current rates.

6.3 **Client-specific configuration.** Connector settings, field mappings, hold/snooze reasons, and threshold values configured for Client under a SOW are licensed to Client for internal use while subscribed. Underlying Mesh/Signal templates, catalogs, and platform remain Provider IP.

6.4 **Feedback.** Client may provide suggestions; Provider may use feedback without obligation or attribution.

6.5 **No source-system license.** This MSA does not grant Client any rights in third-party systems (ERP, FSM, accounting, POS, etc.). Client remains solely responsible for its licenses with those vendors.

---

## 7. Subprocessors

7.1 Client authorizes Provider to use subprocessors to host and deliver the services, including cloud infrastructure and delivery channels.

7.2 **Current subprocessors** (update before signing):

| Subprocessor | Purpose | Location |
|---|---|---|
| Amazon Web Services (S3) | Data storage (raw and curated) | US |
| Amazon Web Services (Glue / related ETL) | Catalog, parsing, orchestration as applicable | US |
| Amazon Athena | SQL query over curated data (if used) | US |
| `[e.g. Amazon QuickSight / Meshflow app / email provider]` | Signal / briefing delivery channel | US |
| `[e.g. Amazon Web Services — Lambda, EventBridge, Step Functions]` | Ingestion and refresh orchestration | US |

7.3 Provider remains responsible for subprocessors' performance of data processing obligations. Provider will notify Client of material subprocessor changes via `[email / updated list on request]`.

---

## 8. Warranties & disclaimers

8.1 **Provider warranty.** Provider will perform services in a **professional and workmanlike manner** consistent with industry standards for similar operational analytics implementations.

8.2 **Client warranty.** Client has the right to provide access to Client Data and systems and that doing so does not violate third-party agreements.

8.3 **DISCLAIMER.** EXCEPT AS STATED IN 8.1, MESHFLOW AND SERVICES ARE PROVIDED **"AS IS."** PROVIDER DISCLAIMS ALL OTHER WARRANTIES, EXPRESS OR IMPLIED, INCLUDING MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, AND NON-INFRINGEMENT.

8.4 **No professional advice.** Meshflow is an **operational insight tool**, not investment, legal, tax, accounting, or audit advice. Client is solely responsible for business decisions based on Meshflow output, including whether to bill, collect, or change operations.

8.5 **Data accuracy.** Signals reflect Client source systems, mappings, catalog definitions, and confidence rules. Provider does not warrant that output is complete, free of false positives/negatives, or suitable for audited financial statements or regulatory compliance without Client's independent verification. Native sync between Client systems (if any) is not replaced by Meshflow.

---

## 9. Limitation of liability

9.1 **Exclusion of indirect damages.** NEITHER PARTY IS LIABLE FOR INDIRECT, INCIDENTAL, SPECIAL, CONSEQUENTIAL, OR PUNITIVE DAMAGES, OR LOST PROFITS, REVENUE, OR DATA, EVEN IF ADVISED OF THE POSSIBILITY.

9.2 **Cap.** PROVIDER'S TOTAL LIABILITY ARISING FROM THIS MSA AND ALL SOWS SHALL NOT EXCEED THE **FEES PAID BY CLIENT TO PROVIDER IN THE TWELVE (12) MONTHS** PRECEDING THE EVENT GIVING RISE TO THE CLAIM.

9.3 **Exceptions.** Sections 9.1–9.2 do not limit liability for: (a) Client's payment obligations; (b) either party's breach of confidentiality or misuse of Client Data caused by gross negligence or willful misconduct; (c) liability that cannot be limited by applicable law.

---

## 10. Indemnification

10.1 **Client indemnity.** Client will defend and indemnify Provider against third-party claims arising from: (a) Client Data or Client's source systems; (b) Client's use of Meshflow in violation of this MSA; (c) Client's violation of applicable law.

10.2 **Provider indemnity.** Provider will defend and indemnify Client against third-party claims that Meshflow (excluding Client Data and Client-specific configuration) infringes a U.S. patent, copyright, or trademark, provided Client promptly notifies Provider and cooperates in defense. Provider's remedy for infringement claims may include modification, replacement, or termination with refund of prepaid unused subscription fees.

---

## 11. Insurance

Provider will maintain **commercial general liability** and **professional liability (E&O)** insurance appropriate to the services, or will obtain such coverage before enterprise clients require it. Certificates available on request.

`[Internal: obtain E&O before first paid customer if not already in place — see pre-launch checklist.]`

---

## 12. Support

12.1 **Meshflow support:** Email support during business hours with **1 business day** target response time for non-critical issues, unless a SOW states otherwise.

12.2 **Availability.** Provider targets Mesh refresh on the cadence stated in the SOW on a best-efforts basis. Scheduled maintenance will be communicated when practicable. Meshflow is not guaranteed uninterrupted or error-free. Real-time or sub-daily refresh is not included unless a SOW expressly states otherwise.

12.3 **Critical issues.** Client will report material platform outages or refresh failures promptly to `[support email]`.

---

## 13. General

13.1 **Independent contractors.** The parties are independent contractors. This MSA does not create a partnership, joint venture, or employment relationship.

13.2 **Assignment.** Neither party may assign this MSA without the other's written consent, except Provider may assign to an affiliate or in connection with a merger or sale of substantially all assets, with notice to Client.

13.3 **Force majeure.** Neither party is liable for delay or failure due to events beyond reasonable control (natural disasters, widespread outages, government action, etc.), except payment obligations.

13.4 **Notices.** Notices must be in writing to the contacts above (email sufficient unless law requires otherwise).

13.5 **Governing law.** State of **North Carolina**, excluding conflict-of-law rules.

13.6 **Disputes.** Parties will attempt good-faith resolution for **30 days** before pursuing litigation. **Venue:** state or federal courts in **`[County, North Carolina]`**.

13.7 **Entire agreement.** This MSA, together with executed Meshflow SOWs and any referenced NDA, is the entire agreement for Meshflow and supersedes prior discussions on the same subject.

13.8 **Amendments.** Must be in writing signed by both parties.

13.9 **Severability.** If any provision is unenforceable, the remainder stays in effect.

13.10 **Counterparts & e-sign.** Signatures may be exchanged electronically and in counterparts; each is an original.

---

## Signatures

**Provider — `[LLC Legal Name]`**

Signature: ___________________________  
Name: Jeremiah Stephens  
Title: `[Manager / Member]`  
Date: _______________

**Client — `[Client Legal Name]`**

Signature: ___________________________  
Name: `[Client Contact Name]`  
Title: `[Title]`  
Date: _______________

---

## Exhibit A — Initial Statement of Work

The parties' first Meshflow engagement under this MSA is defined in:

**SOW number:** `[SOW-MESHFLOW-2026-001]`  
**Effective date:** `[Same as or after MSA date]`  
**Document:** Attached `[sow-template-meshflow.md / PDF export]`

Additional Meshflow SOWs (add Mesh systems, add catalog Signals, change delivery channel, etc.) may be added by mutual written agreement without amending this MSA.

---

## Internal checklist (remove before sending)

- [ ] All `[brackets]` replaced  
- [ ] Subprocessor table matches actual Meshflow stack and delivery channel  
- [ ] Support email live  
- [ ] County for venue filled in  
- [ ] NDA cross-reference if separate NDA exists from trial/discovery  
- [ ] Exhibit A references correct Meshflow SOW number and date  
- [ ] Sign MSA and Meshflow SOW same day (or MSA first)  
- [ ] W-9 ready if Client requested  
- [ ] E&O insurance status confirmed  
- [ ] Attorney review scheduled before first real customer  
- [ ] Confirm this is a **Meshflow** deal — pricing per meshflow-pricing-sheet ($4,000 / $600 flat Mesh)  

---

## Related documents

| Document | When to use |
|---|---|
| [sow-template-meshflow.md](./sow-template-meshflow.md) | Sign with this MSA at Meshflow paid conversion |
| [meshflow-pricing-sheet.md](./meshflow-pricing-sheet.md) | Client-facing Mesh flat pricing ($4,000 / $600) |
| [mesh-node-catalog.md](./mesh-node-catalog.md) | Mesh nodes (`SYS-…`) for SOW Section 3 |
| [mesh-catalog.md](./mesh-catalog.md) | Sample Meshes |
| [signal-catalog.md](./signal-catalog.md) | Signal IDs (`SIG-…`) for SOW Section 4 (checklist) |
| [meshflow-trial-terms.md](./meshflow-trial-terms.md) | Free discovery + implementation + 2-week trial |
| [../contracts/trial-terms.md](../contracts/trial-terms.md) | **Legacy** Bedrock trial |
| [../contracts/msa-template.md](../contracts/msa-template.md) | **Legacy** Bedrock / general MAP MSA |
| [../contracts/sow-template-bedrock.md](../contracts/sow-template-bedrock.md) | **Legacy** Bedrock dashboard SOW |
| [../contracts/map-pricing-sheet.md](../contracts/map-pricing-sheet.md) | **Legacy** Bedrock pricing |
| [../cold-call/pre-launch-checklist.md](../cold-call/pre-launch-checklist.md) | Phase C commercial gate |

---

## Revision log

| Date | Change |
|---|---|
| 2026-07-21 | Initial Meshflow MSA — Mesh + Signal model; catalog templates; read-only; pairs with sow-template-meshflow |
| 2026-07-21 | Fees default to flat Mesh (all applicable Signals); link meshflow-pricing-sheet |
