"""Scrape Microsoft Learn APV2 Properties tables into global source documentation.

Owned by meshflow-connectors (BC). Output lands in
s3://hiveflowai-source-documentation/{source}/entity_properties.yaml.
"""

from __future__ import annotations

import html
import json
import os
import re
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from typing import Any

import yaml

_MS_LEARN_BASE = (
    "https://learn.microsoft.com/en-us/dynamics365/business-central/dev-itpro/api-reference/v2.0"
)
_TOC_URL = f"{_MS_LEARN_BASE}/toc.json"
_USER_AGENT = "MeshflowBCSourceDocs/1.0 (+https://github.com/meshflow)"

DEFAULT_SOURCE_DOCS_BUCKET = "hiveflowai-source-documentation"
DEFAULT_SOURCE = "dbc"

# dynamics_* slug (without prefix) -> Meshflow silver table name.
_SLUG_TO_SILVER: dict[str, str] = {
    "customer": "customers",
    "vendor": "vendors",
    "item": "items",
    "contact": "contacts",
    "employee": "employees",
    "account": "accounts",
    "currency": "currencies",
    "location": "locations",
    "dimension": "dimensions",
    "journal": "journals",
    "project": "projects",
    "company": "company_information",
    "companyinformation": "company_information",
    "salesquote": "sales_quotes",
    "salesquoteline": "sales_quote_lines",
    "salesorder": "sales_orders",
    "salesorderline": "sales_order_lines",
    "salesshipment": "sales_shipments",
    "salesshipmentline": "sales_shipment_lines",
    "salesinvoice": "sales_invoices",
    "salesinvoiceline": "sales_invoice_lines",
    "salescreditmemo": "sales_credit_memos",
    "salescreditmemoline": "sales_credit_memo_lines",
    "purchaseorder": "purchase_orders",
    "purchaseorderline": "purchase_order_lines",
    "purchasereceipt": "purchase_receipts",
    "purchasereceiptline": "purchase_receipt_lines",
    "purchaseinvoice": "purchase_invoices",
    "purchaseinvoiceline": "purchase_invoice_lines",
    "purchasecreditmemo": "purchase_credit_memos",
    "purchasecreditmemoline": "purchase_credit_memo_lines",
    "customerpayment": "customer_payments",
    "customerpaymentjournal": "customer_payment_journals",
    "vendorpayment": "vendor_payments",
    "vendorpaymentjournal": "vendor_payment_journals",
    "customercontact": "customer_contacts",
    "customerfinancialdetail": "customer_financial_details",
    "generalledgerentry": "general_ledger_entries",
    "generalledgersetup": "general_ledger_setup",
    "itemledgerentry": "item_ledger_entries",
    "journalline": "journal_lines",
    "itemvariant": "item_variants",
    "itemcategory": "item_categories",
    "dimensionvalue": "dimension_values",
    "defaultdimension": "default_dimensions",
    "unitofmeasure": "units_of_measure",
    "paymentterm": "payment_terms",
    "paymentmethod": "payment_methods",
    "shipmentmethod": "shipment_methods",
    "countryregion": "countries_regions",
    "currencyexchangerate": "currency_exchange_rates",
    "taxarea": "tax_areas",
    "taxgroup": "tax_groups",
    "customerreturnreason": "customer_return_reasons",
    "disputestatus": "dispute_status",
    "inventorypostinggroup": "inventory_posting_groups",
    "generalproductpostinggroup": "general_product_posting_groups",
    "salespersonpurchaser": "salespeople_purchasers",
    "contactinformation": "contact_information",
    "opportunity": "opportunities",
    "applyvendorentry": "apply_vendor_entries",
    "bankaccount": "bank_accounts",
    "accountingperiod": "accounting_periods",
    "fixedasset": "fixed_assets",
    "fixedassetlocation": "fixed_asset_locations",
    "timeregistrationentry": "time_registration_entries",
    "agedaccountsreceivable": "aged_accounts_receivables",
    "agedaccountspayable": "aged_accounts_payables",
    "balancesheet": "balance_sheets",
    "incomestatement": "income_statements",
    "cashflowstatement": "cash_flow_statements",
    "trialbalance": "trial_balances",
    "retainedearningsstatement": "retained_earnings_statements",
    "documentattachment": "document_attachments",
    "jobqueueentry": "job_queue_entries",
    "jobqueuelogentry": "job_queue_log_entries",
}

_TABLE_ROW_RE = re.compile(r"^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|")
_HTML_H2_RE = re.compile(r"<h2[^>]*id=\"([^\"]+)\"[^>]*>([^<]+)</h2>", re.IGNORECASE)
_HTML_TR_RE = re.compile(r"<tr>(.*?)</tr>", re.IGNORECASE | re.DOTALL)
_HTML_TD_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.IGNORECASE | re.DOTALL)


def source_docs_bucket_name() -> str:
    return os.getenv("MESHFLOW_SOURCE_DOCS_BUCKET", "").strip() or DEFAULT_SOURCE_DOCS_BUCKET


