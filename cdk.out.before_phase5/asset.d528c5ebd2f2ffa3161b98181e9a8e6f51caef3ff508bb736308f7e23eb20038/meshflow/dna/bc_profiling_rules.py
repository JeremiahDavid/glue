"""Parse Microsoft Learn APV2 entity docs into connector profiling rules."""

from __future__ import annotations

import html
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from meshflow.dna.semantic_knowledge_base import connector_knowledge_root

_MS_LEARN_BASE = (
    "https://learn.microsoft.com/en-us/dynamics365/business-central/dev-itpro/api-reference/v2.0"
)
_TOC_URL = f"{_MS_LEARN_BASE}/toc.json"

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

# Parent document navigation on line entities -> FK column on the line.
_PARENT_NAV_COLUMN: dict[str, str] = {
    "salesquote": "documentId",
    "salesorder": "documentId",
    "salesshipment": "documentId",
    "salesinvoice": "documentId",
    "salescreditmemo": "documentId",
    "purchaseorder": "documentId",
    "purchasereceipt": "documentId",
    "purchaseinvoice": "documentId",
    "purchasecreditmemo": "documentId",
    "journal": "journalId",
}

# Navigation property (lower) -> FK column when not *Id shaped.
_NAV_PROPERTY_COLUMN: dict[str, str] = {
    "customer": "customerId",
    "vendor": "vendorId",
    "item": "itemId",
    "account": "accountId",
    "currency": "currencyId",
    "paymentterm": "paymentTermsId",
    "paymentmethod": "paymentMethodId",
    "shipmentmethod": "shipmentMethodId",
    "unitofmeasure": "unitOfMeasureId",
    "itemvariant": "itemVariantId",
    "location": "locationId",
    "dimension": "dimensionId",
    "dimensionvalue": "dimensionValueId",
    "salesorder": "orderId",
    "purchaseorder": "orderId",
    "salesinvoice": "appliesToInvoiceId",
    "purchaseinvoice": "appliesToInvoiceId",
    "project": "jobId",
    "workflow": "workflowId",
}

_DIMENSION_ENTITIES = frozenset(
    {
        "customers",
        "vendors",
        "items",
        "contacts",
        "employees",
        "accounts",
        "locations",
        "dimensions",
        "dimension_values",
        "currencies",
        "units_of_measure",
    }
)
_FACT_LINE_SUFFIX = "_lines"
_REPORT_ENTITIES = frozenset(
    {
        "aged_accounts_receivables",
        "aged_accounts_payables",
        "balance_sheets",
        "income_statements",
        "cash_flow_statements",
        "trial_balances",
        "retained_earnings_statements",
    }
)
_LEDGER_ENTITIES = frozenset({"general_ledger_entries", "item_ledger_entries", "journal_lines"})

_TABLE_ROW_RE = re.compile(r"^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|")
_NAV_LINK_RE = re.compile(r"\[([^\]]+)\]\(dynamics_([^)]+)\)")
_HTML_H2_RE = re.compile(r"<h2[^>]*id=\"([^\"]+)\"[^>]*>([^<]+)</h2>", re.IGNORECASE)
_HTML_TR_RE = re.compile(r"<tr>(.*?)</tr>", re.IGNORECASE | re.DOTALL)
_HTML_TD_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.IGNORECASE | re.DOTALL)
_HTML_LINK_RE = re.compile(
    r"<a[^>]+href=\"(?:\./)?(?:resources/)?(dynamics_[^\"]+)\"[^>]*>([^<]+)</a>",
    re.IGNORECASE,
)
_MEASURE_PROP_RE = re.compile(
    r"(amount|quantity|price|cost|rate|total|balance|count|percent|qty|profit|debit|credit)",
    re.IGNORECASE,
)
_DATE_PROP_RE = re.compile(r"(date|time|timestamp|at$)", re.IGNORECASE)


def profiling_rules_path(source: str = "dbc") -> Path:
    return connector_knowledge_root() / source.strip().lower() / "profiling_rules.yaml"


def slug_to_silver_entity(slug: str) -> str | None:
    key = slug.strip().lower().removeprefix("dynamics_")
    return _SLUG_TO_SILVER.get(key)


