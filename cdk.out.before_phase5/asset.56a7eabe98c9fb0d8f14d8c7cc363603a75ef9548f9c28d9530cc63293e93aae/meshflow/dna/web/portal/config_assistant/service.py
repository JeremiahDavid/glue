"""Orchestrate config assistant chat, approve/deny, and base pack loading."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from meshflow.dna.governance import save_governance_version
from meshflow.dna.schema import load_definition_pack_yaml
from meshflow.dna.settings import DnaSettings
from meshflow.dna.web.portal.config_assistant.bedrock_chat import (
    display_assistant_message,
    extract_proposal_payload,
    invoke_assistant,
    system_prompt,
)
from meshflow.dna.web.portal.config_assistant.bedrock_usage import (
    assert_within_budget,
    record_usage,
)
from meshflow.dna.web.portal.config_assistant.gold_bindings import build_reporting_binding_catalog
from meshflow.dna.web.portal.config_assistant.proposals import (
    bump_patch_version,
    classify_manual_version_bump,
    dump_yaml,
    load_open_proposal_id,
    load_proposal,
    new_proposal_id,
    proposal_diffs,
    save_proposal,
    yaml_content_changed,
)
from meshflow.dna.reporting import (
    load_production_reporting,
    load_reporting_pack_yaml,
    normalize_reporting_identity,
    save_reporting_pack,
)
from meshflow.dna.workflow import load_production_pack, load_workflow_state, save_workflow_state

ApproveTarget = Literal["dna", "reporting"]


def _resolve_client_id(client_id: str = "") -> str:
    import os

    return (client_id or os.getenv("MESHFLOW_PORTAL_CLIENT_ID", "")).strip().lower()


def load_base_configs(settings: DnaSettings) -> dict[str, Any]:
    dna_pack = load_production_pack(settings)
    reporting = load_production_reporting(settings)
    state = load_workflow_state(settings, settings.dna_config_id)
    dna_version = str(state.get("active_version") or dna_pack.version)
    reporting_version = str(
        state.get("active_reporting_version") or reporting.get("version") or dna_version
    )
    return {
        "dna_pack": dna_pack,
        "reporting": reporting,
        "dna_yaml": dump_yaml(dna_pack.to_dict()),
        "reporting_yaml": dump_yaml(reporting),
        "binding_catalog": build_reporting_binding_catalog(settings),
        "base_version": dna_version,
        "dna_version": dna_version,
        "reporting_version": reporting_version,
        "next_version": bump_patch_version(dna_version),
        "next_dna_version": bump_patch_version(dna_version),
        "next_reporting_version": bump_patch_version(reporting_version),
    }


def get_active_proposal(settings: DnaSettings) -> dict[str, Any] | None:
    proposal_id = load_open_proposal_id(settings)
    if not proposal_id:
        return None
    return load_proposal(settings, proposal_id)


def _pack_status(meta: dict[str, Any], *, changed: bool, key: str) -> str:
    raw = str(meta.get(key) or "").strip().lower()
    if raw in {"pending", "approved", "skipped", "denied"}:
        return raw
    return "pending" if changed else "skipped"


def proposal_view(settings: DnaSettings, proposal: dict[str, Any], base: dict[str, Any]) -> dict[str, Any]:
    meta = proposal["meta"]
    dna_base_version = str(meta.get("dna_base_version") or base["dna_version"])
    reporting_base_version = str(meta.get("reporting_base_version") or base["reporting_version"])
    next_dna_version = str(meta.get("next_dna_version") or base["next_dna_version"])
    next_reporting_version = str(
        meta.get("next_reporting_version") or base["next_reporting_version"]
    )
    dna_changed = yaml_content_changed(base["dna_yaml"], proposal["dna_yaml"])
    reporting_changed = yaml_content_changed(base["reporting_yaml"], proposal["reporting_yaml"])
    diffs = proposal_diffs(
        base_dna_yaml=base["dna_yaml"],
        base_reporting_yaml=base["reporting_yaml"],
        proposed_dna_yaml=proposal["dna_yaml"],
        proposed_reporting_yaml=proposal["reporting_yaml"],
        base_version=str(meta.get("base_version") or base["base_version"]),
        next_version=str(meta.get("next_version") or base["next_version"]),
        dna_base_version=dna_base_version,
        dna_next_version=next_dna_version,
        reporting_base_version=reporting_base_version,
        reporting_next_version=next_reporting_version,
    )
    dna_status = _pack_status(meta, changed=dna_changed, key="dna_status")
    reporting_status = _pack_status(meta, changed=reporting_changed, key="reporting_status")
    return {
        "proposal_id": meta.get("proposal_id"),
        "meta": {
            **meta,
            "dna_base_version": dna_base_version,
            "reporting_base_version": reporting_base_version,
            "next_dna_version": next_dna_version,
            "next_reporting_version": next_reporting_version,
            "dna_status": dna_status,
            "reporting_status": reporting_status,
            "dna_changed": dna_changed,
            "reporting_changed": reporting_changed,
        },
        "base_dna_yaml": base["dna_yaml"],
        "base_reporting_yaml": base["reporting_yaml"],
        "dna_yaml": proposal["dna_yaml"],
        "reporting_yaml": proposal["reporting_yaml"],
        "conversation": proposal.get("conversation") or {"messages": []},
        "diffs": diffs,
        "has_changes": bool(diffs["dna"].strip() or diffs["reporting"].strip()),
        "dna_pending": dna_changed and dna_status == "pending",
        "reporting_pending": reporting_changed and reporting_status == "pending",
    }


def _proposal_workspace(
    settings: DnaSettings,
    *,
    base: dict[str, Any],
) -> tuple[str, list[dict[str, Any]], str, str, str, str, dict[str, Any] | None]:
    existing = get_active_proposal(settings)
    if existing and existing["meta"].get("status") in {"open", "running"}:
        proposal_id = str(existing["meta"]["proposal_id"])
        conversation = existing.get("conversation") or {"messages": []}
        messages = list(conversation.get("messages") or [])
        next_version = str(existing["meta"].get("next_version") or base["next_version"])
        base_version = str(existing["meta"].get("base_version") or base["base_version"])
        current_dna = existing["dna_yaml"]
        current_reporting = existing["reporting_yaml"]
        return (
            proposal_id,
            messages,
            next_version,
            base_version,
            current_dna,
            current_reporting,
            existing,
        )
    return (
        new_proposal_id(),
        [],
        base["next_version"],
        base["base_version"],
        base["dna_yaml"],
        base["reporting_yaml"],
        None,
    )


def _prepare_reporting_proposal_yaml(
    settings: DnaSettings,
    *,
    reporting_yaml_text: str,
    next_reporting_version: str,
) -> str:
    """Validate assistant-proposed reporting YAML and return canonical proposal text."""
    reporting = load_reporting_pack_yaml(reporting_yaml_text)
    reporting = normalize_reporting_identity(
        settings,
        reporting,
        version=next_reporting_version,
        status="production",
    )
    return dump_yaml(reporting)


def _apply_assistant_turn(
    settings: DnaSettings,
    *,
    base: dict[str, Any],
    proposal_id: str,
    messages: list[dict[str, Any]],
    user_message: str,
    next_version: str,
    base_version: str,
    current_dna: str,
    current_reporting: str,
    username: str,
    prior_meta: dict[str, Any] | None = None,
    invoke_fn=None,
    client_id: str = "",
) -> dict[str, Any]:
    prior = prior_meta or {}
    next_dna_version = str(prior.get("next_dna_version") or base["next_dna_version"])
    next_reporting_version = str(
        prior.get("next_reporting_version") or base["next_reporting_version"]
    )
    dna_base_version = str(prior.get("dna_base_version") or base["dna_version"])
    reporting_base_version = str(
        prior.get("reporting_base_version") or base["reporting_version"]
    )
    system = system_prompt(
        settings,
        base_version=base_version,
        next_version=next_version,
        dna_version=dna_base_version,
        reporting_version=reporting_base_version,
        next_dna_version=next_dna_version,
        next_reporting_version=next_reporting_version,
    )
    # Always preload YAML so Bedrock can answer in one round (API Gateway ~29s limit).
    context_prefix = (
        f"Current DNA YAML:\n```yaml\n{current_dna}\n```\n\n"
        f"Current reporting YAML:\n```yaml\n{current_reporting}\n```\n\n"
        f"User request:\n"
    )
    assistant_turn = invoke_assistant(
        settings,
        system=system,
        history=[{"role": m["role"], "content": m["content"]} for m in messages if isinstance(m, dict)],
        user_message=context_prefix + user_message,
        invoke_fn=invoke_fn,
    )
    assistant_text = assistant_turn.text
    resolved_client_id = _resolve_client_id(client_id)
    if resolved_client_id and (
        assistant_turn.input_tokens > 0 or assistant_turn.output_tokens > 0
    ):
        record_usage(
            settings,
            input_tokens=assistant_turn.input_tokens,
            output_tokens=assistant_turn.output_tokens,
            client_id=resolved_client_id,
        )

    extracted = extract_proposal_payload(assistant_text)
    summary = str((extracted or {}).get("summary") or prior.get("summary") or "")
    display = display_assistant_message(assistant_text, summary=summary)
    proposal_rejections: list[str] = []

    messages = list(messages)
    messages.append({"role": "user", "content": user_message})
    messages.append({"role": "assistant", "content": display})

    dna_yaml = current_dna
    reporting_yaml = current_reporting
    if extracted:
        if extracted.get("dna_yaml"):
            try:
                dna_pack = load_definition_pack_yaml(extracted["dna_yaml"])
                dna_pack.pack_id = settings.dna_config_id
                dna_pack.version = next_dna_version
                candidate = dump_yaml(dna_pack.to_dict())
                if yaml_content_changed(base["dna_yaml"], candidate):
                    dna_yaml = candidate
            except ValueError as exc:
                proposal_rejections.append(f"DNA changes were not proposed: {exc}")
        if extracted.get("reporting_yaml"):
            try:
                candidate = _prepare_reporting_proposal_yaml(
                    settings,
                    reporting_yaml_text=extracted["reporting_yaml"],
                    next_reporting_version=next_reporting_version,
                )
                if yaml_content_changed(base["reporting_yaml"], candidate):
                    reporting_yaml = candidate
            except ValueError as exc:
                proposal_rejections.append(f"Reporting changes were not proposed: {exc}")

    if proposal_rejections:
        rejection_text = " ".join(proposal_rejections)
        display = f"{display}\n\n{rejection_text}" if display else rejection_text
        messages[-1] = {"role": "assistant", "content": display}

    dna_changed = yaml_content_changed(base["dna_yaml"], dna_yaml)
    reporting_changed = yaml_content_changed(base["reporting_yaml"], reporting_yaml)
    dna_status = "pending" if dna_changed else "skipped"
    reporting_status = "pending" if reporting_changed else "skipped"
    # Preserve prior approvals if the assistant did not touch that pack again.
    if prior.get("dna_status") == "approved" and not dna_changed:
        dna_status = "approved"
        dna_yaml = current_dna
    if prior.get("reporting_status") == "approved" and not reporting_changed:
        reporting_status = "approved"
        reporting_yaml = current_reporting

    meta = {
        "proposal_id": proposal_id,
        "status": "open",
        "base_version": base_version,
        "next_version": next_version,
        "dna_base_version": dna_base_version,
        "reporting_base_version": reporting_base_version,
        "next_dna_version": next_dna_version,
        "next_reporting_version": next_reporting_version,
        "dna_status": dna_status,
        "reporting_status": reporting_status,
        "created_by": username,
        "summary": summary or str(prior.get("summary") or ""),
    }
    meta.pop("pending_user_message", None)
    meta.pop("last_requeue_at", None)
    meta.pop("running_started_at", None)
    save_proposal(
        settings,
        proposal_id=proposal_id,
        meta=meta,
        dna_yaml=dna_yaml,
        reporting_yaml=reporting_yaml,
        conversation={"messages": messages},
    )
    proposal = load_proposal(settings, proposal_id)
    assert proposal is not None
    return proposal_view(settings, proposal, base)


def run_chat_turn(
    settings: DnaSettings,
    *,
    user_message: str,
    username: str,
    invoke_fn=None,
    client_id: str = "",
    monthly_budget_usd: float | None = None,
) -> dict[str, Any]:
    resolved_client_id = _resolve_client_id(client_id)
    if resolved_client_id:
        assert_within_budget(
            settings,
            client_id=resolved_client_id,
            monthly_budget_usd=monthly_budget_usd,
        )
    base = load_base_configs(settings)
    (
        proposal_id,
        messages,
        next_version,
        base_version,
        current_dna,
        current_reporting,
        existing,
    ) = _proposal_workspace(settings, base=base)
    if existing and existing["meta"].get("status") == "running":
        raise RuntimeError("Assistant is still working on the previous message. Refresh in a moment.")

    return _apply_assistant_turn(
        settings,
        base=base,
        proposal_id=proposal_id,
        messages=messages,
        user_message=user_message,
        next_version=next_version,
        base_version=base_version,
        current_dna=current_dna,
        current_reporting=current_reporting,
        username=username,
        prior_meta=(existing or {}).get("meta") or {},
        invoke_fn=invoke_fn,
        client_id=resolved_client_id,
    )


def enqueue_chat_turn(
    settings: DnaSettings,
    *,
    user_message: str,
    username: str,
    client_id: str = "",
    monthly_budget_usd: float | None = None,
) -> dict[str, Any]:
    """Persist the user turn as running and finish Bedrock work in a background Lambda invoke."""
    resolved_client_id = _resolve_client_id(client_id)
    if resolved_client_id:
        assert_within_budget(
            settings,
            client_id=resolved_client_id,
            monthly_budget_usd=monthly_budget_usd,
        )
    base = load_base_configs(settings)
    (
        proposal_id,
        messages,
        next_version,
        base_version,
        current_dna,
        current_reporting,
        existing,
    ) = _proposal_workspace(settings, base=base)
    if existing and existing["meta"].get("status") == "running":
        raise RuntimeError("Assistant is still working on the previous message. Refresh in a moment.")

    prior = (existing or {}).get("meta") or {}
    messages = list(messages)
    messages.append({"role": "user", "content": user_message})
    meta = {
        "proposal_id": proposal_id,
        "status": "running",
        "base_version": base_version,
        "next_version": next_version,
        "dna_base_version": str(prior.get("dna_base_version") or base["dna_version"]),
        "reporting_base_version": str(
            prior.get("reporting_base_version") or base["reporting_version"]
        ),
        "next_dna_version": str(prior.get("next_dna_version") or base["next_dna_version"]),
        "next_reporting_version": str(
            prior.get("next_reporting_version") or base["next_reporting_version"]
        ),
        "dna_status": str(prior.get("dna_status") or "skipped"),
        "reporting_status": str(prior.get("reporting_status") or "skipped"),
        "created_by": username,
        "summary": str(prior.get("summary") or ""),
        "pending_user_message": user_message,
        "running_started_at": datetime.now(UTC).isoformat(),
    }
    # Keep prior YAML until the assistant finishes.
    save_proposal(
        settings,
        proposal_id=proposal_id,
        meta=meta,
        dna_yaml=current_dna,
        reporting_yaml=current_reporting,
        conversation={"messages": messages},
    )

    try:
        _invoke_chat_worker(
            proposal_id=proposal_id,
            username=username,
            company=settings.company,
        )
    except Exception as exc:  # noqa: BLE001 — roll back so the UI is not stuck forever
        fail_messages = list(messages)
        fail_messages.append(
            {
                "role": "assistant",
                "content": f"Sorry — could not start the background assistant: {exc}",
            }
        )
        meta = dict(meta)
        meta["status"] = "open"
        meta.pop("pending_user_message", None)
        save_proposal(
            settings,
            proposal_id=proposal_id,
            meta=meta,
            dna_yaml=current_dna,
            reporting_yaml=current_reporting,
            conversation={"messages": fail_messages},
        )
        raise

    proposal = load_proposal(settings, proposal_id)
    assert proposal is not None
    return proposal_view(settings, proposal, base)


def _invoke_chat_worker(*, proposal_id: str, username: str, company: str) -> None:
    import json
    import os

    import boto3

    function_name = os.environ.get("AWS_LAMBDA_FUNCTION_NAME", "").strip()
    if not function_name:
        raise RuntimeError("Async chat requires AWS_LAMBDA_FUNCTION_NAME")

    region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-2"
    client = boto3.client("lambda", region_name=region)
    response = client.invoke(
        FunctionName=function_name,
        InvocationType="Event",
        Payload=json.dumps(
            {
                "meshflow_task": "config_assistant_chat",
                "proposal_id": proposal_id,
                "username": username,
                "company": company,
                "environment": os.environ.get("MESHFLOW_ENVIRONMENT", ""),
            }
        ).encode("utf-8"),
    )
    status = int(response.get("StatusCode") or 0)
    # Event invoke should return 202 Accepted.
    if status not in {202, 200}:
        raise RuntimeError(f"Background invoke returned status {status}")
    print(
        json.dumps(
            {
                "msg": "config_assistant_chat_enqueued",
                "proposal_id": proposal_id,
                "status_code": status,
            }
        )
    )


STALE_RUNNING_SECONDS = 180
REQUEUE_AFTER_SECONDS = 20


def _proposal_age_seconds(meta: dict[str, Any]) -> float:
    raw = str(meta.get("updated_at") or meta.get("created_at") or "").strip()
    if not raw:
        return 0.0
    try:
        stamped = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    if stamped.tzinfo is None:
        stamped = stamped.replace(tzinfo=UTC)
    return max(0.0, (datetime.now(UTC) - stamped).total_seconds())


def cancel_running_proposal(
    settings: DnaSettings,
    *,
    proposal_id: str,
    username: str,
) -> dict[str, Any]:
    """Clear a stuck running proposal so the admin can retry."""
    base = load_base_configs(settings)
    proposal = load_proposal(settings, proposal_id)
    if not proposal:
        raise FileNotFoundError(f"Proposal {proposal_id!r} not found")
    meta = dict(proposal["meta"])
    if meta.get("status") != "running":
        return proposal_view(settings, proposal, base)

    conversation = proposal.get("conversation") or {"messages": []}
    messages = list(conversation.get("messages") or [])
    pending = str(meta.get("pending_user_message") or "").strip()
    if pending and not (messages and messages[-1].get("role") == "user"):
        messages.append({"role": "user", "content": pending})
    messages.append(
        {
            "role": "assistant",
            "content": f"Cancelled by {username}. You can send the request again.",
        }
    )
    meta["status"] = "open"
    meta.pop("pending_user_message", None)
    meta.pop("last_requeue_at", None)
    meta.pop("running_started_at", None)
    save_proposal(
        settings,
        proposal_id=proposal_id,
        meta=meta,
        dna_yaml=proposal["dna_yaml"],
        reporting_yaml=proposal["reporting_yaml"],
        conversation={"messages": messages},
    )
    updated = load_proposal(settings, proposal_id)
    assert updated is not None
    return proposal_view(settings, updated, base)


def ensure_running_chat_progress(settings: DnaSettings) -> dict[str, Any] | None:
    """Re-queue or fail stuck running proposals (Event self-invoke can be dropped)."""
    proposal = get_active_proposal(settings)
    if not proposal or proposal["meta"].get("status") != "running":
        return proposal

    meta = dict(proposal["meta"])
    started = str(meta.get("running_started_at") or meta.get("updated_at") or "")
    age = _proposal_age_seconds({"updated_at": started})
    proposal_id = str(meta.get("proposal_id") or "")
    username = str(meta.get("created_by") or "admin")

    if age >= STALE_RUNNING_SECONDS:
        cancelled = cancel_running_proposal(
            settings,
            proposal_id=proposal_id,
            username="system",
        )
        # Rewrite the canned cancel note for timeout clarity.
        conversation = cancelled.get("conversation") or {"messages": []}
        messages = list(conversation.get("messages") or [])
        if messages and messages[-1].get("role") == "assistant":
            messages[-1] = {
                "role": "assistant",
                "content": (
                    "Timed out waiting for the background assistant. "
                    "Please send your request again."
                ),
            }
            save_proposal(
                settings,
                proposal_id=proposal_id,
                meta=cancelled["meta"],
                dna_yaml=cancelled["dna_yaml"],
                reporting_yaml=cancelled["reporting_yaml"],
                conversation={"messages": messages},
            )
            return load_proposal(settings, proposal_id)
        return get_active_proposal(settings)

    last_requeue = str(meta.get("last_requeue_at") or "").strip()
    since_requeue = (
        _proposal_age_seconds({"updated_at": last_requeue}) if last_requeue else age
    )

    if age >= REQUEUE_AFTER_SECONDS and since_requeue >= REQUEUE_AFTER_SECONDS:
        try:
            _invoke_chat_worker(
                proposal_id=proposal_id,
                username=username,
                company=str(meta.get("company") or settings.company),
            )
            meta["last_requeue_at"] = datetime.now(UTC).isoformat()
            # Preserve running_started_at so stale timeout still works.
            save_proposal(
                settings,
                proposal_id=proposal_id,
                meta=meta,
                dna_yaml=proposal["dna_yaml"],
                reporting_yaml=proposal["reporting_yaml"],
                conversation=proposal.get("conversation") or {"messages": []},
            )
        except Exception as exc:  # noqa: BLE001 — keep refreshing; cancel path handles stale
            print(f"config_assistant_requeue_failed proposal_id={proposal_id} error={exc}")

    return load_proposal(settings, proposal_id)


def complete_chat_turn(
    settings: DnaSettings,
    *,
    proposal_id: str,
    username: str,
    invoke_fn=None,
    client_id: str = "",
    monthly_budget_usd: float | None = None,
) -> dict[str, Any]:
    """Finish a running proposal (background Lambda worker)."""
    resolved_client_id = _resolve_client_id(client_id)
    if resolved_client_id:
        assert_within_budget(
            settings,
            client_id=resolved_client_id,
            monthly_budget_usd=monthly_budget_usd,
        )
    base = load_base_configs(settings)
    proposal = load_proposal(settings, proposal_id)
    if not proposal:
        raise FileNotFoundError(f"Proposal {proposal_id!r} not found")
    meta = proposal["meta"]
    if meta.get("status") != "running":
        return proposal_view(settings, proposal, base)

    conversation = proposal.get("conversation") or {"messages": []}
    messages = list(conversation.get("messages") or [])
    user_message = str(meta.get("pending_user_message") or "").strip()
    if not user_message and messages and messages[-1].get("role") == "user":
        user_message = str(messages[-1].get("content") or "").strip()

    # History for the model should not include the pending user turn — re-appended below.
    if messages and messages[-1].get("role") == "user":
        messages = messages[:-1]

    if not user_message:
        meta = dict(meta)
        meta["status"] = "open"
        meta.pop("pending_user_message", None)
        save_proposal(
            settings,
            proposal_id=proposal_id,
            meta=meta,
            dna_yaml=proposal["dna_yaml"],
            reporting_yaml=proposal["reporting_yaml"],
            conversation={"messages": messages},
        )
        raise ValueError("No pending user message to complete")

    try:
        return _apply_assistant_turn(
            settings,
            base=base,
            proposal_id=proposal_id,
            messages=messages,
            user_message=user_message,
            next_version=str(meta.get("next_version") or base["next_version"]),
            base_version=str(meta.get("base_version") or base["base_version"]),
            current_dna=proposal["dna_yaml"],
            current_reporting=proposal["reporting_yaml"],
            username=username or str(meta.get("created_by") or "admin"),
            prior_meta=dict(meta),
            invoke_fn=invoke_fn,
            client_id=resolved_client_id,
        )
    except Exception as exc:  # noqa: BLE001 — surface failure in the proposal thread
        fail_messages = list(messages)
        fail_messages.append({"role": "user", "content": user_message})
        fail_messages.append(
            {
                "role": "assistant",
                "content": f"Sorry — the assistant failed: {exc}",
            }
        )
        meta = dict(meta)
        meta["status"] = "open"
        meta.pop("pending_user_message", None)
        save_proposal(
            settings,
            proposal_id=proposal_id,
            meta=meta,
            dna_yaml=proposal["dna_yaml"],
            reporting_yaml=proposal["reporting_yaml"],
            conversation={"messages": fail_messages},
        )
        raise


def submit_chat_turn(
    settings: DnaSettings,
    *,
    user_message: str,
    username: str,
    invoke_fn=None,
    client_id: str = "",
    monthly_budget_usd: float | None = None,
) -> dict[str, Any]:
    """Run chat sync locally; enqueue async on Lambda to avoid API Gateway timeouts."""
    import os

    force_sync = os.getenv("MESHFLOW_CONFIG_ASSISTANT_SYNC", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    if invoke_fn is not None or force_sync or not os.getenv("AWS_LAMBDA_FUNCTION_NAME"):
        return run_chat_turn(
            settings,
            user_message=user_message,
            username=username,
            invoke_fn=invoke_fn,
            client_id=client_id,
            monthly_budget_usd=monthly_budget_usd,
        )
    return enqueue_chat_turn(
        settings,
        user_message=user_message,
        username=username,
        client_id=client_id,
        monthly_budget_usd=monthly_budget_usd,
    )


def deny_proposal(
    settings: DnaSettings,
    proposal_id: str,
    *,
    username: str,
    target: ApproveTarget | None = None,
) -> dict[str, Any]:
    """Deny one pack or the whole proposal. Denying a pack reverts that YAML to the pinned base."""
    proposal = load_proposal(settings, proposal_id)
    if not proposal:
        raise FileNotFoundError(f"Proposal {proposal_id!r} not found")
    if proposal["meta"].get("status") not in {"open", "running"}:
        raise ValueError(f"Proposal {proposal_id!r} is not open")

    base = load_base_configs(settings)
    view = proposal_view(settings, proposal, base)
    meta = dict(view["meta"])
    dna_yaml = proposal["dna_yaml"]
    reporting_yaml = proposal["reporting_yaml"]

    if target is None:
        meta["status"] = "denied"
        meta["denied_by"] = username
        if meta.get("dna_status") == "pending":
            meta["dna_status"] = "denied"
            dna_yaml = base["dna_yaml"]
        if meta.get("reporting_status") == "pending":
            meta["reporting_status"] = "denied"
            reporting_yaml = base["reporting_yaml"]
    else:
        if target not in {"dna", "reporting"}:
            raise ValueError("target must be 'dna' or 'reporting'")
        status_key = "dna_status" if target == "dna" else "reporting_status"
        if meta.get(status_key) == "denied":
            raise ValueError(f"{target} already denied on this proposal")
        if meta.get(status_key) == "approved":
            raise ValueError(f"{target} already approved on this proposal")
        if meta.get(status_key) == "skipped":
            raise ValueError(f"No {target} changes to deny")
        if meta.get(status_key) != "pending":
            raise ValueError(f"{target} is not pending denial")
        meta[status_key] = "denied"
        if target == "dna":
            dna_yaml = base["dna_yaml"]
        else:
            reporting_yaml = base["reporting_yaml"]
        if _proposal_fully_resolved(meta):
            meta["status"] = "denied"
            meta["denied_by"] = username
        else:
            meta["status"] = "open"

    save_proposal(
        settings,
        proposal_id=proposal_id,
        meta=meta,
        dna_yaml=dna_yaml,
        reporting_yaml=reporting_yaml,
        conversation=proposal.get("conversation") or {"messages": []},
    )
    return {
        "status": meta["status"],
        "proposal_id": proposal_id,
        "target": target or "all",
        "dna_status": meta.get("dna_status"),
        "reporting_status": meta.get("reporting_status"),
        "fully_resolved": meta["status"] != "open",
    }


def _append_history(
    state: dict[str, Any],
    *,
    version: str,
    username: str,
    proposal_id: str,
    target: str,
) -> None:
    history = state.get("history")
    if not isinstance(history, list):
        history = []
    history.append(
        {
            "version": version,
            "status": "production",
            "approver": username,
            "at": datetime.now(UTC).isoformat(),
            "notes": f"Approved {target} via Config Assistant proposal {proposal_id}",
            "target": target,
        }
    )
    state["history"] = history


def _proposal_fully_resolved(meta: dict[str, Any]) -> bool:
    dna_status = str(meta.get("dna_status") or "skipped")
    reporting_status = str(meta.get("reporting_status") or "skipped")
    return dna_status in {"approved", "skipped", "denied"} and reporting_status in {
        "approved",
        "skipped",
        "denied",
    }


def approve_proposal(
    settings: DnaSettings,
    proposal_id: str,
    *,
    username: str,
    target: ApproveTarget,
    next_version: str | None = None,
) -> dict[str, Any]:
    """Approve and pin one pack from an open proposal (DNA or reporting)."""
    if target not in {"dna", "reporting"}:
        raise ValueError("target must be 'dna' or 'reporting'")

    proposal = load_proposal(settings, proposal_id)
    if not proposal:
        raise FileNotFoundError(f"Proposal {proposal_id!r} not found")
    if proposal["meta"].get("status") != "open":
        raise ValueError(f"Proposal {proposal_id!r} is not open")

    base = load_base_configs(settings)
    view = proposal_view(settings, proposal, base)
    meta = dict(view["meta"])
    status_key = "dna_status" if target == "dna" else "reporting_status"
    if meta.get(status_key) == "approved":
        raise ValueError(f"{target} already approved on this proposal")
    if meta.get(status_key) == "skipped":
        raise ValueError(f"No {target} changes to approve")
    if meta.get(status_key) != "pending":
        raise ValueError(f"{target} is not pending approval")

    state = load_workflow_state(settings, settings.dna_config_id)
    state["pack_id"] = settings.dna_config_id
    saved: dict[str, Any] = {}

    if target == "dna":
        version = (
            next_version
            or meta.get("next_dna_version")
            or base["next_dna_version"]
        ).strip()
        if not version:
            raise ValueError("next_version is required to approve DNA")
        version_base = str(meta.get("dna_base_version") or base["dna_version"])
        bump = classify_manual_version_bump(version_base, version)
        if bump["kind"] == "invalid":
            raise ValueError(bump["error"])
        pack = load_definition_pack_yaml(proposal["dna_yaml"])
        pack.pack_id = settings.dna_config_id
        pack.version = version
        pack.status = "production"
        pack.approval.status = "production"
        pack.approval.approver = username
        saved = save_governance_version(settings, pack=pack, reporting=None)
        # Keep reporting on its own pin so DNA-only bumps do not orphan the sidecar.
        if not state.get("active_reporting_version"):
            state["active_reporting_version"] = base["reporting_version"]
        state["active_version"] = version
        meta["dna_status"] = "approved"
        meta["next_dna_version"] = version
        _append_history(
            state,
            version=version,
            username=username,
            proposal_id=proposal_id,
            target="dna",
        )
    else:
        version = (
            next_version
            or meta.get("next_reporting_version")
            or base["next_reporting_version"]
        ).strip()
        if not version:
            raise ValueError("next_version is required to approve reporting")
        version_base = str(meta.get("reporting_base_version") or base["reporting_version"])
        bump = classify_manual_version_bump(version_base, version)
        if bump["kind"] == "invalid":
            raise ValueError(bump["error"])
        reporting = load_reporting_pack_yaml(proposal["reporting_yaml"])
        reporting = normalize_reporting_identity(
            settings, reporting, version=version, status="production"
        )
        saved = save_reporting_pack(
            settings,
            pack_id=settings.dna_config_id,
            version=version,
            reporting=reporting,
            status="production",
        )
        state["active_reporting_version"] = version
        # Keep DNA pin unchanged when only reporting is approved.
        if not state.get("active_version"):
            state["active_version"] = base["dna_version"]
        meta["reporting_status"] = "approved"
        meta["next_reporting_version"] = version
        _append_history(
            state,
            version=version,
            username=username,
            proposal_id=proposal_id,
            target="reporting",
        )

    save_workflow_state(settings, state)

    if _proposal_fully_resolved(meta):
        meta["status"] = "approved"
        meta["approved_by"] = username
    meta["next_version"] = version

    save_proposal(
        settings,
        proposal_id=proposal_id,
        meta=meta,
        dna_yaml=proposal["dna_yaml"],
        reporting_yaml=proposal["reporting_yaml"],
        conversation=proposal.get("conversation") or {"messages": []},
    )
    return {
        "status": meta["status"],
        "proposal_id": proposal_id,
        "target": target,
        "version": version,
        "dna_path": saved.get("dna_path"),
        "reporting_path": saved.get("path") or saved.get("reporting_path"),
        "dna_status": meta.get("dna_status"),
        "reporting_status": meta.get("reporting_status"),
        "fully_resolved": meta["status"] == "approved",
    }


def load_proposal_reporting(settings: DnaSettings, proposal_id: str) -> dict[str, Any]:
    proposal = load_proposal(settings, proposal_id)
    if not proposal or proposal["meta"].get("status") != "open":
        raise FileNotFoundError(f"Open proposal {proposal_id!r} not found")
    return load_reporting_pack_yaml(proposal["reporting_yaml"])
