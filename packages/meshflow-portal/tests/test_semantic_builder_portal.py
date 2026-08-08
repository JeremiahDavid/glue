"""Tests for Semantic Builder portal routes and API."""

from __future__ import annotations

from pathlib import Path

import pytest
from werkzeug.test import Client

from meshflow.dna.init_client import init_client_governance
from meshflow.dna.semantic_model import ensure_semantic_model_seed
from meshflow.dna.settings import DnaSettings
from meshflow.dna.web.app import create_app
from meshflow.dna.web.portal.semantics.model_api import builder_payload
from meshflow.project_config import load_project_config


@pytest.fixture
def portal_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HIVEFLOW_PORTAL_USERNAME", "poc")
    monkeypatch.setenv("HIVEFLOW_PORTAL_PASSWORD", "changeme")
    monkeypatch.setenv("HIVEFLOW_PORTAL_CLIENT_ID", "poc")


@pytest.fixture
def seeded_settings(tmp_path: Path) -> DnaSettings:
    settings = DnaSettings(source="dbc", data_dir=tmp_path, company="POC")
    init_client_governance(settings, company="POC")
    ensure_semantic_model_seed(settings)
    return settings


def _client(tmp_path: Path) -> Client:
    settings = DnaSettings(source="dbc", data_dir=tmp_path, company="POC")
    init_client_governance(settings, company="POC")
    ensure_semantic_model_seed(settings)
    config = load_project_config()
    try:
        from meshflow.project_config import get_platform_environment_config

        env_config = get_platform_environment_config("dev")
    except KeyError:
        env_config = config["companies"]["POC"]["environments"]["dev"]
    return Client(create_app(settings, company="POC", environment="dev", env_config=env_config))


def test_builder_payload(seeded_settings: DnaSettings) -> None:
    payload = builder_payload(seeded_settings)
    assert payload["draft"]["status"] == "draft"
    assert "coverage" in payload
    assert "readiness" in payload
    assert payload["workflow"]["init_completed"] is False


def test_semantic_builder_page_renders(tmp_path: Path, portal_env: None) -> None:
    client = _client(tmp_path)
    client.post("/portal/login", data={"username": "poc", "password": "changeme"})
    response = client.get("/portal/semantics/builder")
    assert response.status_code == 200
    assert b"Semantic Builder" in response.data
    assert b"Initialize from source docs" in response.data
    assert b'id="semantic-builder-content"' in response.data


def test_semantic_model_api_requires_auth(tmp_path: Path) -> None:
    client = _client(tmp_path)
    response = client.get("/api/semantic-model")
    assert response.status_code == 401


def test_semantic_model_graph_api(tmp_path: Path, portal_env: None) -> None:
    client = _client(tmp_path)
    client.post("/portal/login", data={"username": "poc", "password": "changeme"})
    response = client.get("/api/semantic-model/graph")
    assert response.status_code == 200
    payload = response.get_json()
    assert "graph" in payload
    assert "svg" in payload
    assert "semantic-graph-svg" in payload["svg"]
    assert "facts" in payload
    assert payload.get("mode") in {"overview", "roles", "fact"}


def test_semantic_model_graph_api_focus_fact(tmp_path: Path, portal_env: None) -> None:
    from meshflow.dna.semantic_init import run_semantic_init
    from meshflow.ingest.storage import write_parquet_local
    from meshflow.storage.paths import prefix_path, silver_entity_prefix

    settings = DnaSettings(source="dbc", data_dir=tmp_path, company="POC")
    out_dir = prefix_path(tmp_path, silver_entity_prefix("dbc", "customers"))
    write_parquet_local(out_dir, "data.parquet", [{"id": "c1", "displayName": "Acme"}])

    client = _client(tmp_path)
    client.post("/portal/login", data={"username": "poc", "password": "changeme"})
    run_semantic_init(settings, username="tester", enable_llm_tagging=False)

    response = client.get("/api/semantic-model/graph?fact=sales_invoice_lines")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload.get("mode") == "fact"
    assert payload.get("focus_fact") == "sales_invoice_lines"


