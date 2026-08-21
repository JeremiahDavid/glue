"""HiveFlowAI branding assets — optional S3-backed static files."""

from __future__ import annotations

import os
from functools import lru_cache

# Map bundled static filenames to environment variables holding the S3 object key.
STATIC_FILENAME_ENV: dict[str, str] = {
    "hiveflowai-symbol.png": "HIVEFLOW_BRANDING_SYMBOL_KEY",
    "hiveflowai-logo.png": "HIVEFLOW_BRANDING_LOGO_KEY",
}


def branding_bucket() -> str:
    return os.environ.get("HIVEFLOW_BRANDING_BUCKET", "").strip()


def branding_object_key(filename: str) -> str | None:
    env_name = STATIC_FILENAME_ENV.get(filename)
    if not env_name:
        return None
    key = os.environ.get(env_name, "").strip()
    return key or None


def _fetch_s3_object(bucket: str, key: str) -> bytes | None:
    try:
        import boto3
        from botocore.exceptions import BotoCoreError, ClientError

        response = boto3.client("s3").get_object(Bucket=bucket, Key=key)
        body = response["Body"].read()
        return body if body else None
    except (ImportError, BotoCoreError, ClientError, OSError):
        return None


@lru_cache(maxsize=8)
def _fetch_s3_object_cached(bucket: str, key: str) -> bytes | None:
    return _fetch_s3_object(bucket, key)


def load_branding_asset(filename: str) -> bytes | None:
    """Load a branding asset from S3 when configured; otherwise None (use bundled static)."""
    bucket = branding_bucket()
    key = branding_object_key(filename)
    if not bucket or not key:
        return None
    dev_mode = os.environ.get("HIVEFLOW_DEV", "").strip().lower() in {"1", "true", "yes"}
    if dev_mode:
        return _fetch_s3_object(bucket, key)
    return _fetch_s3_object_cached(bucket, key)
