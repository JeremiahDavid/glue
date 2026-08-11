"""Tests for source-docs scrape → relationships Lambda enqueue."""

from __future__ import annotations

import json
from typing import Any

from meshflow.bc import source_docs_handler


def test_enqueue_relationships_job_invokes_async(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    class FakeLambda:
        def invoke(self, **kwargs):  # type: ignore[no-untyped-def]
            captured.update(kwargs)
            return {"StatusCode": 202}

    monkeypatch.setenv("MESHFLOW_SOURCE_DOCS_RELATIONSHIPS_FUNCTION", "platform-dev-bc-source-docs-relationships")
    monkeypatch.setattr("boto3.client", lambda service: FakeLambda() if service == "lambda" else None)

    follow_on = source_docs_handler._enqueue_relationships_job(
        {
            "status": "published",
            "source": "dbc",
            "artifact": {"bucket": "hiveflowai-source-documentation", "key": "dbc/entity_properties.yaml"},
        },
        {},
    )
    assert follow_on is not None
    assert follow_on["status_code"] == 202
    assert captured["FunctionName"] == "platform-dev-bc-source-docs-relationships"
    assert captured["InvocationType"] == "Event"
    payload = json.loads(captured["Payload"].decode("utf-8"))
    assert payload["properties_object_key"] == "dbc/entity_properties.yaml"


def test_enqueue_relationships_job_skips_dry_run_status(monkeypatch) -> None:
    monkeypatch.setenv("MESHFLOW_SOURCE_DOCS_RELATIONSHIPS_FUNCTION", "platform-dev-bc-source-docs-relationships")
    assert (
        source_docs_handler._enqueue_relationships_job({"status": "dry_run", "source": "dbc"}, {}) is None
    )


def test_enqueue_relationships_job_honors_skip_flag(monkeypatch) -> None:
    monkeypatch.setenv("MESHFLOW_SOURCE_DOCS_RELATIONSHIPS_FUNCTION", "platform-dev-bc-source-docs-relationships")
    follow_on = source_docs_handler._enqueue_relationships_job(
        {"status": "published", "source": "dbc"},
        {"skip_relationships": True},
    )
    assert follow_on == {"skipped": True, "reason": "skip_relationships"}


def test_enqueue_tags_job_invokes_async(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    class FakeLambda:
        def invoke(self, **kwargs):  # type: ignore[no-untyped-def]
            captured.update(kwargs)
            return {"StatusCode": 202}

    monkeypatch.setenv("MESHFLOW_SOURCE_DOCS_TAGS_FUNCTION", "platform-dev-bc-source-docs-tags")
    monkeypatch.setattr("boto3.client", lambda service: FakeLambda() if service == "lambda" else None)

    follow_on = source_docs_handler._enqueue_tags_job(
        {
            "status": "published",
            "source": "dbc",
            "artifact": {"bucket": "hiveflowai-source-documentation", "key": "dbc/entity_properties.yaml"},
        },
        {},
    )
    assert follow_on is not None
    assert follow_on["function_name"] == "platform-dev-bc-source-docs-tags"
    assert captured["InvocationType"] == "Event"
