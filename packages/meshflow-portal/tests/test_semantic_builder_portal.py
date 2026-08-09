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


def _reporting_client(tmp_path: Path) -> Client:
    settings = DnaSettings(source="dbc", data_dir=tmp_path, company="POC")
    init_client_governance(settings, company="POC")
    ensure_semantic_model_seed(settings)
    config = load_project_config()
    try:
        from meshflow.project_config import get_platform_environment_config

        env_config = get_platform_environment_config("dev")
    except KeyError:
        env_config = config["companies"]["POC"]["environments"]["dev"]
    return Client(
        create_app(
            settings,
            company="POC",
            environment="dev",
            env_config=env_config,
            ui_mode="reporting",
        )
    )


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
    assert b"Profile silver" in response.data or b"Semantic builder process" in response.data
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
    assert payload["llm_tagging"]["reason"] == "deferred_to_step_3"


def test_semantic_model_init_enqueues_profiling_on_lambda(
    tmp_path: Path, portal_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    from meshflow.ingest.storage import write_parquet_local
    from meshflow.storage.paths import prefix_path, silver_entity_prefix

    monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "meshflow-ui-test")
    monkeypatch.setattr(
        "meshflow.dna.web.portal.semantics.init_service.enqueue_semantic_profiling",
        lambda **_kwargs: {"status": "enqueued", "status_code": 202},
    )

    out_dir = prefix_path(tmp_path, silver_entity_prefix("dbc", "customers"))
    write_parquet_local(out_dir, "data.parquet", [{"id": "c1", "displayName": "Acme"}])

    client = _client(tmp_path)
    client.post("/portal/login", data={"username": "poc", "password": "changeme"})
    response = client.post(
        "/api/semantic-model/init",
        data=b"{}",
        content_type="application/json",
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "enqueued"
    assert payload["profiling"]["status"] == "in_progress"


def test_semantic_model_init_force_requeues_when_profiling_stuck(
    tmp_path: Path, portal_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    from meshflow.dna.semantic_model import load_semantic_model_workflow, update_profiling_workflow
    from meshflow.ingest.storage import write_parquet_local
    from meshflow.storage.paths import prefix_path, silver_entity_prefix

    settings = DnaSettings(source="dbc", data_dir=tmp_path, company="POC")
    init_client_governance(settings, company="POC")
    ensure_semantic_model_seed(settings)
    update_profiling_workflow(settings, status="in_progress", username="poc")

    monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "meshflow-ui-test")
    enqueued: list[bool] = []

    def _enqueue(**_kwargs):
        enqueued.append(True)
        return {"status": "enqueued", "status_code": 202}

    monkeypatch.setattr(
        "meshflow.dna.web.portal.semantics.init_service.enqueue_semantic_profiling",
        _enqueue,
    )

    out_dir = prefix_path(tmp_path, silver_entity_prefix("dbc", "customers"))
    write_parquet_local(out_dir, "data.parquet", [{"id": "c1", "displayName": "Acme"}])

    client = _client(tmp_path)
    client.post("/portal/login", data={"username": "poc", "password": "changeme"})
    response = client.post(
        "/api/semantic-model/init",
        data=b'{"force": true}',
        content_type="application/json",
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "enqueued"
    assert enqueued == [True]
    workflow = load_semantic_model_workflow(settings)
    assert workflow.get("profiling_status") == "in_progress"


def test_semantic_model_generate_relationships_api(
    tmp_path: Path, portal_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    from meshflow.dna.semantic_init import run_semantic_init
    from meshflow.dna.semantic_model import load_semantic_model_draft, load_semantic_model_workflow, save_semantic_model_workflow
    from meshflow.ingest.storage import write_parquet_local
    from meshflow.storage.paths import prefix_path, silver_entity_prefix

    settings = DnaSettings(source="dbc", data_dir=tmp_path, company="POC")
    init_client_governance(settings, company="POC")
    out_dir = prefix_path(tmp_path, silver_entity_prefix("dbc", "customers"))
    write_parquet_local(out_dir, "data.parquet", [{"id": "c1", "customerId": "c1", "displayName": "Acme"}])
    out_dir = prefix_path(tmp_path, silver_entity_prefix("dbc", "sales_invoice_lines"))
    write_parquet_local(
        out_dir,
        "data.parquet",
        [{"id": "l1", "documentId": "inv1", "customerId": "c1"}],
    )

    monkeypatch.setattr(
        "meshflow.dna.semantic_column_tagger.apply_llm_tags_to_attributes",
        lambda *_args, **_kwargs: {"tagged_count": 0, "skipped_count": 0, "reason": "disabled"},
    )
    run_semantic_init(settings, username="admin@test.com", enable_llm_tagging=False)
    workflow = load_semantic_model_workflow(settings)
    workflow["current_step"] = "relationships"
    workflow["steps_completed"] = {"keys": True, "relationships": False, "tags": False}
    save_semantic_model_workflow(settings, workflow)

    draft = load_semantic_model_draft(settings)
    draft["relationships"] = []
    from meshflow.dna.semantic_model import save_semantic_model_draft

    save_semantic_model_draft(settings, draft, username="admin@test.com")

    client = _client(tmp_path)
    client.post("/portal/login", data={"username": "poc", "password": "changeme"})
    response = client.post(
        "/api/semantic-model/builder/generate-relationships",
        data=b'{"approve_proposed": true}',
        content_type="application/json",
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["result"]["added"] >= 1
    updated = load_semantic_model_draft(settings)
    assert updated.get("relationships")


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
    from meshflow.dna.semantic_model import load_semantic_model_workflow, save_semantic_model_workflow

    run_semantic_init(settings, username="admin@test.com", enable_llm_tagging=False)
    workflow = load_semantic_model_workflow(settings)
    workflow["current_step"] = "tags"
    workflow["steps_completed"] = {"keys": True, "relationships": True, "tags": False}
    save_semantic_model_workflow(settings, workflow)

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

    entity_approve = client.post(f"/api/semantic-model/entities/{entity_id}/approve")
    assert entity_approve.status_code == 200
    updated = load_semantic_model_draft(settings)
    entity_status = next(
        str(item.get("status") or "")
        for item in updated.get("entities") or []
        if str(item.get("id") or "") == entity_id
    )
    assert entity_status == "approved"

    attr_approve = client.post(
        f"/api/semantic-model/attributes/{attr_entity}/{attr_column}/approve"
    )
    assert attr_approve.status_code == 200
    updated = load_semantic_model_draft(settings)
    attr_status = next(
        str(item.get("status") or "")
        for item in updated.get("attributes") or []
        if str(item.get("entity") or "") == attr_entity
        and str(item.get("column") or "") == attr_column
    )
    assert attr_status == "approved"

    entity_propose = client.post(f"/api/semantic-model/entities/{entity_id}/propose")
    assert entity_propose.status_code == 200
    updated = load_semantic_model_draft(settings)
    entity_status = next(
        str(item.get("status") or "")
        for item in updated.get("entities") or []
        if str(item.get("id") or "") == entity_id
    )
    assert entity_status == "proposed"

    builder_ui = client.get("/api/semantic-model/builder-ui")
    assert builder_ui.status_code == 200
    html = builder_ui.get_json()["html"]
    assert "semantics-status-approved" in html
    assert f'data-attr-reject="{attr_entity}::{attr_column}"' in html


def test_semantic_model_complete_step_reporting_mode(
    tmp_path: Path, portal_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    from meshflow.ingest.storage import write_parquet_local
    from meshflow.dna.semantic_init import run_semantic_init
    from meshflow.dna.semantic_model import load_semantic_model_draft, load_semantic_model_workflow
    from meshflow.storage.paths import prefix_path, silver_entity_prefix

    entities = {
        "customers": [{"id": "c1", "number": "C001", "displayName": "Acme"}],
        "items": [{"id": "i1", "number": "ITEM1", "displayName": "Widget"}],
        "sales_invoice_lines": [
            {
                "id": "l1",
                "documentId": "inv1",
                "customerId": "c1",
                "itemId": "i1",
                "netAmount": 100.0,
                "postingDate": "2024-01-15",
            }
        ],
    }
    for entity, rows in entities.items():
        out_dir = prefix_path(tmp_path, silver_entity_prefix("dbc", entity))
        write_parquet_local(out_dir, "data.parquet", rows)

    monkeypatch.setattr(
        "meshflow.dna.semantic_column_tagger.apply_llm_tags_to_attributes",
        lambda *_args, **_kwargs: {"tagged_count": 0, "skipped_count": 0, "reason": "disabled"},
    )

    settings = DnaSettings(source="dbc", data_dir=tmp_path, company="POC")
    run_semantic_init(settings, username="admin@test.com", enable_llm_tagging=False)

    client = _reporting_client(tmp_path)
    client.post("/portal/login", data={"username": "poc", "password": "changeme"})
    response = client.post(
        "/api/semantic-model/workflow/complete-step",
        json={"step": "keys"},
    )
    assert response.status_code == 200
    workflow = load_semantic_model_workflow(settings)
    assert workflow.get("current_step") == "relationships"
    assert (workflow.get("steps_completed") or {}).get("keys") is True
    draft = load_semantic_model_draft(settings)
    assert len(draft.get("relationships") or []) >= 1


def test_semantic_model_builder_manual_pk_api(
    tmp_path: Path, portal_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    from meshflow.ingest.storage import write_parquet_local
    from meshflow.dna.semantic_init import run_semantic_init
    from meshflow.storage.paths import prefix_path, silver_entity_prefix

    out_dir = prefix_path(tmp_path, silver_entity_prefix("dbc", "customers"))
    write_parquet_local(out_dir, "data.parquet", [{"id": "c1", "number": "C001"}])

    monkeypatch.setattr(
        "meshflow.dna.semantic_column_tagger.apply_llm_tags_to_attributes",
        lambda *_args, **_kwargs: {"tagged_count": 0, "skipped_count": 0, "reason": "disabled"},
    )

    settings = DnaSettings(source="dbc", data_dir=tmp_path, company="POC")
    run_semantic_init(settings, username="admin@test.com", enable_llm_tagging=False)

    client = _reporting_client(tmp_path)
    client.post("/portal/login", data={"username": "poc", "password": "changeme"})
    response = client.post(
        "/api/semantic-model/builder/primary-key",
        json={"entity": "customers", "column": "number"},
    )
    assert response.status_code == 200
    draft = response.get_json()["draft"]
    customer = next(e for e in draft["entities"] if e.get("silver_entity") == "customers")
    assert customer.get("primary_key") == "number"
    assert customer.get("primary_key_status") == "proposed"
