from __future__ import annotations

from datetime import UTC, datetime

from hiveflow.qbd.models import EntityType
from hiveflow.qbd.qbxml.requests import build_entity_query


def test_incremental_customer_query_matches_qbwc_iteration_pattern() -> None:
    xml = build_entity_query(
        EntityType.CUSTOMER,
        qbxml_version="17.0",
        from_modified_date=datetime(2026, 7, 24, 14, 27, 11, tzinfo=UTC),
        max_returned=100,
        request_id="1",
    )
    assert 'iterator="Start"' in xml
    assert "<ModifiedDateRangeFilter>" not in xml
    assert "<ToModifiedDate>" not in xml
    assert "<MaxReturned>100</MaxReturned>" in xml
    assert "<FromModifiedDate>2026-07-24T14:27:11</FromModifiedDate>" in xml
    assert xml.index("<MaxReturned>") < xml.index("<FromModifiedDate>")


def test_incremental_invoice_query_includes_line_items_and_from_modified_date() -> None:
    xml = build_entity_query(
        EntityType.INVOICE,
        qbxml_version="17.0",
        from_modified_date=datetime(2026, 7, 24, 14, 27, 11, tzinfo=UTC),
        max_returned=100,
        request_id="2",
    )
    assert "<ModifiedDateRangeFilter>" in xml
    assert "<FromModifiedDate>2026-07-24T14:27:11</FromModifiedDate>" in xml
    assert xml.index("<ModifiedDateRangeFilter>") < xml.index("<IncludeLineItems>")
    assert "<IncludeLineItems>true</IncludeLineItems>" in xml
    assert "<TxnModifiedDateRangeFilter>" not in xml


def test_invoice_iterator_continue_uses_iterator_id_attribute() -> None:
    xml = build_entity_query(
        EntityType.INVOICE,
        qbxml_version="17.0",
        from_modified_date=datetime(2026, 7, 24, 14, 27, 11, tzinfo=UTC),
        iterator="Continue",
        iterator_id="{abc-123}",
        max_returned=100,
        request_id="3",
    )
    assert 'iterator="Continue"' in xml
    assert 'iteratorID="{abc-123}"' in xml
    assert "<iteratorID>" not in xml


def test_account_query_omits_iterator() -> None:
    xml = build_entity_query(
        EntityType.ACCOUNT,
        qbxml_version="17.0",
        max_returned=100,
        request_id="4",
    )
    assert 'iterator="Start"' not in xml
    assert 'iterator="Continue"' not in xml
    assert "iteratorID=" not in xml
    assert "<AccountQueryRq requestID=\"4\">" in xml
    assert "<MaxReturned>100</MaxReturned>" in xml


def test_class_query_omits_iterator() -> None:
    xml = build_entity_query(
        EntityType.CLASS,
        qbxml_version="17.0",
        max_returned=100,
        request_id="1",
    )
    assert 'iterator="Start"' not in xml
    assert "iteratorID=" not in xml


def test_full_accounting_bundle_excludes_departments() -> None:
    from hiveflow.qbd.entities import output_specs, sync_job_specs

    output_names = [spec.output_name for spec in output_specs("full_accounting")]
    job_names = [spec.output_name for spec in sync_job_specs("full_accounting")]
    assert "departments" not in output_names
    assert "departments" not in job_names
    assert output_names.index("classes") < output_names.index("invoices")
