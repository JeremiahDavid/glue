from __future__ import annotations

from hiveflow.bc.client import BCClient
from hiveflow.bc.entities import BCEntitySpec
from hiveflow.bc.token_store import BCTokens
from hiveflow.config import BCSettings


def test_bc_client_paginates_odata(tmp_path, monkeypatch) -> None:
    settings = BCSettings(
        client_id="client",
        client_secret="secret",
        tenant_id="tenant",
        environment_name="Sandbox",
        company_id="company-guid",
        data_dir=tmp_path,
    )
    tokens = BCTokens(
        access_token="token",
        tenant_id="tenant",
        environment_name="Sandbox",
        company_id="company-guid",
    )
    client = BCClient(settings, tokens)

    calls: list[str] = []

    def fake_request(method: str, url: str, *, params=None):
        calls.append(url)
        if len(calls) == 1:
            return {
                "value": [{"id": "1", "number": "SO-1"}],
                "@odata.nextLink": "https://example.test/next-page",
            }
        return {"value": [{"id": "2", "number": "SO-2"}]}

    monkeypatch.setattr(client, "_request", fake_request)

    rows = client.list_entity_rows(BCEntitySpec("sales_orders", "salesOrders"))
    assert len(rows) == 2
    assert calls[1] == "https://example.test/next-page"


def test_bc_client_applies_incremental_filter(tmp_path, monkeypatch) -> None:
    settings = BCSettings(
        client_id="client",
        client_secret="secret",
        tenant_id="tenant",
        environment_name="Sandbox",
        company_id="company-guid",
        data_dir=tmp_path,
    )
    tokens = BCTokens(
        access_token="token",
        tenant_id="tenant",
        environment_name="Sandbox",
        company_id="company-guid",
    )
    client = BCClient(settings, tokens)
    captured: list[dict | None] = []

    def fake_request(method: str, url: str, *, params=None):
        captured.append(params)
        return {"value": []}

    monkeypatch.setattr(client, "_request", fake_request)

    client.list_entity_rows(
        BCEntitySpec("customers", "customers"),
        watermark="2026-01-01T00:00:00Z",
    )
    assert captured[0]["$filter"] == "(lastModifiedDateTime gt 2026-01-01T00:00:00Z)"


def test_bc_client_skips_incremental_filter_when_disabled(tmp_path, monkeypatch) -> None:
    settings = BCSettings(
        client_id="client",
        client_secret="secret",
        tenant_id="tenant",
        environment_name="Sandbox",
        company_id="company-guid",
        data_dir=tmp_path,
    )
    tokens = BCTokens(
        access_token="token",
        tenant_id="tenant",
        environment_name="Sandbox",
        company_id="company-guid",
    )
    client = BCClient(settings, tokens)
    captured: list[dict | None] = []

    def fake_request(method: str, url: str, *, params=None):
        captured.append(params)
        return {"value": []}

    monkeypatch.setattr(client, "_request", fake_request)

    client.list_entity_rows(
        BCEntitySpec("balance_sheets", "balanceSheets", incremental_field=None),
        watermark="2026-01-01T00:00:00Z",
    )
    assert captured[0] == {}


def test_bc_client_probe_entity_rows_uses_top(tmp_path, monkeypatch) -> None:
    settings = BCSettings(
        client_id="client",
        client_secret="secret",
        tenant_id="tenant",
        environment_name="Sandbox",
        company_id="company-guid",
        data_dir=tmp_path,
    )
    tokens = BCTokens(
        access_token="token",
        tenant_id="tenant",
        environment_name="Sandbox",
        company_id="company-guid",
    )
    client = BCClient(settings, tokens)
    captured: list[dict | None] = []

    def fake_request(method: str, url: str, *, params=None):
        captured.append(params)
        return {"value": [{"id": "1", "displayName": "CRONUS"}]}

    monkeypatch.setattr(client, "_request", fake_request)

    row_count = client.probe_entity_rows(
        BCEntitySpec("company_information", "companyInformation", incremental_field=None),
    )
    assert row_count == 1
    assert captured[0] == {"$top": 1}
