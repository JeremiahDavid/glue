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
    bump_major_version,
    bump_minor_version,
    bump_patch_version,
    classify_manual_version_bump,
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
    assert bump_minor_version("1.0.5") == "1.1.0"
    assert bump_minor_version("2.3.9") == "2.4.0"
    assert bump_major_version("1.2.3") == "2.0.0"
    assert bump_major_version("2.3.9") == "3.0.0"


def test_classify_manual_version_bump() -> None:
    patch = classify_manual_version_bump("1.0.0", "1.0.1")
    assert patch["kind"] == "patch"
    assert not patch["warning"]
    assert patch["suggested_major"] == "2.0.0"

    minor = classify_manual_version_bump("1.0.5", "1.1.0")
    assert minor["kind"] == "minor"
    assert "resets to 0" in minor["warning"]
    assert "1.1.x" in minor["warning"]

    major = classify_manual_version_bump("1.2.3", "2.0.0")
    assert major["kind"] == "major"

    skipped = classify_manual_version_bump("1.0.0", "1.0.5")
    assert skipped["kind"] == "invalid"
    assert "1.0.1" in skipped["error"]
    assert "2.0.0" in skipped["error"]

    same = classify_manual_version_bump("1.0.1", "1.0.1")
    assert same["kind"] == "invalid"


def test_unified_diff_and_extract_payload() -> None:
    diff = unified_yaml_diff(
        "keep: 1\na: 1\n",
        "keep: 1\na: 2\n",
        from_label="old",
        to_label="new",
    )
    assert "-a: 1" in diff
    assert "+a: 2" in diff
    # n=0 omits unchanged context rows from the unified diff body.
    changed_body = "\n".join(
        line
        for line in diff.splitlines()
        if line[:1] in {"+", "-"} and not line.startswith(("+++", "---"))
    )
    assert "keep: 1" not in changed_body
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
    assert state["active_version"] == "1.1.0"
    assert state["active_reporting_version"] == "1.1.1"
    assert load_production_pack(seeded_settings).version == "1.1.0"
    assert load_production_reporting(seeded_settings)["version"] == "1.1.1"
    assert (
        seeded_settings.data_dir
        / "governance"
        / "poc_dna_config"
        / "v1.1.1"
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
    assert state["active_version"] == "1.1.1"
    assert state.get("active_reporting_version") in {None, "1.1.0"} or "active_reporting_version" not in state

    reporting_result = approve_proposal(
        seeded_settings,
        str(view["proposal_id"]),
        username="admin",
        target="reporting",
    )
    assert reporting_result["status"] == "approved"
    assert reporting_result["fully_resolved"] is True
    state = load_workflow_state(seeded_settings, "poc_dna_config")
    assert state["active_version"] == "1.1.1"
    assert state["active_reporting_version"] == "1.1.1"


def test_approve_rejects_non_adjacent_version(
    seeded_settings: DnaSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MESHFLOW_CONFIG_ASSISTANT_MOCK", "1")
    view = run_chat_turn(
        seeded_settings,
        user_message="Add a note to reporting descriptions",
        username="admin",
    )
    with pytest.raises(ValueError, match="next patch"):
        approve_proposal(
            seeded_settings,
            str(view["proposal_id"]),
            username="admin",
            target="reporting",
            next_version="9.9.9",
        )


def test_approve_allows_minor_bump(
    seeded_settings: DnaSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MESHFLOW_CONFIG_ASSISTANT_MOCK", "1")
    view = run_chat_turn(
        seeded_settings,
        user_message="Add a note to reporting descriptions",
        username="admin",
    )
    base = str(view["meta"]["reporting_base_version"])
    minor = bump_minor_version(base)
    result = approve_proposal(
        seeded_settings,
        str(view["proposal_id"]),
        username="admin",
        target="reporting",
        next_version=minor,
    )
    assert result["status"] == "approved"
    state = load_workflow_state(seeded_settings, "poc_dna_config")
    assert state["active_reporting_version"] == minor


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


def test_deny_one_pack_keeps_other_pending(
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
    result = deny_proposal(
        seeded_settings,
        str(view["proposal_id"]),
        username="admin",
        target="dna",
    )
    assert result["fully_resolved"] is False
    assert result["dna_status"] == "denied"
    assert result["reporting_status"] == "pending"
    active = get_active_proposal(seeded_settings)
    assert active is not None
    assert active["meta"]["status"] == "open"


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


def test_render_assistant_diff_html_highlights_changed_rows_only() -> None:
    from meshflow.dna.web.portal.views import render_assistant_diff_html

    diff = """--- dna@v1.0.0
+++ dna@v1.0.1
@@ -1,3 +1,3 @@
 pack_id: poc_dna_config
-description: old
+description: new
 status: production
"""
    html = render_assistant_diff_html(diff, empty_label="(no DNA changes)")
    assert "assistant-diff-line del" in html
    assert "assistant-diff-line add" in html
    assert "-description: old" in html
    assert "+description: new" in html
    assert "pack_id: poc_dna_config" not in html
    assert "status: production" not in html
    assert "@@" not in html
    assert "---" not in html

    empty = render_assistant_diff_html("", empty_label="(no DNA changes)")
    assert "(no DNA changes)" in empty
    assert "assistant-diff-empty" in empty


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
    response = client.get("/portal/governance/config", follow_redirects=False)
    assert response.status_code == 302
    assert "update=assist" in response.headers["Location"]

    response = client.post(
        "/portal/governance",
        data={"action": "chat", "message": "Rename a page"},
        follow_redirects=False,
    )
    assert response.status_code == 403


def test_chat_post_redirects_to_get(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """PRG: chat POST must redirect so auto-refresh cannot resubmit the form."""
    from unittest.mock import MagicMock

    from werkzeug.test import Client

    from meshflow.dna.web.app import create_app
    from meshflow.project_config import load_project_config

    monkeypatch.setenv("HIVEFLOW_PORTAL_USERNAME", "poc")
    monkeypatch.setenv("HIVEFLOW_PORTAL_PASSWORD", "changeme")
    monkeypatch.setenv("HIVEFLOW_PORTAL_CLIENT_ID", "poc")
    monkeypatch.setenv("MESHFLOW_CONFIG_ASSISTANT_MOCK", "1")
    monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "test-reporting-fn")
    monkeypatch.setattr(
        "meshflow.dna.web.app.require_portal_admin",
        lambda *args, **kwargs: True,
    )
    mock_lambda = MagicMock()
    mock_lambda.invoke.return_value = {"StatusCode": 202}
    monkeypatch.setattr(
        "boto3.client",
        lambda service, **_kwargs: mock_lambda if service == "lambda" else MagicMock(),
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

    response = client.post(
        "/portal/governance",
        data={"action": "chat", "message": "Rename a page"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    location = response.headers["Location"]
    assert "update=assist" in location
    assert "msg=" in location

    follow = client.get("/portal/governance?update=assist", follow_redirects=False)
    assert follow.status_code == 200
    assert b'id="config-assist-live"' in follow.data
    assert b"data-poll-url=" in follow.data
    assert b"data-running=\"1\"" in follow.data
    assert b"assistant-thinking-dots" in follow.data
    assert b"window.location.reload" not in follow.data
    assert b"window.location.replace" not in follow.data
    assert b"Assistant is working" in follow.data

    poll = client.get("/api/config-assistant")
    assert poll.status_code == 200
    payload = poll.get_json()
    assert payload["running"] is True
    assert "Thinking" in payload["html"]
    assert "assistant-thinking-dots" in payload["html"]


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
