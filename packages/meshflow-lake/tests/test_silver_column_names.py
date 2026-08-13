from __future__ import annotations

import json

from meshflow.ingest.storage import write_parquet_local
from meshflow.silver.column_names import normalize_silver_column_name, normalize_silver_row
from meshflow.silver.consolidate import consolidate_source
from meshflow.silver.settings import ConsolidateSettings


def test_normalize_silver_column_name_maps_odata_fields() -> None:
    assert normalize_silver_column_name("@odata.etag") == "odata_etag"
    assert normalize_silver_column_name("@odata.context") == "odata_context"


def test_normalize_silver_column_name_preserves_camel_case() -> None:
    assert normalize_silver_column_name("displayName") == "displayName"
    assert normalize_silver_column_name("id") == "id"


def test_normalize_silver_column_name_handles_invalid_chars() -> None:
    assert normalize_silver_column_name("Customer Name") == "Customer_Name"
    assert normalize_silver_column_name("99days") == "_99days"


def test_normalize_silver_row_renames_keys() -> None:
    row = normalize_silver_row(
        {
            "id": "1",
            "@odata.etag": "W/\"abc\"",
            "displayName": "Acme",
        }
    )
    assert row == {
        "id": "1",
        "odata_etag": "W/\"abc\"",
        "displayName": "Acme",
    }


def test_normalize_silver_row_resolves_collisions() -> None:
    row = normalize_silver_row(
        {
            "@odata.etag": "from-annotation",
            "odata_etag": "from-field",
        }
    )
    assert row["odata_etag"] == "from-annotation"
    assert row["odata_etag_2"] == "from-field"


def test_consolidate_source_normalizes_silver_columns(tmp_path) -> None:
    source = "dbc"
    run_dir = tmp_path / "raw" / source / "20260101T120000Z"
    run_dir.mkdir(parents=True)
    rows = [
        {
            "id": "11111111-1111-1111-1111-111111111111",
            "@odata.etag": 'W/"etag-value"',
            "displayName": "Contoso",
        }
    ]
    manifest = {
        "entity_bundle": "v1_accounting",
        "entities": [
            {"entity": "customers", "row_count": len(rows), "path": str(run_dir / "customers.parquet")},
        ],
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    write_parquet_local(run_dir, "customers.parquet", rows)

    settings = ConsolidateSettings(
        source=source,
        data_dir=tmp_path,
        raw_prefix=f"raw/{source}",
    )
    consolidate_source(settings)

    import pyarrow.parquet as pq

    table = pq.read_table(tmp_path / "silver" / source / "customers" / "data.parquet")
    assert table.column_names == ["id", "odata_etag", "displayName"]
