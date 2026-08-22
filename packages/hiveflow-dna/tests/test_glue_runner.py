"""Tests for DNA Glue pack-scoped copy of silver_stg → silver."""

from __future__ import annotations

from pathlib import Path

from hiveflow.dna.glue_runner import (
    _sync_dna_silver_glue,
    copy_silver_stg_to_silver,
    prune_dna_silver,
    resolve_dna_silver_entities,
)
from hiveflow.dna.settings import DnaSettings
from hiveflow.dna.sql_pack import parse_sql_manifest


def test_copy_silver_stg_to_silver_local(tmp_path: Path) -> None:
    settings = DnaSettings(source="dbc", data_dir=tmp_path, company="POC")
    stg = tmp_path / "silver_stg" / "dbc" / "customers"
    stg.mkdir(parents=True)
    payload = b"parquet-bytes"
    (stg / "data.parquet").write_bytes(payload)

    result = copy_silver_stg_to_silver(
        settings,
        source="dbc",
        entities=["customers", "missing_entity"],
    )

    assert result["copied"] == ["customers"]
    assert result["skipped"] == ["missing_entity"]
    dest = tmp_path / "silver" / "dbc" / "customers" / "data.parquet"
    assert dest.is_file()
    assert dest.read_bytes() == payload
    assert result["catalog_skipped"] == []


def test_copy_silver_stg_skips_empty_glue_schema(monkeypatch) -> None:
    settings = DnaSettings(source="dbc", data_dir=Path("."), company="POC", s3_bucket="bucket")
    copied: list[str] = []

    def fake_copy(*, bucket: str, source: str, entity: str) -> bool:
        del bucket, source
        copied.append(entity)
        return True

    def fake_sync(_settings, **kwargs) -> bool:
        return kwargs["entity"] != "vendors"

    monkeypatch.setattr("hiveflow.dna.glue_runner._copy_s3_entity", fake_copy)
    monkeypatch.setattr("hiveflow.dna.glue_runner._sync_dna_silver_glue", fake_sync)

    result = copy_silver_stg_to_silver(
        settings,
        source="dbc",
        entities=["customers", "vendors"],
    )

    assert copied == ["customers", "vendors"]
    assert result["copied"] == ["customers", "vendors"]
    assert result["catalog_skipped"] == ["vendors"]
    assert result["skipped"] == []


def test_sync_dna_silver_glue_skips_empty_parquet(monkeypatch) -> None:
    settings = DnaSettings(source="dbc", data_dir=Path("."), company="POC", s3_bucket="bucket")

    def boom(*_args, **_kwargs):
        raise ValueError("No columns inferred from s3://bucket/silver/dbc/vendors/data.parquet")

    monkeypatch.setattr("hiveflow.catalog.glue_schema.sync_silver_table_schema", boom)
    assert (
        _sync_dna_silver_glue(
            settings,
            source="dbc",
            entity="vendors",
            company="POC",
            environment="dev",
            region=None,
        )
        is False
    )


def test_prune_dna_silver_keeps_pack_entities(tmp_path: Path) -> None:
    settings = DnaSettings(source="dbc", data_dir=tmp_path, company="POC")
    for entity in ("customers", "vendors"):
        dest = tmp_path / "silver" / "dbc" / entity
        dest.mkdir(parents=True)
        (dest / "data.parquet").write_bytes(b"x")

    result = prune_dna_silver(settings, source="dbc", keep_entities=["customers"])

    assert result["removed_prefixes"] == ["vendors"]
    assert (tmp_path / "silver" / "dbc" / "customers" / "data.parquet").is_file()
    assert not (tmp_path / "silver" / "dbc" / "vendors").exists()


def test_resolve_dna_silver_entities_from_sql_pack(monkeypatch) -> None:
    settings = DnaSettings(source="dbc", data_dir=Path("."), company="POC")
    digest = "a" * 64
    pack = parse_sql_manifest(
        {
            "version": "1.0.0",
            "transforms": [
                {
                    "id": "enhance__customers",
                    "layer": "silver",
                    "mode": "add_columns",
                    "file": "silver/enhance__customers.sql",
                    "sha256": digest,
                    "target_entity": "customers",
                },
                {
                    "id": "kpi_rev",
                    "layer": "gold",
                    "mode": "kpi",
                    "file": "gold/kpi_rev.sql",
                    "sha256": digest,
                    "output_id": "out_kpi_snapshot",
                    "grain_columns": ["customerId"],
                },
            ],
        }
    )

    monkeypatch.setattr("hiveflow.dna.glue_runner.load_sql_pack", lambda _settings: pack)
    monkeypatch.setattr(
        "hiveflow.dna.glue_runner.load_transform_sql",
        lambda *_args, **_kwargs: "SELECT SUM(amount) FROM silver_dbc_sales_invoice_lines",
    )

    assert resolve_dna_silver_entities(settings, source="dbc") == [
        "customers",
        "sales_invoice_lines",
    ]
