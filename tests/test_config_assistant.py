from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from meshflow.dna.init_client import init_client_governance
from meshflow.dna.settings import DnaSettings
from meshflow.dna.web.portal.config_assistant.bedrock_chat import (
    display_assistant_message,
    extract_proposal_payload,
    run_tool,
)
from meshflow.dna.web.portal.config_assistant.proposals import (
    bump_patch_version,
    proposal_diffs,
    unified_yaml_diff,
)
from meshflow.dna.web.portal.config_assistant.service import (
    approve_proposal,
    deny_proposal,
    get_active_proposal,
    load_base_configs,
    load_proposal_reporting,
    run_chat_turn,
)
from meshflow.dna.web.portal.preview import PREVIEW_COOKIE
from meshflow.dna.web.reporting import load_production_reporting
from meshflow.dna.workflow import load_production_pack, load_workflow_state


@pytest.fixture
def seeded_settings(tmp_path: Path) -> DnaSettings:
    settings = DnaSettings(source="dbc", data_dir=tmp_path, company="POC")
    init_client_governance(settings, company="POC")
    return settings


def test_bump_patch_version() -> None:
    assert bump_patch_version("1.0.0") == "1.0.1"
    assert bump_patch_version("2.3.9") == "2.3.10"


def test_unified_diff_and_extract_payload() -> None:
    diff = unified_yaml_diff("a: 1\n", "a: 2\n", from_label="old", to_label="new")
    assert "a: 1" in diff or "-a: 1" in diff.replace(" ", "")
    text = """Here are the changes.

```json
{
  "summary": "Rename page",
  "dna_yaml": "pack_id: poc_dna_config\\nversion: 1.0.1\\n",
  "reporting_yaml": "pack_id: poc_reporting_config\\nversion: 1.0.1\\npages: []\\nstatus: production\\n"
}
```
"""
    payload = extract_proposal_payload(text)
    assert payload is not None
    assert payload["summary"] == "Rename page"
    assert payload["dna_yaml"]
    assert payload["reporting_yaml"]


def test_extract_payload_allows_single_pack() -> None:
    text = """Short note.

```json
{"summary": "Reporting only", "reporting_yaml": "pack_id: x\\nversion: 1.0.1\\n"}
```
"""
    payload = extract_proposal_payload(text)
    assert payload is not None
    assert payload["reporting_yaml"]
    assert payload["dna_yaml"] is None


def test_display_assistant_message_strips_json() -> None:
    text = (
        "Got it — updated the reporting labels.\n\n"
        "```json\n"
        '{"summary": "Updated labels", "reporting_yaml": "pack_id: x\\n"}\n'
        "```"
    )
    shown = display_assistant_message(text, summary="Updated labels")
    assert "```" not in shown
    assert "reporting_yaml" not in shown
    assert "Got it" in shown


def test_tool_guard_rejects_bucket_arg(seeded_settings: DnaSettings) -> None:
    with pytest.raises(ValueError, match="bucket"):
        run_tool(seeded_settings, "list_governance_keys", {"bucket": "other-bucket"})


def test_tool_guard_rejects_s3_uri(seeded_settings: DnaSettings) -> None:
    with pytest.raises(ValueError, match="Cross-bucket|absolute"):
        run_tool(seeded_settings, "list_governance_keys", {"prefix": "s3://other-bucket/governance"})


