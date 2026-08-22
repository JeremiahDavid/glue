from __future__ import annotations

from meshflow.storage.column_names import normalize_silver_column_name, normalize_silver_row


def test_normalize_silver_column_name_maps_odata_fields() -> None:
    assert normalize_silver_column_name("@odata.etag") == "odata_etag"
    assert normalize_silver_column_name("@odata.context") == "odata_context"


def test_normalize_silver_column_name_preserves_camel_case() -> None:
    assert normalize_silver_column_name("displayName") == "displayName"
    assert normalize_silver_column_name("id") == "id"


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