def test_semantic_model_builder_ui_api(tmp_path: Path, portal_env: None) -> None:
    client = _client(tmp_path)
    client.post("/portal/login", data={"username": "poc", "password": "changeme"})
    response = client.get("/api/semantic-model/builder-ui")
    assert response.status_code == 200
    payload = response.get_json()
    assert "html" in payload
    assert "coverage" in payload
    assert "semantic-builder-coverage" in payload["html"]


def test_semantic_model_init_api_skips_sync_llm(
    tmp_path: Path, portal_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    from meshflow.ingest.storage import write_parquet_local
    from meshflow.storage.paths import prefix_path, silver_entity_prefix

    settings = DnaSettings(source="dbc", data_dir=tmp_path, company="POC")
    out_dir = prefix_path(tmp_path, silver_entity_prefix("dbc", "customers"))
    write_parquet_local(out_dir, "data.parquet", [{"id": "c1", "displayName": "Acme"}])

    def _boom(*_args, **_kwargs):
        raise AssertionError("sync LLM tagging must not run on portal init")

    monkeypatch.setattr(
        "meshflow.dna.semantic_column_tagger.apply_llm_tags_to_attributes",
        _boom,
    )
    monkeypatch.setattr(
        "meshflow.dna.web.portal.semantics.init_service.enqueue_semantic_llm_tagging",
        lambda **_kwargs: {"status": "skipped", "reason": "test"},
    )

    client = _client(tmp_path)
    client.post("/portal/login", data={"username": "poc", "password": "changeme"})
    response = client.post(
        "/api/semantic-model/init",
        data=b"{}",
        content_type="application/json",
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "initialized"
    assert payload["llm_tagging"]["reason"] == "async"


def test_semantic_model_entity_and_attribute_reject(
    tmp_path: Path, portal_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    from meshflow.ingest.storage import write_parquet_local
    from meshflow.dna.semantic_init import run_semantic_init
    from meshflow.dna.semantic_model import load_semantic_model_draft, save_semantic_model_draft
    from meshflow.storage.paths import prefix_path, silver_entity_prefix

    settings = DnaSettings(source="dbc", data_dir=tmp_path, company="POC")
    init_client_governance(settings, company="POC")
    out_dir = prefix_path(tmp_path, silver_entity_prefix("dbc", "customers"))
    write_parquet_local(out_dir, "data.parquet", [{"id": "c1", "displayName": "Acme"}])

    monkeypatch.setattr(
        "meshflow.dna.semantic_column_tagger.apply_llm_tags_to_attributes",
        lambda *_args, **_kwargs: {"tagged_count": 0, "skipped_count": 0, "reason": "disabled"},
    )
    run_semantic_init(settings, username="admin@test.com", enable_llm_tagging=False)

    draft = load_semantic_model_draft(settings)
    entity_id = str((draft.get("entities") or [{}])[0].get("id") or "")
    assert entity_id

    attributes = list(draft.get("attributes") or [])
    attr_entity = "customers"
    attr_column = "_test_tag_column"
    attributes.append(
        {
            "entity": attr_entity,
            "column": attr_column,
            "concepts": ["customer_name"],
            "status": "proposed",
        }
    )
    draft["attributes"] = attributes
    save_semantic_model_draft(settings, draft, username="admin@test.com")

    client = _client(tmp_path)
    client.post("/portal/login", data={"username": "poc", "password": "changeme"})

    entity_reject = client.post(f"/api/semantic-model/entities/{entity_id}/reject")
    assert entity_reject.status_code == 200
    updated = load_semantic_model_draft(settings)
    entity_status = next(
        str(item.get("status") or "")
        for item in updated.get("entities") or []
        if str(item.get("id") or "") == entity_id
    )
    assert entity_status == "rejected"

    attr_reject = client.post(
        f"/api/semantic-model/attributes/{attr_entity}/{attr_column}/reject"
    )
    assert attr_reject.status_code == 200
    updated = load_semantic_model_draft(settings)
    attr_status = next(
        str(item.get("status") or "")
        for item in updated.get("attributes") or []
        if str(item.get("entity") or "") == attr_entity
        and str(item.get("column") or "") == attr_column
    )
    assert attr_status == "rejected"
