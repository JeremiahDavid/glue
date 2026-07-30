from __future__ import annotations

from dataclasses import dataclass
from typing import Any

DEFAULT_ENTITY_BUNDLE = "full"


@dataclass(frozen=True)
class BCEntitySpec:
    output_name: str
    resource: str
    expand: str | None = None
    odata_filter: str | None = None
    incremental_field: str | None = "lastModifiedDateTime"
    derived_from: str | None = None


def _spec(
    output_name: str,
    resource: str,
    *,
    expand: str | None = None,
    odata_filter: str | None = None,
    incremental_field: str | None = "lastModifiedDateTime",
) -> BCEntitySpec:
    return BCEntitySpec(
        output_name=output_name,
        resource=resource,
        expand=expand,
        odata_filter=odata_filter,
        incremental_field=incremental_field,
    )


# Standard BC API v2.0 company-scoped entities (Microsoft APV2).
# Excludes automation-route admin entities and child-only media endpoints.
_FULL_ENTITY_SPECS: list[BCEntitySpec] = [
    # Master data
    _spec("customers", "customers"),
    _spec("vendors", "vendors"),
    _spec("items", "items"),
    _spec("item_variants", "itemVariants"),
    _spec("item_categories", "itemCategories"),
    _spec("contacts", "contacts"),
    _spec("contact_information", "contactsInformation"),
    _spec("employees", "employees"),
    _spec("salespeople_purchasers", "salespeoplePurchasers"),
    _spec("units_of_measure", "unitsOfMeasure"),
    _spec("locations", "locations"),
    _spec("payment_terms", "paymentTerms"),
    _spec("payment_methods", "paymentMethods"),
    _spec("shipment_methods", "shipmentMethods"),
    _spec("countries_regions", "countriesRegions"),
    _spec("currencies", "currencies"),
    _spec("currency_exchange_rates", "currencyExchangeRates"),
    _spec("tax_areas", "taxAreas"),
    _spec("tax_groups", "taxGroups"),
    _spec("customer_return_reasons", "customerReturnReasons"),
    _spec("dispute_status", "disputeStatus"),
    _spec("inventory_posting_groups", "inventoryPostingGroups"),
    _spec("general_product_posting_groups", "generalProductPostingGroups"),
    # Dimensions
    _spec("dimensions", "dimensions"),
    _spec("dimension_values", "dimensionValues"),
    _spec("default_dimensions", "defaultDimensions"),
    # Sales documents
    _spec("sales_quotes", "salesQuotes", expand="salesQuoteLines"),
    _spec("sales_orders", "salesOrders", expand="salesOrderLines"),
    _spec("sales_shipments", "salesShipments", expand="salesShipmentLines"),
    _spec("sales_invoices", "salesInvoices", expand="salesInvoiceLines"),
    _spec("sales_credit_memos", "salesCreditMemos", expand="salesCreditMemoLines"),
    _spec("customer_payments", "customerPayments"),
    _spec("customer_payment_journals", "customerPaymentJournals"),
    _spec("customer_contacts", "customerContacts"),
    _spec("customer_financial_details", "customerFinancialDetails"),
    _spec("opportunities", "opportunities"),
    # Purchasing
    _spec("purchase_orders", "purchaseOrders", expand="purchaseOrderLines"),
    _spec("purchase_receipts", "purchaseReceipts", expand="purchaseReceiptLines"),
    _spec("purchase_invoices", "purchaseInvoices", expand="purchaseInvoiceLines"),
    _spec("purchase_credit_memos", "purchaseCreditMemos", expand="purchaseCreditMemoLines"),
    _spec("vendor_payments", "vendorPayments"),
    _spec("vendor_payment_journals", "vendorPaymentJournals"),
    _spec("apply_vendor_entries", "applyVendorEntries"),
    # Finance / GL
    _spec("accounts", "accounts"),
    _spec("bank_accounts", "bankAccounts"),
    _spec("journals", "journals"),
    _spec("journal_lines", "journalLines"),
    _spec("general_ledger_entries", "generalLedgerEntries"),
    _spec("general_ledger_setup", "generalLedgerSetup", incremental_field=None),
    _spec("accounting_periods", "accountingPeriods"),
    # Inventory / operations
    _spec("item_ledger_entries", "itemLedgerEntries"),
    # Fixed assets / projects
    _spec("fixed_assets", "fixedAssets"),
    _spec("fixed_asset_locations", "fixedAssetLocations"),
    _spec("projects", "projects"),
    _spec("time_registration_entries", "timeRegistrationEntries"),
    # Financial reports (snapshot-style; full refresh each run)
    _spec("aged_accounts_receivables", "agedAccountsReceivables", incremental_field=None),
    _spec("aged_accounts_payables", "agedAccountsPayables", incremental_field=None),
    _spec("balance_sheets", "balanceSheets", incremental_field=None),
    _spec("income_statements", "incomeStatements", incremental_field=None),
    _spec("cash_flow_statements", "cashFlowStatements", incremental_field=None),
    _spec("trial_balances", "trialBalances", incremental_field=None),
    _spec("retained_earnings_statements", "retainedEarningsStatements", incremental_field=None),
    # Company / attachments
    _spec("company_information", "companyInformation", incremental_field=None),
    _spec("document_attachments", "documentAttachments"),
    # Workflow / approvals
    _spec("approval_entries", "approvalEntries"),
    _spec("approval_user_setups", "approvalUserSetups"),
    _spec("posted_approval_entries", "postedApprovalEntries"),
    _spec("workflows", "workflows"),
    _spec("workflow_steps", "workflowSteps"),
    _spec("workflow_approvers", "workflowApprovers"),
    _spec("workflow_response_options", "workflowResponseOptions"),
    # System
    _spec("job_queue_entries", "jobQueueEntries"),
    _spec("job_queue_log_entries", "jobQueueLogEntries"),
]

