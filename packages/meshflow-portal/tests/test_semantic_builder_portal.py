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
    assert b"semantic-builder-step-nav" in response.data
    assert b"semantic-builder-start-btn" in response.data
    assert b"Start semantic build" in response.data
    assert b"semantic-builder-nav" not in response.data


def test_semantic_builder_step_pages_renders(tmp_path: Path, portal_env: None) -> None:
    client = _client(tmp_path)
    client.post("/portal/login", data={"username": "poc", "password": "changeme"})
    for path in (
        "/portal/semantics/builder/keys",
        "/portal/semantics/builder/relationships",
        "/portal/semantics/builder/tags",
        "/portal/semantics/builder/decisions",
    ):
        response = client.get(path)
        assert response.status_code == 200
        assert b"semantic-builder-step-nav" in response.data
        assert b'id="semantic-builder-content"' in response.data
        assert b"Loading semantic builder" in response.data


def test_semantic_model_api_requires_auth(tmp_path: Path) -> None:
    client = _client(tmp_path)
    response = client.get("/api/semantic-model")
    assert response.status_code == 401


def test_semantic_model_builder_ui_api(tmp_path: Path, portal_env: None) -> None:
    client = _client(tmp_path)
    client.post("/portal/login", data={"username": "poc", "password": "changeme"})
    response = client.get("/api/semantic-model/builder-ui?page=keys")
    assert response.status_code == 200
    payload = response.get_json()
    assert "html" in payload
    assert "workflow" in payload
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

    builder_ui = client.get("/api/semantic-model/builder-ui?page=tags")
    assert builder_ui.status_code == 200
    html = builder_ui.get_json()["html"]
    assert "semantics-status-approved" in html
    assert f'data-attr-reject="{attr_entity}::{attr_column}"' in html