def infer_entity_role(silver_entity: str) -> str:
    name = silver_entity.strip().lower()
    if name in _REPORT_ENTITIES:
        return "reference"
    if name in _LEDGER_ENTITIES or name.endswith(_FACT_LINE_SUFFIX):
        return "fact"
    if name in _DIMENSION_ENTITIES:
        return "dimension"
    if any(token in name for token in ("_orders", "_invoices", "_shipments", "_receipts", "_quotes", "_credit_memos")):
        return "reference"
    if name.endswith("_payments") or name.endswith("_journals"):
        return "fact"
    return "reference"


def infer_entity_grain(silver_entity: str) -> str:
    name = silver_entity.strip().lower()
    if name.endswith(_FACT_LINE_SUFFIX):
        return "line"
    if name in {"customers", "vendors", "items", "contacts", "employees", "accounts"}:
        return name.rstrip("s")
    if any(
        token in name
        for token in ("_orders", "_invoices", "_shipments", "_receipts", "_quotes", "_credit_memos", "_payments")
    ):
        return "document"
    if name in _LEDGER_ENTITIES:
        return "entry"
    if name in _REPORT_ENTITIES:
        return "snapshot"
    return "record"


def _column_concept(column: str, role: str) -> list[str]:
    lowered = column.strip()
    snake = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", lowered).lower()
    if role == "foreign_key":
        return [snake.replace("_id", "_id") if snake.endswith("_id") else f"{snake}_id"]
    if role == "date":
        return [snake]
    if role == "measure":
        return [snake]
    if role == "status":
        return [snake]
    if lowered == "number":
        return ["document_number"]
    if lowered == "displayName":
        return ["display_name"]
    if lowered == "id":
        return ["document_id"]
    return [snake]


def _infer_property_role(name: str, prop_type: str, description: str) -> str | None:
    lowered = name.strip()
    type_lower = prop_type.strip().lower()
    desc_lower = description.strip().lower()
    if lowered == "id" and "guid" in type_lower:
        return "identifier"
    if lowered.endswith("Id") and "guid" in type_lower:
        return "foreign_key"
    if lowered.endswith("Number") or lowered == "number":
        return "identifier"
    if _DATE_PROP_RE.search(lowered) or type_lower == "date" or type_lower == "datetime":
        return "date"
    if type_lower == "decimal" and _MEASURE_PROP_RE.search(lowered):
        return "measure"
    if lowered in {"status", "blocked", "lineType", "documentType", "entryType"}:
        return "status"
    if "name" in lowered.lower() and type_lower == "string":
        return "dimension"
    if "balance" in desc_lower or "amount" in desc_lower:
        return "measure"
    return None


def _nav_to_column(nav_name: str, parent_slug: str) -> str | None:
    nav_key = nav_name.strip().lower()
    if nav_key in _PARENT_NAV_COLUMN and parent_slug.endswith("line"):
        return _PARENT_NAV_COLUMN[nav_key]
    return _NAV_PROPERTY_COLUMN.get(nav_key) or (
        f"{nav_name[0].lower()}{nav_name[1:]}Id" if nav_name and nav_name[0].isupper() else None
    )


def _strip_html(text: str) -> str:
    cleaned = re.sub(r"<[^>]+>", "", text)
    return html.unescape(cleaned).strip()


def _parse_html_tables(page: str) -> tuple[dict[str, dict[str, str]], list[dict[str, str]], str]:
    """Parse Properties and Navigation tables from a Microsoft Learn HTML page."""
    properties: dict[str, dict[str, str]] = {}
    navigation: list[dict[str, str]] = []
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

    for section_name in ("properties", "navigation"):
        chunk = sections.get(section_name, "")
        if not chunk:
            continue
        for row_match in _HTML_TR_RE.finditer(chunk):
            cells = [_strip_html(cell) for cell in _HTML_TD_RE.findall(row_match.group(1))]
            if len(cells) < 3:
                continue
            header = cells[0].lower()
            if header in {"property", "navigation"}:
                continue
            if section_name == "properties":
                properties[cells[0]] = {"type": cells[1], "description": cells[2]}
            else:
                link_match = _HTML_LINK_RE.search(row_match.group(1))
                if not link_match:
                    continue
                target_slug = link_match.group(1).removeprefix("dynamics_")
                nav_name = _strip_html(link_match.group(2))
                navigation.append(
                    {
                        "name": nav_name,
                        "target_slug": target_slug,
                        "target_entity": slug_to_silver_entity(f"dynamics_{target_slug}") or "",
                    }
                )
    return properties, navigation, description


