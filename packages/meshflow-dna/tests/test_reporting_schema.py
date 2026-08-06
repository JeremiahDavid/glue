"""Reporting pack JSON Schema validation (approve/save gate)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from meshflow.dna.reporting import (
    default_reporting_pack,
    load_reporting_boilerplate,
    load_reporting_pack,
    load_reporting_pack_yaml,
    reporting_boilerplate_path,
    save_reporting_pack,
    validate_reporting_pack_schema,
)
from meshflow.dna.settings import DnaSettings


def _minimal_pack(**overrides: object) -> dict:
    payload = default_reporting_pack(pack_id="poc_reporting_config", version="1.0.0")
    payload.update(overrides)
    return payload


def test_boilerplate_passes_schema() -> None:
    path = reporting_boilerplate_path()
    assert path.is_file()
    loaded = load_reporting_pack_yaml(path.read_text(encoding="utf-8"))
    assert loaded["pack_id"] == "dbc_reporting_boilerplate"
    assert loaded["include_chart_catalog"] is True
    assert loaded["pages"]


def test_load_reporting_boilerplate_rewrites_identity() -> None:
    loaded = load_reporting_boilerplate(pack_id="acme_reporting_config", version="2.0.0")
    assert loaded["pack_id"] == "acme_reporting_config"
    assert loaded["version"] == "2.0.0"
    assert loaded["include_chart_catalog"] is True


def test_load_preserves_include_chart_catalog() -> None:
    payload = _minimal_pack(include_chart_catalog=True)
    loaded = load_reporting_pack(payload)
    assert loaded["include_chart_catalog"] is True


def test_invalid_layout_enum_rejected() -> None:
    payload = _minimal_pack(
        pages=[
            {
                "id": "page_exec",
                "title": "Executive",
                "sections": [{"id": "sec1", "layout": "not_a_layout"}],
            }
        ]
    )
    with pytest.raises(ValueError, match="schema error"):
        validate_reporting_pack_schema(payload)


def test_table_missing_source_output_rejected() -> None:
    payload = _minimal_pack(
        pages=[
            {
                "id": "page_exec",
                "title": "Executive",
                "sections": [
                    {
                        "id": "sec_top",
                        "layout": "ranked_table",
                        "table": {"limit": 10},
                    }
                ],
            }
        ]
    )
    with pytest.raises(ValueError, match="source_output|schema error"):
        load_reporting_pack(payload)


def test_malformed_dim_join_rejected() -> None:
    payload = _minimal_pack(
        pages=[
            {
                "id": "page_exec",
                "title": "Executive",
                "sections": [
                    {
                        "id": "sec_top",
                        "layout": "ranked_table",
                        "table": {
                            "source_output": "out_top_customers_ytd",
                            "dim_join": {"label_columns": ["displayName"]},
                        },
                    }
                ],
            }
        ]
    )
    with pytest.raises(ValueError, match="schema error"):
        load_reporting_pack(payload)


def test_save_reporting_pack_blocks_invalid(tmp_path: Path) -> None:
    settings = DnaSettings(source="dbc", data_dir=tmp_path, company="POC")
    bad = _minimal_pack(
        pages=[
            {
                "id": "page_exec",
                "title": "Executive",
                "sections": [{"layout": "ranked_table", "table": {}}],
            }
        ]
    )
    with pytest.raises(ValueError, match="schema error"):
        save_reporting_pack(
            settings,
            pack_id=settings.dna_config_id,
            version="1.0.1",
            reporting=bad,
            status="production",
        )


def test_valid_ranked_table_with_dim_join_loads() -> None:
    payload = _minimal_pack(
        pages=[
            {
                "id": "page_exec",
                "title": "Executive",
                "sections": [
                    {
                        "id": "sec_top",
                        "layout": "ranked_table",
                        "table": {
                            "source_output": "out_top_customers_ytd",
                            "limit": 10,
                            "dim_join": {
                                "output": "out_dim_customers",
                                "id_column": "customerId",
                                "label_columns": ["displayName"],
                                "title_column": "Customer",
                            },
                        },
                    }
                ],
            }
        ]
    )
    loaded = load_reporting_pack(payload)
    section = loaded["pages"][0]["sections"][0]
    assert section["table"]["dim_join"]["output"] == "out_dim_customers"


def test_yaml_roundtrip_invalid_layout_blocked() -> None:
    text = yaml.safe_dump(
        _minimal_pack(
            pages=[
                {
                    "id": "page_exec",
                    "title": "Executive",
                    "sections": [{"layout": "mystery_grid"}],
                }
            ]
        )
    )
    with pytest.raises(ValueError, match="schema error"):
        load_reporting_pack_yaml(text)
