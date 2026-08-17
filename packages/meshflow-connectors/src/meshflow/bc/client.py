from __future__ import annotations

from typing import Any

import httpx

from meshflow.bc.auth import ensure_access_token
from meshflow.bc.entities import BCEntitySpec
from meshflow.bc.token_store import BCTokens
from meshflow.config import BCSettings


class BCClient:
    """Minimal Business Central OData client for scheduled ingest."""

    def __init__(self, settings: BCSettings, tokens: BCTokens) -> None:
        self.settings = settings
        self.tokens = tokens

    @property
    def api_root(self) -> str:
        return (
            "https://api.businesscentral.dynamics.com/v2.0/"
            f"{self.settings.tenant_id}/{self.settings.environment_name}/api/v2.0"
        )

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"{self.tokens.token_type} {self.tokens.access_token}",
            "Accept": "application/json",
        }

    def _request(self, method: str, url: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        with httpx.Client(timeout=120.0) as client:
            response = client.request(method, url, headers=self._headers(), params=params)

        if response.status_code == 401:
            self.tokens = ensure_access_token(self.settings, None)
            with httpx.Client(timeout=120.0) as client:
                response = client.request(method, url, headers=self._headers(), params=params)

        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError(f"Unexpected BC response type from {url}")
        return payload

    def company(self) -> dict[str, Any]:
        url = f"{self.api_root}/companies({self.settings.company_id})"
        return self._request("GET", url)

    def list_companies(self) -> list[dict[str, str]]:
        url = f"{self.api_root}/companies"
        rows: list[dict[str, Any]] = []
        request_params: dict[str, Any] | None = None

        while url:
            payload = self._request("GET", url, params=request_params)
            batch = payload.get("value", [])
            if isinstance(batch, list):
                rows.extend(item for item in batch if isinstance(item, dict))

            next_link = payload.get("@odata.nextLink")
            if not next_link:
                break
            url = str(next_link)
            request_params = None

        companies: list[dict[str, str]] = []
        for row in rows:
            company_id = str(row.get("id", "")).strip()
            if not company_id:
                continue
            display_name = str(row.get("displayName") or row.get("name") or company_id).strip()
            companies.append({"id": company_id, "display_name": display_name})
        companies.sort(key=lambda item: item["display_name"].lower())
        return companies

    def list_entity_rows(
        self,
        spec: BCEntitySpec,
        *,
        watermark: str | None = None,
    ) -> list[dict[str, Any]]:
        filters: list[str] = []
        if spec.odata_filter:
            filters.append(spec.odata_filter)
        if watermark and spec.incremental_field:
            filters.append(f"{spec.incremental_field} gt {watermark}")

        params: dict[str, Any] = {}
        if filters:
            params["$filter"] = " and ".join(f"({item})" for item in filters)
        if spec.expand:
            params["$expand"] = spec.expand

        url = f"{self.api_root}/companies({self.settings.company_id})/{spec.resource}"
        rows: list[dict[str, Any]] = []
        request_params: dict[str, Any] | None = params

        while url:
            payload = self._request("GET", url, params=request_params)
            batch = payload.get("value", [])
            if isinstance(batch, list):
                rows.extend(item for item in batch if isinstance(item, dict))

            next_link = payload.get("@odata.nextLink")
            if not next_link:
                break
            url = str(next_link)
            request_params = None

        return rows

    @classmethod
    def from_settings(cls, settings: BCSettings) -> BCClient:
        from meshflow.bc.token_store import load_tokens

        tokens = load_tokens(settings)
        tokens = ensure_access_token(settings, tokens)
        return cls(settings, tokens)