def parse_ms_learn_entity_page(text: str, *, slug: str) -> dict[str, Any]:
    """Extract properties, navigation, and inferred keys from a Learn page."""
    silver_entity = slug_to_silver_entity(slug)
    if not silver_entity:
        return {}

    description = ""
    properties: dict[str, dict[str, str]] = {}
    navigation: list[dict[str, str]] = []

    if "<table" in text.lower():
        properties, navigation, description = _parse_html_tables(text)
    else:
        title_match = re.search(r"^#\s+(.+?)\s+resource type", text, re.MULTILINE)
        if title_match:
            description = title_match.group(1).replace(" resource type", "").strip()
        intro_match = re.search(r"^Represents (.+?) in Business Central\.", text, re.MULTILINE)
        if intro_match:
            description = intro_match.group(1).strip()

        section = ""
        for line in text.splitlines():
            if line.startswith("## Properties"):
                section = "properties"
                continue
            if line.startswith("## Navigation"):
                section = "navigation"
                continue
            if line.startswith("## "):
                section = ""
                continue
            if section == "properties":
                match = _TABLE_ROW_RE.match(line)
                if not match or match.group(1).strip().lower() == "property":
                    continue
                prop_name = match.group(1).strip()
                prop_type = match.group(2).strip()
                prop_desc = match.group(3).strip()
                properties[prop_name] = {"type": prop_type, "description": prop_desc}
            elif section == "navigation":
                match = _TABLE_ROW_RE.match(line)
                if not match or match.group(1).strip().lower() == "navigation":
                    continue
                nav_cell = match.group(1).strip()
                link = _NAV_LINK_RE.search(nav_cell)
                if not link:
                    continue
                nav_name, target_slug = link.group(1), link.group(2)
                navigation.append(
                    {
                        "name": nav_name,
                        "target_slug": target_slug,
                        "target_entity": slug_to_silver_entity(target_slug) or "",
                    }
                )

    primary_key = "id" if "id" in properties else ""
    foreign_keys: list[dict[str, str]] = []
    relationships: list[dict[str, Any]] = []
    column_hints: dict[str, dict[str, Any]] = {}

    parent_slug = slug.removeprefix("dynamics_").lower()
    for nav in navigation:
        target_entity = str(nav.get("target_entity") or "").strip()
        if not target_entity:
            continue
        column = _nav_to_column(str(nav.get("name") or ""), parent_slug)
        if not column or column not in properties:
            continue
        foreign_keys.append(
            {
                "column": column,
                "to_entity": target_entity,
                "to_column": "id",
                "citation": f"microsoft_learn:{slug}#navigation",
            }
        )
        relationships.append(
            {
                "from_entity": silver_entity,
                "from_column": column,
                "to_entity": target_entity,
                "to_column": "id",
                "cardinality": "many_to_one",
                "citation": f"microsoft_learn:{slug}#navigation",
            }
        )

    for prop_name, meta in properties.items():
        role = _infer_property_role(prop_name, meta.get("type", ""), meta.get("description", ""))
        if not role:
            continue
        concepts = _column_concept(prop_name, role)
        hint: dict[str, Any] = {
            "role": role,
            "concepts": concepts,
            "citation": f"microsoft_learn:{slug}#properties",
        }
        if role == "foreign_key":
            for fk in foreign_keys:
                if fk["column"] == prop_name:
                    hint["fk_target_entity"] = fk["to_entity"]
                    hint["fk_target_column"] = fk["to_column"]
                    break
        column_hints[prop_name] = hint

    return {
        "silver_entity": silver_entity,
        "bc_resource_slug": slug.removeprefix("dynamics_"),
        "role": infer_entity_role(silver_entity),
        "grain": infer_entity_grain(silver_entity),
        "primary_key": primary_key,
        "description": description,
        "ms_learn_url": f"{_MS_LEARN_BASE}/resources/{slug}",
        "foreign_keys": foreign_keys,
        "relationships": relationships,
        "column_hints": column_hints,
    }