ENTITY_BUNDLE_SPECS: dict[str, list[BCEntitySpec]] = {
    "v1_intra": [
        BCEntitySpec("customers", "customers"),
        BCEntitySpec("items", "items"),
        BCEntitySpec("sales_orders", "salesOrders", expand="salesOrderLines"),
        BCEntitySpec("sales_shipments", "salesShipments"),
        BCEntitySpec("sales_invoices", "salesInvoices", expand="salesInvoiceLines"),
        BCEntitySpec("customer_payments", "customerPayments"),
    ],
    "v1_accounting": [
        BCEntitySpec("customers", "customers"),
        BCEntitySpec("sales_invoices", "salesInvoices", expand="salesInvoiceLines"),
        BCEntitySpec(
            "open_sales_invoices",
            "salesInvoices",
            expand="salesInvoiceLines",
            odata_filter="status eq 'Open'",
        ),
        BCEntitySpec("customer_payments", "customerPayments"),
    ],
    "full": list(_FULL_ENTITY_SPECS),
}


def list_entity_bundles() -> list[str]:
    return sorted(ENTITY_BUNDLE_SPECS)


def sync_entity_specs(bundle: str) -> list[BCEntitySpec]:
    """Entities fetched from BC API (excludes derived-only outputs)."""
    return [spec for spec in ENTITY_BUNDLE_SPECS[bundle] if spec.derived_from is None]


def output_specs(bundle: str) -> list[BCEntitySpec]:
    return list(ENTITY_BUNDLE_SPECS[bundle])


def resolve_bc_entities_from_ingest_config(
    ingest_cfg: dict[str, Any],
) -> tuple[str, list[BCEntitySpec]]:
    explicit = ingest_cfg.get("entities")
    if isinstance(explicit, dict) and explicit:
        specs = [
            BCEntitySpec(output_name=str(name), resource=str(resource))
            for name, resource in explicit.items()
        ]
        if not specs:
            raise ValueError("dbc.entities must contain at least one entity mapping")
        return "custom", specs

    bundle = str(ingest_cfg.get("entity_bundle", DEFAULT_ENTITY_BUNDLE)).strip().lower()
    if bundle not in ENTITY_BUNDLE_SPECS:
        available = ", ".join(list_entity_bundles())
        raise ValueError(f"Unknown dbc.entity_bundle {bundle!r}. Available bundles: {available}")
    return bundle, output_specs(bundle)