def source_docs_object_key(source: str = DEFAULT_SOURCE) -> str:
    connector = source.strip().lower() or DEFAULT_SOURCE
    override = os.getenv("MESHFLOW_SOURCE_DOCS_OBJECT_KEY", "").strip()
    if override:
        return override.lstrip("/")
    return f"{connector}/entity_properties.yaml"


def slug_to_silver_entity(slug: str) -> str | None:
    key = slug.strip().lower().removeprefix("dynamics_")
    return _SLUG_TO_SILVER.get(key)


def _strip_html(text: str) -> str:
    cleaned = re.sub(r"<[^>]+>", "", text)
    return html.unescape(cleaned).strip()


def _parse_html_properties(page: str) -> tuple[dict[str, dict[str, str]], str]:
    """Parse Properties table + entity description from a Microsoft Learn HTML page."""
    properties: dict[str, dict[str, str]] = {}
    description = ""

    intro_match = re.search(
        r"<meta name=\"description\" content=\"([^\"]+)\"",
        page,
        re.IGNORECASE,
    )
    if intro_match:
        description = _strip_html(intro_match.group(1))

    sections: dict[str, str] = {}
    headings = list(_HTML_H2_RE.finditer(page))
    for index, match in enumerate(headings):
        section_id = match.group(1).strip().lower()
        start = match.end()
        end = headings[index + 1].start() if index + 1 < len(headings) else len(page)
        sections[section_id] = page[start:end]

    chunk = sections.get("properties", "")
    for row_match in _HTML_TR_RE.finditer(chunk):
        cells = [_strip_html(cell) for cell in _HTML_TD_RE.findall(row_match.group(1))]
        if len(cells) < 3:
            continue
        if cells[0].lower() == "property":
            continue
        properties[cells[0]] = {"type": cells[1], "description": cells[2]}
    return properties, description


def _parse_markdown_properties(text: str) -> tuple[dict[str, dict[str, str]], str]:
    """Parse Properties table + entity description from markdown Learn pages."""
    properties: dict[str, dict[str, str]] = {}
    description = ""
    title_match = re.search(r"^#\s+(.+?)\s+resource type", text, re.MULTILINE)
    if title_match:
        description = title_match.group(1).replace(" resource type", "").strip()
    intro_match = re.search(r"^Represents (.+?) in Business Central\.", text, re.MULTILINE)
    if intro_match:
        description = intro_match.group(1).strip()
        if not description.lower().startswith("a ") and not description.lower().startswith("an "):
            description = f"A {description} in Business Central."

    section = ""
    for line in text.splitlines():
        if line.startswith("## Properties"):
            section = "properties"
            continue
        if line.startswith("## "):
            section = ""
            continue
        if section != "properties":
            continue
        match = _TABLE_ROW_RE.match(line)
        if not match or match.group(1).strip().lower() == "property":
            continue
        name = match.group(1).strip()
        if not name or set(name) <= {"-"}:
            continue
        properties[name] = {
            "type": match.group(2).strip(),
            "description": match.group(3).strip(),
        }
    return properties, description


def extract_toc_resource_slugs(toc_payload: dict[str, Any]) -> list[str]:
    """Return dynamics_* resource slugs from the APV2 toc.json."""
    slugs: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            href = str(node.get("href") or "")
            if href.startswith("resources/dynamics_"):
                slugs.append(href.split("/", 1)[1])
            for child in node.get("children") or []:
                walk(child)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(toc_payload.get("items") or [])
    return sorted(set(slugs))


def load_toc_slugs_from_json(text: str) -> list[str]:
    return extract_toc_resource_slugs(json.loads(text))


def _fetch(url: str, *, timeout: int = 60) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8")


def fetch_entity_page(slug: str, *, timeout: int = 60) -> str:
    return _fetch(f"{_MS_LEARN_BASE}/resources/{slug}", timeout=timeout)


def extract_entity_properties_doc(text: str, *, slug: str) -> dict[str, Any]:
    """Return entity + full Properties table (name, type, description) for one Learn page."""
    normalized_slug = slug if slug.startswith("dynamics_") else f"dynamics_{slug}"
    silver_entity = slug_to_silver_entity(normalized_slug)
    if not silver_entity:
        return {}

    if "<table" in text.lower():
        properties, description = _parse_html_properties(text)
    else:
        properties, description = _parse_markdown_properties(text)

    if not description:
        description = f"A {silver_entity.replace('_', ' ')} object in Dynamics 365 Business Central."

    property_rows = [
        {
            "name": name,
            "type": str(meta.get("type") or "").strip(),
            "description": str(meta.get("description") or "").strip(),
        }
        for name, meta in properties.items()
        if str(name).strip()
    ]
    property_rows.sort(key=lambda item: str(item.get("name") or "").lower())

    return {
        "silver_entity": silver_entity,
        "bc_resource_slug": normalized_slug.removeprefix("dynamics_"),
        "description": description,
        "ms_learn_url": f"{_MS_LEARN_BASE}/resources/{normalized_slug}",
        "property_count": len(property_rows),
        "properties": property_rows,
    }


