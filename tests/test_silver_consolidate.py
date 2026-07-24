from __future__ import annotations

from meshflow.silver.consolidate import upsert_rows
from meshflow.silver.keys import row_merge_key


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

    from meshflow.ingest.storage import write_parquet_local
    from meshflow.silver.consolidate import consolidate_source
    from meshflow.silver.settings import ConsolidateSettings

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

    settings = ConsolidateSettings(source=source, data_dir=tmp_path, s3_prefix=source)
    manifest = consolidate_source(settings)

    assert manifest["processed_run_count"] == 2
    assert len(manifest["entities"]) == 2
    customers = next(item for item in manifest["entities"] if item["entity"] == "customers")
    invoices = next(item for item in manifest["entities"] if item["entity"] == "invoices")
    assert customers["row_count"] == 2
    assert invoices["row_count"] == 2

    consolidated_dir = tmp_path / "raw" / source / "_consolidated"
    assert (consolidated_dir / "customers.parquet").is_file()
    assert (consolidated_dir / "state.json").is_file()

    second_pass = consolidate_source(settings)
    assert second_pass["runs_applied_this_execution"] == []
