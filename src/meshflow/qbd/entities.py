from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from meshflow.qbd.models import EntityType
from meshflow.qbo.entities import DEFAULT_ENTITY_BUNDLE, list_entity_bundles

MAX_RETURNED = 100


@dataclass(frozen=True)
class EntitySpec:
    entity_type: EntityType
    output_name: str
    derived_from: str | None = None


ENTITY_BUNDLE_SPECS: dict[str, list[EntitySpec]] = {
    "v1_accounting": [
        EntitySpec(EntityType.CUSTOMER, "customers"),
        EntitySpec(EntityType.INVOICE, "invoices"),
        EntitySpec(EntityType.INVOICE, "open_invoices", derived_from="invoices"),
        EntitySpec(EntityType.RECEIVE_PAYMENT, "payments"),
    ],
    "full_accounting": [
        EntitySpec(EntityType.CUSTOMER, "customers"),
        EntitySpec(EntityType.VENDOR, "vendors"),
        EntitySpec(EntityType.ITEM, "items"),
        EntitySpec(EntityType.ACCOUNT, "accounts"),
        EntitySpec(EntityType.CLASS, "classes"),
        EntitySpec(EntityType.INVOICE, "invoices"),
        EntitySpec(EntityType.RECEIVE_PAYMENT, "payments"),
        EntitySpec(EntityType.BILL, "bills"),
        EntitySpec(EntityType.CREDIT_MEMO, "credit_memos"),
        EntitySpec(EntityType.DEPOSIT, "deposits"),
        EntitySpec(EntityType.SALES_RECEIPT, "sales_receipts"),
        EntitySpec(EntityType.ESTIMATE, "estimates"),
    ],
}

DEFAULT_ENTITIES = ENTITY_BUNDLE_SPECS[DEFAULT_ENTITY_BUNDLE]


def list_qbd_entity_bundles() -> list[str]:
    return sorted(ENTITY_BUNDLE_SPECS)


def sync_job_specs(bundle: str) -> list[EntitySpec]:
    """QBXML query jobs only — derived outputs are excluded."""
    return [spec for spec in ENTITY_BUNDLE_SPECS[bundle] if spec.derived_from is None]


def output_specs(bundle: str) -> list[EntitySpec]:
    return list(ENTITY_BUNDLE_SPECS[bundle])


def resolve_qbd_entities_from_ingest_config(
    ingest_cfg: dict[str, Any],
) -> tuple[str, list[EntitySpec]]:
    bundle = str(ingest_cfg.get("entity_bundle", DEFAULT_ENTITY_BUNDLE)).strip().lower()
    if bundle not in ENTITY_BUNDLE_SPECS:
        available = ", ".join(list_entity_bundles())
        raise ValueError(f"Unknown ingest.entity_bundle {bundle!r}. Available bundles: {available}")
    return bundle, output_specs(bundle)
