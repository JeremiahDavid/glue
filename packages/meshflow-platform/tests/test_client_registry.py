"""Tests for client onboarding registry."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from meshflow.client_registry import (
    ClientCreateSpec,
    ClientRegistry,
    ConnectorSchedule,
    ConnectorSpec,
    DnaSpec,
    PortalClientSpec,
    StackLifecycle,
    describe_stack_status,
    validate_client_create_spec,
)


@pytest.fixture()
def config_path(tmp_path: Path) -> Path:
    source = Path(__file__).resolve().parents[3] / "config.yaml"
    payload = yaml.safe_load(source.read_text(encoding="utf-8"))
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def test_validate_client_create_spec_rejects_duplicate_company(config_path: Path) -> None:
    spec = ClientCreateSpec(
        company="POC",
        client_id="newco",
        environment="dev",
        connectors=(ConnectorSpec(source="dbc", entity_bundle="full"),),
        dna=DnaSpec(source="dbc"),
        portal=PortalClientSpec(display_name="New Co", reporting_hostname="newco"),
    )
    with pytest.raises(ValueError, match="already exists"):
        validate_client_create_spec(spec, path=config_path)


def test_create_client_writes_config(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "platform": {
                    "environments": {
                        "dev": {
                            "ui": {
                                "portal": {"clients": {}},
                            }
                        }
                    }
                },
                "companies": {},
            }
        ),
        encoding="utf-8",
    )
    registry = ClientRegistry(path=path)
    record = registry.create_client(
        ClientCreateSpec(
            company="ACME",
            client_id="acme",
            environment="dev",
            connectors=(
                ConnectorSpec(
                    source="dbc",
                    entity_bundle="full",
                    schedule=ConnectorSchedule(hour=6, minute=30),
                ),
            ),
            dna=DnaSpec(enabled=True, source="dbc", schedule=ConnectorSchedule(hour=7, minute=0)),
            portal=PortalClientSpec(display_name="Acme Corp", reporting_hostname="acme"),
        )
    )
    assert record.company == "ACME"
    assert record.client_id == "acme"
    saved = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert "ACME" in saved["companies"]
    assert "acme" in saved["platform"]["environments"]["dev"]["ui"]["portal"]["clients"]


def test_create_client_writes_multiple_connectors(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "platform": {
                    "environments": {
                        "dev": {
                            "ui": {
                                "portal": {"clients": {}},
                            }
                        }
                    }
                },
                "companies": {},
            }
        ),
        encoding="utf-8",
    )
    registry = ClientRegistry(path=path)
    registry.create_client(
        ClientCreateSpec(
            company="ACME",
            client_id="acme",
            environment="dev",
            connectors=(
                ConnectorSpec(source="dbc", entity_bundle="full", schedule=ConnectorSchedule(hour=6, minute=30)),
                ConnectorSpec(source="qbo", entity_bundle="full_accounting", schedule=ConnectorSchedule(hour=6, minute=0), tier="sandbox"),
            ),
            dna=DnaSpec(enabled=True, source="dbc"),
            portal=PortalClientSpec(display_name="Acme Corp", reporting_hostname="acme"),
        )
    )
    saved = yaml.safe_load(path.read_text(encoding="utf-8"))
    env_config = saved["companies"]["ACME"]["environments"]["dev"]
    assert "dbc" in env_config
    assert "qbo" in env_config
    assert env_config["dna"]["source"] == "dbc"


def test_describe_stack_status_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeClient:
        def describe_stacks(self, **kwargs):
            from botocore.exceptions import ClientError

            raise ClientError({"Error": {"Code": "ValidationError", "Message": "does not exist"}}, "DescribeStacks")

        def describe_stack_events(self, **kwargs):
            return {"StackEvents": []}

    class FakeBoto3:
        def client(self, name, region_name=None):
            return FakeClient()

    monkeypatch.setitem(__import__("sys").modules, "boto3", FakeBoto3())
    status = describe_stack_status("MissingStack-dev")
    assert status.status == StackLifecycle.NOT_FOUND