def test_chat_approve_reporting_only_leaves_dna_pin(
    seeded_settings: DnaSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MESHFLOW_CONFIG_ASSISTANT_MOCK", "1")
    view = run_chat_turn(
        seeded_settings,
        user_message="Add a note to reporting descriptions",
        username="admin",
    )
    assert view["meta"]["status"] == "open"
    assert view["proposal_id"]
    assert view["reporting_pending"]
    assert not view["dna_pending"]
    assert "```" not in str((view["conversation"]["messages"][-1]).get("content") or "")

    result = approve_proposal(
        seeded_settings,
        str(view["proposal_id"]),
        username="admin",
        target="reporting",
        next_version=str(view["meta"]["next_reporting_version"]),
    )
    assert result["status"] == "approved"
    assert result["target"] == "reporting"
    state = load_workflow_state(seeded_settings, "poc_dna_config")
    assert state["active_version"] == "1.0.0"
    assert state["active_reporting_version"] == "1.0.1"
    assert load_production_pack(seeded_settings).version == "1.0.0"
    assert load_production_reporting(seeded_settings)["version"] == "1.0.1"
    assert (
        seeded_settings.data_dir
        / "governance"
        / "poc_dna_config"
        / "v1.0.1"
        / "poc_reporting_config.yaml"
    ).is_file()


def test_chat_approve_dna_independently(
    seeded_settings: DnaSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MESHFLOW_CONFIG_ASSISTANT_MOCK", "1")
    view = run_chat_turn(
        seeded_settings,
        user_message="Update both dna and reporting notes",
        username="admin",
    )
    assert view["dna_pending"]
    assert view["reporting_pending"]

    dna_result = approve_proposal(
        seeded_settings,
        str(view["proposal_id"]),
        username="admin",
        target="dna",
    )
    assert dna_result["status"] == "open"
    assert dna_result["fully_resolved"] is False
    state = load_workflow_state(seeded_settings, "poc_dna_config")
    assert state["active_version"] == "1.0.1"
    assert state.get("active_reporting_version") in {None, "1.0.0"} or "active_reporting_version" not in state

    reporting_result = approve_proposal(
        seeded_settings,
        str(view["proposal_id"]),
        username="admin",
        target="reporting",
    )
    assert reporting_result["status"] == "approved"
    assert reporting_result["fully_resolved"] is True
    state = load_workflow_state(seeded_settings, "poc_dna_config")
    assert state["active_version"] == "1.0.1"
    assert state["active_reporting_version"] == "1.0.1"


def test_deny_leaves_pin_unchanged(seeded_settings: DnaSettings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MESHFLOW_CONFIG_ASSISTANT_MOCK", "1")
    before = load_workflow_state(seeded_settings, "poc_dna_config")["active_version"]
    view = run_chat_turn(
        seeded_settings,
        user_message="Try a change",
        username="admin",
    )
    deny_proposal(seeded_settings, str(view["proposal_id"]), username="admin")
    after = load_workflow_state(seeded_settings, "poc_dna_config")["active_version"]
    assert after == before
    assert get_active_proposal(seeded_settings) is None


def test_preview_loader_reads_proposal_reporting(
    seeded_settings: DnaSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MESHFLOW_CONFIG_ASSISTANT_MOCK", "1")
    view = run_chat_turn(
        seeded_settings,
        user_message="Previewable change",
        username="admin",
    )
    reporting = load_proposal_reporting(seeded_settings, str(view["proposal_id"]))
    assert reporting["pack_id"] == "poc_reporting_config"
    assert "assistant note" in str(reporting.get("description") or "")


def test_proposal_diffs_smoke(seeded_settings: DnaSettings) -> None:
    base = load_base_configs(seeded_settings)
    proposed_reporting = yaml.safe_load(base["reporting_yaml"])
    proposed_reporting["description"] = "Changed"
    diffs = proposal_diffs(
        base_dna_yaml=base["dna_yaml"],
        base_reporting_yaml=base["reporting_yaml"],
        proposed_dna_yaml=base["dna_yaml"],
        proposed_reporting_yaml=yaml.safe_dump(proposed_reporting, sort_keys=False),
        base_version="1.0.0",
        next_version="1.0.1",
    )
    assert "Changed" in diffs["reporting"]
    assert diffs["dna"] == ""


def test_admin_config_route_forbidden_for_member(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from werkzeug.test import Client

    from meshflow.dna.web.app import create_app
    from meshflow.project_config import load_project_config

    monkeypatch.setenv("HIVEFLOW_PORTAL_USERNAME", "poc")
    monkeypatch.setenv("HIVEFLOW_PORTAL_PASSWORD", "changeme")
    monkeypatch.setenv("HIVEFLOW_PORTAL_CLIENT_ID", "poc")
    monkeypatch.setattr(
        "meshflow.dna.web.app.require_portal_admin",
        lambda *args, **kwargs: False,
    )

    settings = DnaSettings(source="dbc", data_dir=tmp_path, company="POC")
    init_client_governance(settings, company="POC")
    config = load_project_config()
    try:
        from meshflow.project_config import get_platform_environment_config

        env_config = get_platform_environment_config("dev")
    except KeyError:
        env_config = config["companies"]["POC"]["environments"]["dev"]

    client = Client(
        create_app(
            settings,
            company="POC",
            environment="dev",
            env_config=env_config,
            ui_mode="reporting",
        )
    )
    client.post("/portal/login", data={"username": "poc", "password": "changeme"})
    response = client.get("/portal/governance/config")
    assert response.status_code == 403


def test_preview_cookie_name() -> None:
    assert PREVIEW_COOKIE == "meshflow_config_preview"


def test_enqueue_and_complete_chat(seeded_settings: DnaSettings, monkeypatch: pytest.MonkeyPatch) -> None:
    from unittest.mock import MagicMock

    from meshflow.dna.web.portal.config_assistant.service import (
        complete_chat_turn,
        enqueue_chat_turn,
    )

    monkeypatch.setenv("MESHFLOW_CONFIG_ASSISTANT_MOCK", "1")
    monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "test-reporting-fn")

    mock_lambda = MagicMock()
    mock_lambda.invoke.return_value = {"StatusCode": 202}
    monkeypatch.setattr(
        "boto3.client",
        lambda service, **_kwargs: mock_lambda if service == "lambda" else MagicMock(),
    )

    queued = enqueue_chat_turn(
        seeded_settings,
        user_message="Add a note to descriptions",
        username="admin",
    )
    assert queued["meta"]["status"] == "running"
    mock_lambda.invoke.assert_called_once()

    done = complete_chat_turn(
        seeded_settings,
        proposal_id=str(queued["proposal_id"]),
        username="admin",
    )
    assert done["meta"]["status"] == "open"
    assert done["has_changes"]
    assert done["reporting_pending"]
    assert not done["dna_pending"]
