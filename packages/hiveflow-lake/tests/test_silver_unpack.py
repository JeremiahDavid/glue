from __future__ import annotations

from meshflow.silver.unpack.qbd_invoices import unpack_qbd_invoices


def test_unpack_qbd_invoices_flattens_refs_and_explodes_lines() -> None:
    rows = [
        {
            "TxnID": "ABC-1",
            "TxnNumber": "402",
            "RefNumber": "1087",
            "Subtotal": "1000.00",
            "CustomerRef": {"ListID": "CUST-1", "FullName": "Acme Corp"},
            "InvoiceLineRet": [
                {
                    "TxnLineID": "LINE-1",
                    "Desc": "Labor",
                    "Amount": "600.00",
                    "ItemRef": {"ListID": "ITEM-1", "FullName": "Labor"},
                },
                {
                    "TxnLineID": "LINE-2",
                    "Desc": "Materials",
                    "Amount": "400.00",
                    "ItemRef": {"ListID": "ITEM-2", "FullName": "Materials"},
                },
            ],
        }
    ]

    headers, lines = unpack_qbd_invoices(rows)

    assert len(headers) == 1
    assert headers[0]["TxnID"] == "ABC-1"
    assert headers[0]["customer_list_id"] == "CUST-1"
    assert headers[0]["customer_full_name"] == "Acme Corp"
    assert "InvoiceLineRet" not in headers[0]

    assert len(lines) == 2
    assert lines[0]["TxnID"] == "ABC-1"
    assert lines[0]["TxnLineID"] == "LINE-1"
    assert lines[0]["item_list_id"] == "ITEM-1"
    assert lines[1]["item_full_name"] == "Materials"


def test_unpack_qbd_invoices_parses_json_strings_from_parquet() -> None:
    rows = [
        {
            "TxnID": "ABC-2",
            "CustomerRef": '{"ListID":"CUST-2","FullName":"Beta LLC"}',
            "InvoiceLineRet": '[{"TxnLineID":"LINE-9","Amount":"15.00"}]',
        }
    ]

    headers, lines = unpack_qbd_invoices(rows)

    assert headers[0]["customer_list_id"] == "CUST-2"
    assert len(lines) == 1
    assert lines[0]["TxnLineID"] == "LINE-9"


def test_consolidate_unpacks_qbd_invoices_into_lines(tmp_path) -> None:
    import json

    from meshflow.ingest.storage import write_parquet_local
    from meshflow.silver.consolidate import consolidate_source
    from meshflow.silver.settings import ConsolidateSettings

    source = "qbd"
    run_dir = tmp_path / "raw" / source / "20260101T120000Z"
    run_dir.mkdir(parents=True)
    invoice_rows = [
        {
            "TxnID": "ABC-1",
            "RefNumber": "1001",
            "CustomerRef": {"ListID": "1", "FullName": "Alpha"},
            "InvoiceLineRet": [{"TxnLineID": "L1", "Amount": "10.00"}],
        }
    ]
    manifest = {
        "entity_bundle": "v1_accounting",
        "entities": [{"entity": "invoices", "row_count": 1}],
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    write_parquet_local(run_dir / "invoices", "data.parquet", invoice_rows)

    settings = ConsolidateSettings(
        source=source,
        data_dir=tmp_path,
        raw_prefix=f"raw/{source}",
    )
    manifest = consolidate_source(settings)

    entities = {item["entity"]: item for item in manifest["entities"]}
    assert entities["invoices"]["row_count"] == 1
    assert entities["invoice_lines"]["row_count"] == 1
    assert (tmp_path / "silver_stg" / source / "invoice_lines" / "data.parquet").is_file()
