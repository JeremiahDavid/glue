from __future__ import annotations

from hiveflow.silver.consolidate import upsert_rows
from hiveflow.silver.keys import row_merge_key


def test_upsert_rows_uses_qbd_list_id() -> None:
    table: dict[str, dict] = {}
    applied = upsert_rows(
        table,
        [{"ListID": "1", "Name": "Alpha"}, {"ListID": "2", "Name": "Beta"}],
        "customers",
    )
    assert applied == 2
    assert len(table) == 2


def test_upsert_rows_updates_existing_key() -> None:
    table: dict[str, dict] = {"1": {"ListID": "1", "Name": "Old"}}
    upsert_rows(table, [{"ListID": "1", "Name": "New"}], "customers")
    assert table["1"]["Name"] == "New"


def test_row_merge_key_falls_back_to_qbo_id() -> None:
    assert row_merge_key({"Id": "77", "DisplayName": "Acme"}, "customers") == "77"


def test_row_merge_key_uses_txn_id_for_invoices() -> None:
    assert row_merge_key({"TxnID": "ABC-1", "RefNumber": "1001"}, "invoices") == "ABC-1"


def test_consolidate_source_merges_two_bronze_runs(tmp_path) -> None:
    import json

    from hiveflow.ingest.storage import write_parquet_local
    from hiveflow.silver.consolidate import consolidate_source
    from hiveflow.silver.settings import ConsolidateSettings

    source = "qbd"
    run_a = tmp_path / "raw" / source / "20260101T120000Z"
    run_b = tmp_path / "raw" / source / "20260102T120000Z"
    for run_dir, entities in (
        (
            run_a,
            [
                ("customers", [{"ListID": "1", "Name": "Alpha"}]),
                ("invoices", [{"TxnID": "T1", "RefNumber": "100"}]),
            ],
        ),
        (
            run_b,
            [
                ("customers", [{"ListID": "1", "Name": "Alpha Updated"}, {"ListID": "2", "Name": "Beta"}]),
                ("invoices", [{"TxnID": "T2", "RefNumber": "101"}]),
            ],
        ),
    ):
        run_dir.mkdir(parents=True)
        manifest = {
            "entity_bundle": "v1_accounting",
            "company_name": "Test Co",
            "entities": [
                {"entity": name, "row_count": len(rows), "path": str(run_dir / f"{name}.parquet")}
                for name, rows in entities
            ],
        }
        (run_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        for name, rows in entities:
            write_parquet_local(run_dir, f"{name}.parquet", rows)

    settings = ConsolidateSettings(
        source=source,
        data_dir=tmp_path,
        raw_prefix=f"raw/{source}",
    )
    manifest = consolidate_source(settings)

    assert manifest["processed_run_count"] == 2
    entities = {item["entity"]: item for item in manifest["entities"]}
    assert set(entities) == {"customers", "invoices", "invoice_lines"}
    assert entities["customers"]["row_count"] == 2
    assert entities["invoices"]["row_count"] == 2
    assert entities["invoice_lines"]["row_count"] == 0

    silver_dir = tmp_path / "silver_stg" / source / "customers"
    assert (silver_dir / "data.parquet").is_file()
    assert (tmp_path / "silver_stg" / source / "_state" / "state.json").is_file()

    second_pass = consolidate_source(settings)
    assert second_pass["runs_applied_this_execution"] == []
