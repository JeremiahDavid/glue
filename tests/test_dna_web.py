from __future__ import annotations

from pathlib import Path

from werkzeug.test import Client

from meshflow.dna.settings import DnaSettings
from meshflow.dna.web.app import REVENUE_TABLE_LIMIT, create_app


def test_web_app_home_and_definitions(tmp_path: Path) -> None:
    settings = DnaSettings(source="dbc", data_dir=tmp_path, pack_id="bc_intra_v1")
    client = Client(create_app(settings))

    home = client.get("/")
    assert home.status_code == 200
    assert b"HiveFlowAI" in home.data or b"Hive Flow" in home.data
    assert b"Executive snapshot" in home.data

    definitions = client.get("/definitions")
    assert definitions.status_code == 200
    assert b"bc_intra_v1" in definitions.data

    revenue = client.get("/revenue")
    assert revenue.status_code == 200
    assert b"out_fact_revenue_lines" in revenue.data

    static = client.get("/static/hiveflowai-symbol.png")
    assert static.status_code == 200
    assert static.mimetype == "image/png"


def test_web_app_api_endpoints(tmp_path: Path) -> None:
    settings = DnaSettings(source="dbc", data_dir=tmp_path, pack_id="bc_intra_v1")
    client = Client(create_app(settings))

    pack = client.get("/api/pack")
    assert pack.status_code == 200
    assert pack.json["pack_id"] == "bc_intra_v1"

    revenue = client.get("/api/revenue")
    assert revenue.status_code == 200
    assert revenue.json["output_id"] == "out_fact_revenue_lines"
    assert revenue.json["row_count"] == 0
    assert len(revenue.json["rows"]) <= REVENUE_TABLE_LIMIT