def build_source_properties_catalog(
    pages: dict[str, str],
    *,
    source: str = DEFAULT_SOURCE,
    failures: list[str] | None = None,
) -> dict[str, Any]:
    """Build the global source documentation catalog from scraped Learn pages."""
    entities: list[dict[str, Any]] = []
    for slug, text in sorted(pages.items()):
        doc = extract_entity_properties_doc(text, slug=slug)
        if not doc.get("silver_entity"):
            continue
        entities.append(doc)

    entities.sort(key=lambda item: str(item.get("silver_entity") or ""))
    property_count = sum(int(item.get("property_count") or 0) for item in entities)
    return {
        "source": source.strip().lower() or DEFAULT_SOURCE,
        "kind": "ms_learn_entity_properties",
        "description": (
            "Microsoft Learn APV2 Properties tables (property, type, description) "
            "for Meshflow silver entities. Refreshed on a biweekly schedule."
        ),
        "generated_at": datetime.now(UTC).isoformat(),
        "ms_learn_toc": _TOC_URL,
        "entity_count": len(entities),
        "property_count": property_count,
        "scrape_failures": list(failures or []),
        "entities": entities,
    }


def scrape_ms_learn_entity_pages(
    *,
    delay_seconds: float = 0.35,
    limit: int = 0,
) -> tuple[dict[str, str], list[str], list[str]]:
    """Fetch mapped APV2 resource pages. Returns (pages, mapped_slugs, failures)."""
    toc_text = _fetch(_TOC_URL)
    slugs = load_toc_slugs_from_json(toc_text)
    mapped = [slug for slug in slugs if slug_to_silver_entity(slug)]
    if limit > 0:
        mapped = mapped[:limit]

    pages: dict[str, str] = {}
    failures: list[str] = []
    for index, slug in enumerate(mapped, start=1):
        try:
            pages[slug] = fetch_entity_page(slug)
        except urllib.error.HTTPError as exc:
            failures.append(f"{slug}: HTTP {exc.code}")
        except urllib.error.URLError as exc:
            failures.append(f"{slug}: {exc}")
        if index < len(mapped):
            time.sleep(max(0.0, delay_seconds))
    return pages, mapped, failures


def catalog_to_yaml(catalog: dict[str, Any]) -> str:
    return yaml.safe_dump(catalog, sort_keys=False, allow_unicode=True, width=120)


def write_source_properties_catalog(
    catalog: dict[str, Any],
    *,
    bucket: str | None = None,
    object_key: str | None = None,
) -> dict[str, Any]:
    """Write the properties catalog YAML to the global source-documentation bucket."""
    import boto3

    bucket_name = (bucket or source_docs_bucket_name()).strip()
    key = (object_key or source_docs_object_key(str(catalog.get("source") or DEFAULT_SOURCE))).lstrip("/")
    body = catalog_to_yaml(catalog).encode("utf-8")
    client = boto3.client("s3")
    client.put_object(
        Bucket=bucket_name,
        Key=key,
        Body=body,
        ContentType="application/yaml; charset=utf-8",
        Metadata={
            "source": str(catalog.get("source") or DEFAULT_SOURCE),
            "kind": "ms_learn_entity_properties",
            "entity_count": str(catalog.get("entity_count") or 0),
            "property_count": str(catalog.get("property_count") or 0),
        },
    )
    return {
        "bucket": bucket_name,
        "key": key,
        "uri": f"s3://{bucket_name}/{key}",
        "bytes": len(body),
    }


def run_source_docs_scrape_job(
    *,
    source: str = DEFAULT_SOURCE,
    delay_seconds: float = 0.35,
    limit: int = 0,
    bucket: str | None = None,
    object_key: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Scrape MS Learn Properties tables and publish under the source prefix."""
    pages, mapped, failures = scrape_ms_learn_entity_pages(delay_seconds=delay_seconds, limit=limit)
    catalog = build_source_properties_catalog(pages, source=source, failures=failures)
    result: dict[str, Any] = {
        "status": "scraped",
        "source": catalog["source"],
        "mapped_slug_count": len(mapped),
        "entity_count": catalog.get("entity_count"),
        "property_count": catalog.get("property_count"),
        "failure_count": len(failures),
        "failures": failures,
        "generated_at": catalog.get("generated_at"),
    }
    if dry_run:
        result["status"] = "dry_run"
        result["catalog_preview"] = {
            "entity_count": catalog.get("entity_count"),
            "property_count": catalog.get("property_count"),
            "sample_entities": [e.get("silver_entity") for e in (catalog.get("entities") or [])[:5]],
        }
        return result

    written = write_source_properties_catalog(catalog, bucket=bucket, object_key=object_key)
    result["status"] = "published"
    result["artifact"] = written
    print(json.dumps({"msg": "source_docs_scrape_published", **result}, default=str))
    return result