def test_semantic_model_approve_all_keys_api(
    tmp_path: Path, portal_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    from meshflow.ingest.storage import write_parquet_local
    from meshflow.dna.semantic_init import run_semantic_init
    from meshflow.dna.semantic_model import load_semantic_model_draft
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

    builder_ui = client.get("/api/semantic-model/builder-ui?page=keys")
    assert builder_ui.status_code == 200
    assert b'id="semantic-approve-all-primary-keys"' in builder_ui.get_json()["html"].encode()

    response = client.post("/api/semantic-model/approve-all-primary-keys")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["primary_keys_approved"] >= 1

    draft = load_semantic_model_draft(settings)
    customer = next(e for e in draft["entities"] if e.get("silver_entity") == "customers")
    assert customer.get("primary_key_status") == "approved"


def test_semantic_model_question_resolve_api(
    tmp_path: Path, portal_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    from meshflow.ingest.storage import write_parquet_local
    from meshflow.dna.semantic_init import run_semantic_init
    from meshflow.dna.semantic_model import load_semantic_model_draft
    from meshflow.storage.paths import prefix_path, silver_entity_prefix

    out_dir = prefix_path(tmp_path, silver_entity_prefix("dbc", "customers"))
    write_parquet_local(out_dir, "data.parquet", [{"id": "c1", "displayName": "Acme"}])

    monkeypatch.setattr(
        "meshflow.dna.semantic_column_tagger.apply_llm_tags_to_attributes",
        lambda *_args, **_kwargs: {"tagged_count": 0, "skipped_count": 0, "reason": "disabled"},
    )

    settings = DnaSettings(source="dbc", data_dir=tmp_path, company="POC")
    run_semantic_init(settings, username="admin@test.com", enable_llm_tagging=False)

    client = _client(tmp_path)
    client.post("/portal/login", data={"username": "poc", "password": "changeme"})

    builder_ui = client.get("/api/semantic-model/builder-ui?page=decisions")
    assert builder_ui.status_code == 200
    assert "data-question-id" in builder_ui.get_json()["html"]
    assert "semantic-submit-decisions" in builder_ui.get_json()["html"]
    assert "Document later" in builder_ui.get_json()["html"]

    keys_ui = client.get("/api/semantic-model/builder-ui?page=keys")
    assert keys_ui.status_code == 200
    assert "semantic-submit-decisions" not in keys_ui.get_json()["html"]

    response = client.post(
        "/api/semantic-model/questions/q_revenue_date/resolve",
        json={"choice": "posting_date"},
    )
    assert response.status_code == 200

    draft = load_semantic_model_draft(settings)
    resolved = next(q for q in draft["questions"] if q.get("id") == "q_revenue_date")
    assert resolved.get("status") == "resolved"

    builder_ui = client.get("/api/semantic-model/builder-ui?page=decisions")
    html = builder_ui.get_json()["html"]
    assert "q_revenue_date" not in html


def test_semantic_builder_keys_revisit_after_complete_step(
    tmp_path: Path, portal_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    from meshflow.ingest.storage import write_parquet_local
    from meshflow.dna.semantic_init import run_semantic_init
    from meshflow.dna.semantic_model import load_semantic_model_workflow
    from meshflow.storage.paths import prefix_path, silver_entity_prefix

    out_dir = prefix_path(tmp_path, silver_entity_prefix("dbc", "customers"))
    write_parquet_local(out_dir, "data.parquet", [{"id": "c1", "number": "C001"}])

    monkeypatch.setattr(
        "meshflow.dna.semantic_column_tagger.apply_llm_tags_to_attributes",
        lambda *_args, **_kwargs: {"tagged_count": 0, "skipped_count": 0, "reason": "disabled"},
    )

    settings = DnaSettings(source="dbc", data_dir=tmp_path, company="POC")
    run_semantic_init(settings, username="admin@test.com", enable_llm_tagging=False)

    client = _client(tmp_path)
    client.post("/portal/login", data={"username": "poc", "password": "changeme"})

    complete = client.post(
        "/api/semantic-model/workflow/complete-step",
        json={"step": "keys"},
    )
    assert complete.status_code == 200
    workflow = load_semantic_model_workflow(settings)
    assert workflow.get("current_step") == "relationships"

    keys_page = client.get("/portal/semantics/builder/keys")
    assert keys_page.status_code == 200
    assert b"semantic-builder-step-nav" in keys_page.data

    workflow = load_semantic_model_workflow(settings)
    assert workflow.get("current_step") == "keys"

    builder_ui = client.get("/api/semantic-model/builder-ui?page=keys")
    html = builder_ui.get_json()["html"]
    assert "semantic-builder-revisit" not in html
    assert 'data-keys-tab="pk"' in html
    assert "data-pk-approve" in html or "semantic-builder-pk-select" in html


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
    client.post("/api/semantic-model/approve-all-primary-keys")
    response = client.post(
        "/api/semantic-model/workflow/complete-step",
        json={"step": "keys"},
    )
    assert response.status_code == 200
    workflow = load_semantic_model_workflow(settings)
    assert workflow.get("current_step") == "relationships"
    assert (workflow.get("steps_completed") or {}).get("keys") is True
    client.post("/api/semantic-model/approve-all-foreign-keys")
    rel_complete = client.post(
        "/api/semantic-model/workflow/complete-step",
        json={"step": "relationships"},
    )
    assert rel_complete.status_code == 200
    draft = load_semantic_model_draft(settings)
    assert len(draft.get("relationships") or []) >= 1


def test_semantic_model_complete_relationships_enqueues_tagging_on_lambda(
    tmp_path: Path, portal_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    from meshflow.ingest.storage import write_parquet_local
    from meshflow.dna.semantic_init import run_semantic_init
    from meshflow.dna.semantic_model import load_semantic_model_workflow, save_semantic_model_workflow
    from meshflow.storage.paths import prefix_path, silver_entity_prefix

    out_dir = prefix_path(tmp_path, silver_entity_prefix("dbc", "customers"))
    write_parquet_local(out_dir, "data.parquet", [{"id": "c1", "displayName": "Acme"}])

    def _boom(*_args, **_kwargs):
        raise AssertionError("sync LLM tagging must not run on portal complete-step")

    monkeypatch.setattr(
        "meshflow.dna.semantic_column_tagger.apply_llm_tags_to_attributes",
        _boom,
    )
    monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "meshflow-ui-test")
    monkeypatch.setattr(
        "meshflow.dna.web.portal.semantics.init_service.enqueue_semantic_llm_tagging",
        lambda **_kwargs: {"status": "enqueued", "status_code": 202},
    )

    settings = DnaSettings(source="dbc", data_dir=tmp_path, company="POC")
    run_semantic_init(settings, username="admin@test.com", enable_llm_tagging=False)
    workflow = load_semantic_model_workflow(settings)
    workflow["current_step"] = "relationships"
    workflow["steps_completed"] = {"keys": True, "relationships": False, "tags": False}
    save_semantic_model_workflow(settings, workflow)

    client = _client(tmp_path)
    client.post("/portal/login", data={"username": "poc", "password": "changeme"})
    response = client.post(
        "/api/semantic-model/workflow/complete-step",
        data=b'{"step": "relationships"}',
        content_type="application/json",
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "enqueued"
    assert payload["reason"] == "async_tagging"
    assert payload["side_effects"]["tagging"]["status"] == "in_progress"

    workflow = load_semantic_model_workflow(settings)
    assert workflow.get("tagging_status") == "in_progress"
    assert (workflow.get("steps_completed") or {}).get("relationships") is True
    assert workflow.get("current_step") == "tags"


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


def test_relationships_reference_panel_is_read_only() -> None:
    from meshflow.dna.web.portal.semantics.builder_render import _relationships_reference_panel

    entities = [
        {
            "id": "customers",
            "silver_entity": "customers",
            "primary_key": "id",
            "primary_key_status": "approved",
        },
        {
            "id": "orders",
            "silver_entity": "orders",
            "primary_key": "id",
            "primary_key_status": "approved",
        },
    ]
    attributes = [
        {
            "entity": "orders",
            "column": "customer_id",
            "role": "foreign_key",
            "fk_target_entity": "customers",
            "fk_target_column": "id",
            "status": "approved",
            "join_stats": {"match_rate": 1.0, "orphan_rate": 0.0},
        }
    ]
    relationships = [
        {
            "id": "r1",
            "from_entity": "orders",
            "from_column": "customer_id",
            "to_entity": "customers",
            "to_column": "id",
            "status": "approved",
            "join_stats": {"match_rate": 1.0, "orphan_rate": 0.0},
        }
    ]
    html = _relationships_reference_panel(
        entities,
        attributes,
        relationships,
        keys_step_completed=True,
    )
    assert "Reference only" in html
    assert "orders.customer_id" in html
    assert "data-rel-approve" not in html
    assert "semantic-approve-all-relationships" not in html


def test_relationships_table_sorts_by_join_count_and_bulk_actions() -> None:
    from meshflow.dna.web.portal.semantics.builder_render import _relationships_table

    relationships = [
        {
            "id": "r1",
            "from_entity": "alpha",
            "from_column": "a_id",
            "to_entity": "beta",
            "to_column": "id",
            "status": "proposed",
            "join_stats": {"match_rate": 1.0, "orphan_rate": 0.0},
        },
        {
            "id": "r2",
            "from_entity": "gamma",
            "from_column": "g_id",
            "to_entity": "delta",
            "to_column": "id",
            "status": "proposed",
            "join_stats": {"match_rate": 1.0, "orphan_rate": 0.0},
        },
        {
            "id": "r4",
            "from_entity": "gamma",
            "from_column": "g3_id",
            "to_entity": "zeta",
            "to_column": "id",
            "status": "proposed",
            "join_stats": {"match_rate": 1.0, "orphan_rate": 0.0},
        },
        {
            "id": "r3",
            "from_entity": "beta",
            "from_column": "b2_id",
            "to_entity": "epsilon",
            "to_column": "id",
            "status": "rejected",
            "join_stats": {"match_rate": 0.0, "orphan_rate": 1.0},
        },
    ]
    html = _relationships_table(relationships, is_admin=True, keys_step_completed=True)
    undecided_html = html.split("Submitted")[0]
    gamma_pos = undecided_html.index("gamma")
    alpha_pos = undecided_html.index("alpha")
    assert gamma_pos < alpha_pos
    assert "Undecided" in html
    assert "Submitted" in html
    assert "semantic-approve-all-100-matches" in html
    assert "semantic-approve-all-relationships" in html
    assert "data-rel-match-pct=\"100\"" in html


def test_keys_step_approved_and_need_action_sections() -> None:
    from meshflow.dna.web.portal.semantics.builder_render import _keys_step_section

    entities = [
        {
            "id": "customers",
            "silver_entity": "customers",
            "primary_key": "id",
            "primary_key_status": "approved",
            "pk_stats": {"pk_unique": True, "pk_null_rate": 0.0, "row_count": 10},
        },
        {
            "id": "orders",
            "silver_entity": "orders",
            "primary_key": "id",
            "primary_key_status": "proposed",
            "pk_stats": {"pk_unique": True, "pk_null_rate": 0.0, "row_count": 5},
        },
    ]
    attributes = [
        {
            "entity": "orders",
            "column": "customer_id",
            "role": "foreign_key",
            "fk_target_entity": "customers",
            "fk_target_column": "id",
            "status": "approved",
            "join_stats": {"match_rate": 1.0, "orphan_rate": 0.0},
        },
        {
            "entity": "orders",
            "column": "bad_id",
            "role": "foreign_key",
            "fk_target_entity": "customers",
            "fk_target_column": "id",
            "status": "proposed",
            "join_stats": {"match_rate": 0.0, "orphan_rate": 1.0},
        },
    ]
    html = _keys_step_section(entities, attributes, is_admin=True, builder_options={})
    assert html.count("semantic-builder-subsection-title") >= 2
    assert "Need action" in html
    assert "Approved" in html
    assert "semantic-builder-pk-tbody-need-action" in html
    assert "semantic-builder-pk-tbody-approved" in html
    assert "semantic-builder-fk-sections-need-action" in html
    assert "semantic-builder-fk-sections-approved" in html
    need_action_pos = html.index("semantic-builder-pk-tbody-need-action")
    approved_pos = html.index("semantic-builder-pk-tbody-approved")
    assert need_action_pos < approved_pos
    assert 'data-pk-status="proposed"' in html
    assert 'data-pk-status="approved"' in html


def test_keys_step_fk_need_action_excludes_tables_without_proposed_fks() -> None:
    from meshflow.dna.web.portal.semantics.builder_render import _keys_step_section

    entities = [
        {
            "id": "customers",
            "silver_entity": "customers",
            "primary_key": "id",
            "primary_key_status": "proposed",
            "pk_stats": {"pk_unique": True, "pk_null_rate": 0.0, "row_count": 10},
        },
        {
            "id": "orders",
            "silver_entity": "orders",
            "primary_key": "id",
            "primary_key_status": "proposed",
            "pk_stats": {"pk_unique": True, "pk_null_rate": 0.0, "row_count": 5},
        },
    ]
    html = _keys_step_section(entities, [], is_admin=True, builder_options={})
    need_action_html = html.split("Foreign keys awaiting your decision.", 1)[1]
    assign_html = html.split("semantic-builder-fk-sections-assign", 1)[-1]
    assert "semantic-builder-fk-sections-need-action" not in html
    assert "No foreign keys proposed yet." in need_action_html
    assert "semantic-builder-fk-section-summary-inner" not in need_action_html.split("Assign foreign keys", 1)[0]
    assert assign_html.count('<details class="semantic-builder-fk-section">') == 2
    assert "Assign foreign keys" in html
    assert "semantic-builder-fk-sections-assign" in html
    assert "Primary keys (2)" in html
    assert "semantic-builder-keys-attention" in html


def test_keys_step_generate_fk_stats_button() -> None:
    from meshflow.dna.web.portal.semantics.builder_render import _keys_step_section

    entities = [
        {
            "id": "orders",
            "silver_entity": "orders",
            "primary_key": "id",
            "primary_key_status": "approved",
            "pk_stats": {"pk_unique": True, "pk_null_rate": 0.0, "row_count": 5},
        },
    ]
    attributes = [
        {
            "entity": "orders",
            "column": "customer_id",
            "role": "foreign_key",
            "fk_target_entity": "customers",
            "fk_target_column": "id",
            "status": "proposed",
            "join_stats": {"match_rate": 1.0, "orphan_rate": 0.0},
        },
        {
            "entity": "orders",
            "column": "product_id",
            "role": "foreign_key",
            "fk_target_entity": "products",
            "fk_target_column": "id",
            "status": "proposed",
        },
    ]
    html = _keys_step_section(entities, attributes, is_admin=True, builder_options={})
    assert 'data-fk-filter="all"' in html
    assert "Show All</button>" in html
    assert 'data-fk-filter="added"' in html
    assert "Show Added</button>" in html
    assert 'id="semantic-generate-fk-stats-btn">Generate stats (1)</button>' in html
    assert 'data-fk-missing-stats="1"' in html


def test_keys_step_bulk_action_buttons() -> None:
    from meshflow.dna.web.portal.semantics.builder_render import _keys_step_section

    entities = [
        {
            "id": "customers",
            "silver_entity": "customers",
            "primary_key": "id",
            "primary_key_status": "proposed",
            "pk_stats": {"pk_unique": True, "pk_null_rate": 0.0, "row_count": 10},
        },
        {
            "id": "orders",
            "silver_entity": "orders",
            "primary_key": "id",
            "primary_key_status": "proposed",
            "pk_stats": {"pk_unique": False, "pk_null_rate": 0.1, "row_count": 5},
        },
        {
            "id": "empty_table",
            "silver_entity": "empty_table",
            "primary_key": "id",
            "primary_key_status": "proposed",
            "pk_stats": {"pk_unique": False, "row_count": 0},
        },
    ]
    attributes = [
        {
            "entity": "orders",
            "column": "customer_id",
            "role": "foreign_key",
            "fk_target_entity": "customers",
            "fk_target_column": "id",
            "status": "proposed",
            "join_stats": {"match_rate": 1.0, "orphan_rate": 0.0},
        },
        {
            "entity": "orders",
            "column": "bad_id",
            "role": "foreign_key",
            "fk_target_entity": "customers",
            "fk_target_column": "id",
            "status": "proposed",
            "join_stats": {"match_rate": 0.0, "orphan_rate": 1.0},
        },
    ]
    html = _keys_step_section(entities, attributes, is_admin=True, builder_options={})
    assert 'id="semantic-approve-all-100-unique-pks"' in html
    assert 'id="semantic-reject-empty-pks"' in html
    assert 'id="semantic-approve-all-primary-keys">Approve all</button>' in html
    assert 'id="semantic-fk-match-threshold-pct"' in html
    assert 'id="semantic-approve-all-fk-matches"' in html
    assert '<option value="100" selected>100%</option>' in html
    assert '<option value="0">0%</option>' in html
    assert 'id="semantic-reject-all-100-fk-orphans"' in html
    assert 'id="semantic-approve-all-foreign-keys">Approve all</button>' in html
    assert 'data-pk-unique="1"' in html
    assert 'data-pk-unique="0"' in html
    assert 'data-pk-empty="1"' in html
    assert "Empty table" in html
    assert 'data-fk-match-pct="100"' in html
    assert 'data-fk-orphan-pct="100"' in html


def test_keys_step_primary_key_dropdown() -> None:
    from meshflow.dna.web.portal.semantics.builder_render import _keys_step_section

    entities = [
        {
            "id": "customers",
            "silver_entity": "customers",
            "primary_key": "id",
            "primary_key_status": "proposed",
            "pk_stats": {"pk_unique": True, "pk_null_rate": 0.0},
        }
    ]
    builder_options = {
        "columns_by_entity": {
            "customers": ["id", "number", "displayName"],
        }
    }
    html = _keys_step_section(
        entities,
        [],
        is_admin=True,
        builder_options=builder_options,
    )
    assert "semantic-builder-pk-select" in html
    assert 'data-entity="customers"' in html
    assert '<option value="id" selected>id</option>' in html
    assert '<option value="number">number</option>' in html
    assert "semantic-builder-keys-tabs" in html
    assert 'data-keys-tab="pk"' in html
    assert 'data-keys-tab="fk"' in html

    read_only_html = _keys_step_section(
        entities,
        [],
        is_admin=False,
        builder_options=builder_options,
    )
    assert "semantic-builder-pk-select" not in read_only_html
    assert "<code>id</code>" in read_only_html


def test_keys_step_inline_foreign_key_assign() -> None:
    from meshflow.dna.web.portal.semantics.builder_render import _keys_step_section

    entities = [
        {
            "id": "orders",
            "silver_entity": "orders",
            "primary_key": "id",
            "primary_key_status": "proposed",
            "pk_stats": {"pk_unique": True, "pk_null_rate": 0.0},
        }
    ]
    attributes = [
        {
            "entity": "orders",
            "column": "customer_id",
            "role": "foreign_key",
            "fk_target_entity": "customers",
            "fk_target_column": "id",
            "status": "proposed",
            "join_stats": {"match_rate": 1.0, "orphan_rate": 0.0},
        }
    ]
    builder_options = {
        "entities": [
            {"silver_entity": "orders", "label": "orders", "primary_key": "id"},
            {"silver_entity": "customers", "label": "customers", "primary_key": "id"},
        ],
        "columns_by_entity": {
            "orders": ["id", "customer_id", "order_date"],
            "customers": ["id", "number"],
        },
    }
    html = _keys_step_section(
        entities,
        attributes,
        is_admin=True,
        builder_options=builder_options,
    )
    assert "semantic-inline-fk-cell" in html
    assert 'data-from-entity="orders"' in html
    assert "semantic-builder-keys-tabs" in html
    assert 'data-keys-panel="fk"' in html
    assert "semantic-builder-fk-section" in html
    assert "semantic-builder-fk-section-summary-inner" in html
    assert "semantic-builder-fk-section-title" in html
    assert "semantic-builder-keys-fk-table" not in html
    assert "semantic-inline-fk-column" in html
    assert "semantic-inline-fk-to-entity" in html
    assert "semantic-inline-fk-to-column" in html
    assert "semantic-inline-fk-label" in html
    assert ">FK column</span>" in html
    assert ">Target table</span>" in html
    assert ">Target column</span>" in html
    assert 'class="semantic-builder-fk-section" open' not in html
    assert "Add FK" in html
    assert "Build keys manually" not in html
    fk_cell_start = html.index('class="semantic-inline-fk-cell semantic-inline-fk-grid"')
    fk_cell_html = html[fk_cell_start : html.index("</div>", fk_cell_start)]
    assert '<option value="order_date">order_date</option>' in fk_cell_html
    assert '<option value="customer_id">customer_id</option>' not in fk_cell_html


def test_keys_step_inline_fk_excludes_approved_columns() -> None:
    from meshflow.dna.web.portal.semantics.builder_render import _keys_step_section

    entities = [
        {
            "id": "orders",
            "silver_entity": "orders",
            "primary_key": "id",
            "primary_key_status": "approved",
            "pk_stats": {"pk_unique": True, "pk_null_rate": 0.0},
        }
    ]
    attributes = [
        {
            "entity": "orders",
            "column": "customer_id",
            "role": "foreign_key",
            "fk_target_entity": "customers",
            "fk_target_column": "id",
            "status": "approved",
            "join_stats": {"match_rate": 1.0, "orphan_rate": 0.0},
        },
        {
            "entity": "orders",
            "column": "product_id",
            "role": "foreign_key",
            "fk_target_entity": "products",
            "fk_target_column": "id",
            "status": "proposed",
            "join_stats": {"match_rate": 1.0, "orphan_rate": 0.0},
        },
    ]
    builder_options = {
        "entities": [
            {"silver_entity": "orders", "label": "orders", "primary_key": "id"},
            {"silver_entity": "customers", "label": "customers", "primary_key": "id"},
            {"silver_entity": "products", "label": "products", "primary_key": "id"},
        ],
        "columns_by_entity": {
            "orders": ["id", "customer_id", "product_id", "order_date"],
            "customers": ["id"],
            "products": ["id"],
        },
    }
    html = _keys_step_section(
        entities,
        attributes,
        is_admin=True,
        builder_options=builder_options,
    )
    fk_cell_start = html.index('class="semantic-inline-fk-cell semantic-inline-fk-grid"')
    fk_cell_html = html[fk_cell_start : html.index("</div>", fk_cell_start)]
    assert '<option value="order_date">order_date</option>' in fk_cell_html
    assert '<option value="customer_id">customer_id</option>' not in fk_cell_html
    assert '<option value="product_id">product_id</option>' not in fk_cell_html
