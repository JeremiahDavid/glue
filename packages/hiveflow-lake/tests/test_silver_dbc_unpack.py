from __future__ import annotations

from hiveflow.silver.unpack.dbc_documents import unpack_dbc_document_entity


def test_unpack_dbc_sales_orders_splits_headers_and_lines() -> None:
    rows = [
        {
            "id": "hdr-1",
            "number": "SO-100",
            "customerId": "cust-1",
            "salesOrderLines": [
                {"id": "line-1", "documentId": "hdr-1", "itemId": "item-1", "quantity": 2},
                {"id": "line-2", "documentId": "hdr-1", "itemId": "item-2", "quantity": 1},
            ],
        }
    ]

    headers, lines, line_entity = unpack_dbc_document_entity("sales_orders", rows)

    assert line_entity == "sales_order_lines"
    assert len(headers) == 1
    assert headers[0]["number"] == "SO-100"
    assert "salesOrderLines" not in headers[0]

    assert len(lines) == 2
    assert lines[0]["id"] == "line-1"
    assert lines[0]["header_id"] == "hdr-1"
    assert lines[0]["header_number"] == "SO-100"


def test_unpack_dbc_documents_parses_json_strings_from_parquet() -> None:
    rows = [
        {
            "id": "inv-1",
            "number": "SI-9",
            "salesInvoiceLines": '[{"id":"line-9","quantity":4}]',
        }
    ]

    headers, lines, line_entity = unpack_dbc_document_entity("sales_invoices", rows)

    assert line_entity == "sales_invoice_lines"
    assert "salesInvoiceLines" not in headers[0]
    assert len(lines) == 1
    assert lines[0]["id"] == "line-9"
    assert lines[0]["documentId"] == "inv-1"


def test_consolidate_unpacks_dbc_sales_invoices_into_lines(tmp_path) -> None:
    import json

    from hiveflow.ingest.storage import write_parquet_local
    from hiveflow.silver.consolidate import consolidate_source
    from hiveflow.silver.settings import ConsolidateSettings

    source = "dbc"
    run_dir = tmp_path / "raw" / source / "20260101T120000Z"
    run_dir.mkdir(parents=True)
    invoice_rows = [
        {
            "id": "inv-1",
            "number": "SI-1001",
            "customerId": "cust-1",
            "salesInvoiceLines": [{"id": "line-1", "documentId": "inv-1", "quantity": 1}],
        }
    ]
    manifest = {
        "entity_bundle": "v1_accounting",
        "entities": [{"entity": "sales_invoices", "row_count": 1}],
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    write_parquet_local(run_dir / "sales_invoices", "data.parquet", invoice_rows)

    settings = ConsolidateSettings(
        source=source,
        data_dir=tmp_path,
        raw_prefix=f"raw/{source}",
    )
    manifest = consolidate_source(settings)

    entities = {item["entity"]: item for item in manifest["entities"]}
    assert entities["sales_invoices"]["row_count"] == 1
    assert entities["sales_invoice_lines"]["row_count"] == 1
    assert (tmp_path / "silver_stg" / source / "sales_invoice_lines" / "data.parquet").is_file()