def build_profiling_rules_from_pages(pages: dict[str, str]) -> dict[str, Any]:
    """Merge parsed entity pages into a single profiling rules document."""
    entities_by_name: dict[str, dict[str, Any]] = {}
    relationships: list[dict[str, Any]] = []
    column_hints: dict[str, dict[str, Any]] = {}

    for slug, text in sorted(pages.items()):
        parsed = parse_ms_learn_entity_page(text, slug=slug if slug.startswith("dynamics_") else f"dynamics_{slug}")
        silver = str(parsed.get("silver_entity") or "").strip()
        if not silver:
            continue
        entities_by_name[silver] = {
            key: parsed[key]
            for key in (
                "silver_entity",
                "bc_resource_slug",
                "role",
                "grain",
                "primary_key",
                "description",
                "ms_learn_url",
                "foreign_keys",
            )
            if key in parsed
        }
        relationships.extend(parsed.get("relationships") or [])
        for column, hint in (parsed.get("column_hints") or {}).items():
            if column not in column_hints:
                column_hints[column] = hint

    # Deduplicate relationships.
    rel_keys: set[tuple[str, str, str, str]] = set()
    unique_relationships: list[dict[str, Any]] = []
    for rel in relationships:
        if not isinstance(rel, dict):
            continue
        key = (
            str(rel.get("from_entity") or ""),
            str(rel.get("from_column") or ""),
            str(rel.get("to_entity") or ""),
            str(rel.get("to_column") or ""),
        )
        if key in rel_keys:
            continue
        rel_keys.add(key)
        unique_relationships.append(rel)

    return {
        "source": "dbc",
        "description": (
            "Baseline profiling rules scraped from Microsoft Learn APV2 entity documentation. "
            "Used to seed PK/FK proposals and column roles before silver profiling runs."
        ),
        "generated_at": datetime.now(UTC).isoformat(),
        "ms_learn_toc": _TOC_URL,
        "entity_count": len(entities_by_name),
        "entities": [entities_by_name[name] for name in sorted(entities_by_name)],
        "relationships": unique_relationships,
        "column_hints": column_hints,
    }


def load_profiling_rules(source: str = "dbc") -> dict[str, Any]:
    path = profiling_rules_path(source)
    if not path.is_file():
        return {}
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def merge_profiling_rules_into_hints(
    connector_hints: dict[str, Any],
    profiling_rules: dict[str, Any],
) -> dict[str, Any]:
    """Overlay scraped Microsoft rules beneath tenant overrides (handled upstream)."""
    if not profiling_rules:
        return dict(connector_hints)

    merged = dict(connector_hints)
    if not merged.get("description"):
        merged["description"] = str(profiling_rules.get("description") or "").strip()

    entity_index = {
        str(item.get("silver_entity") or "").strip().lower(): dict(item)
        for item in connector_hints.get("entities") or []
        if isinstance(item, dict) and str(item.get("silver_entity") or "").strip()
    }
    for item in profiling_rules.get("entities") or []:
        if not isinstance(item, dict):
            continue
        silver = str(item.get("silver_entity") or "").strip().lower()
        if not silver:
            continue
        base = entity_index.get(silver, {})
        entity_index[silver] = {**item, **base, "silver_entity": silver}
    merged["entities"] = [entity_index[key] for key in sorted(entity_index)]

    rel_index = {
        str(item.get("id") or "").strip().lower(): dict(item)
        for item in connector_hints.get("relationships") or []
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    }
    for item in profiling_rules.get("relationships") or []:
        if not isinstance(item, dict):
            continue
        rel_id = str(item.get("id") or "").strip().lower()
        if not rel_id:
            rel_id = (
                f"rel_{item.get('from_entity')}_{item.get('from_column')}_"
                f"{item.get('to_entity')}_{item.get('to_column')}"
            ).lower()
        rel_index.setdefault(rel_id, {**item, "id": rel_id, "status": item.get("status", "proposed")})
    merged["relationships"] = [rel_index[key] for key in sorted(rel_index)]

    column_hints: dict[str, Any] = {}
    for source in (profiling_rules, connector_hints):
        hints = source.get("column_hints")
        if isinstance(hints, dict):
            column_hints.update(hints)
    merged["column_hints"] = column_hints
    merged["profiling_rules"] = {
        "generated_at": profiling_rules.get("generated_at"),
        "entity_count": profiling_rules.get("entity_count"),
        "ms_learn_toc": profiling_rules.get("ms_learn_toc"),
    }
    return merged


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
