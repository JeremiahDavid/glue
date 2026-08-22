from __future__ import annotations

from typing import Any

import httpx

from hiveflow.config import QBOSettings
from hiveflow.qbo.oauth import access_token_is_valid, ensure_access_token
from hiveflow.qbo.token_store import QBOTokens, load_tokens


class QBOClient:
    """Minimal QuickBooks Online API client for POC ingestion."""

    MINOR_VERSION = 75

    def __init__(self, settings: QBOSettings, tokens: QBOTokens) -> None:
        self.settings = settings
        self.tokens = tokens

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.tokens.access_token}",
            "Accept": "application/json",
        }

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        url = f"{self.settings.api_base_url}{path}"
        with httpx.Client(timeout=60.0) as client:
            response = client.request(method, url, headers=self._headers(), **kwargs)

        if response.status_code == 401:
            latest = load_tokens(self.settings.token_path)
            if latest and access_token_is_valid(latest):
                self.tokens = latest
            else:
                self.tokens = ensure_access_token(self.settings, latest or self.tokens)
            with httpx.Client(timeout=60.0) as client:
                response = client.request(method, url, headers=self._headers(), **kwargs)

        response.raise_for_status()
        return response.json()

    def query(self, sql: str) -> list[dict[str, Any]]:
        """Run a QBO SQL-like query with pagination."""
        rows: list[dict[str, Any]] = []
        start = 1
        page_size = 1000

        while True:
            paged_sql = f"{sql} STARTPOSITION {start} MAXRESULTS {page_size}"
            payload = self._request(
                "GET",
                f"/v3/company/{self.tokens.realm_id}/query",
                params={"query": paged_sql, "minorversion": self.MINOR_VERSION},
            )
            query_response = payload.get("QueryResponse", {})
            entity_key = next((key for key in query_response if key not in {"startPosition", "maxResults", "totalCount"}), None)
            if not entity_key:
                break

            batch = query_response.get(entity_key, [])
            if not batch:
                break

            rows.extend(batch)
            if len(batch) < page_size:
                break
            start += page_size

        return rows

    def company_info(self) -> dict[str, Any]:
        payload = self._request(
            "GET",
            f"/v3/company/{self.tokens.realm_id}/companyinfo/{self.tokens.realm_id}",
            params={"minorversion": self.MINOR_VERSION},
        )
        return payload.get("CompanyInfo", {})

    @classmethod
    def from_settings(cls, settings: QBOSettings, tokens: QBOTokens) -> QBOClient:
        return cls(settings, tokens)

    @classmethod
    def from_saved_tokens(cls, settings: QBOSettings) -> QBOClient:
        tokens = ensure_access_token(settings)
        return cls(settings, tokens)
