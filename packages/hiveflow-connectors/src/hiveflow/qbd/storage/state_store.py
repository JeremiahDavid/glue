from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from hiveflow.config import QBDSettings
from hiveflow.storage.paths import prefix_path


class StateStore:
    """Persist QBWC sessions and connector sync state to S3 or local disk."""

    def __init__(self, settings: QBDSettings) -> None:
        self.settings = settings

    @property
    def state_root(self) -> Path:
        return prefix_path(self.settings.data_dir, self.settings.s3_prefix, "_state")

    def _state_key(self, *parts: str) -> str:
        suffix = "/".join(part.strip("/") for part in parts if part)
        return f"{self.settings.s3_prefix.strip('/')}/_state/{suffix}"

    def get_json(self, key: str) -> dict[str, Any] | None:
        if self.settings.s3_bucket:
            return self._get_json_s3(key)
        return self._get_json_local(key)

    def put_json(self, key: str, payload: dict[str, Any]) -> None:
        if self.settings.s3_bucket:
            self._put_json_s3(key, payload)
            return
        self._put_json_local(key, payload)

    def _local_path(self, key: str) -> Path:
        relative = key.split(f"{self.settings.s3_prefix.strip('/')}/_state/", 1)[-1]
        return self.state_root / relative

    def _get_json_local(self, key: str) -> dict[str, Any] | None:
        path = self._local_path(key)
        if not path.is_file():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else None

    def _put_json_local(self, key: str, payload: dict[str, Any]) -> None:
        path = self._local_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    def _get_json_s3(self, key: str) -> dict[str, Any] | None:
        import boto3
        from botocore.exceptions import ClientError

        client = boto3.client("s3")
        try:
            response = client.get_object(Bucket=self.settings.s3_bucket, Key=key)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in {"NoSuchKey", "404"}:
                return None
            raise
        payload = json.loads(response["Body"].read().decode("utf-8"))
        return payload if isinstance(payload, dict) else None

    def _put_json_s3(self, key: str, payload: dict[str, Any]) -> None:
        import boto3

        boto3.client("s3").put_object(
            Bucket=self.settings.s3_bucket,
            Key=key,
            Body=json.dumps(payload, indent=2, default=str).encode("utf-8"),
            ContentType="application/json",
        )

    def session_key(self, ticket: str) -> str:
        return self._state_key("sessions", f"{ticket}.json")

    def connector_state_key(self) -> str:
        return self._state_key("connector_state.json")

    def sync_run_key(self, sync_run_id: str) -> str:
        return self._state_key("sync_runs", f"{sync_run_id}.json")
