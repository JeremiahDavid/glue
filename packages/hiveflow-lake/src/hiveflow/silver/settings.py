from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from hiveflow.config import DEFAULT_DATA_DIR
from hiveflow.storage.paths import raw_source_prefix, silver_stg_source_prefix


@dataclass(frozen=True)
class ConsolidateSettings:
    source: str
    data_dir: Path
    s3_bucket: str | None = None
    raw_prefix: str | None = None

    @property
    def bronze_prefix(self) -> str:
        if self.raw_prefix:
            return self.raw_prefix.strip("/")
        return raw_source_prefix(self.source)

    @property
    def silver_prefix(self) -> str:
        return silver_stg_source_prefix(self.source)


def load_consolidate_settings(source: str) -> ConsolidateSettings:
    source_slug = source.strip().lower()
    if not source_slug:
        raise ValueError("source is required")

    from hiveflow.project_config import resolve_ingest_s3_prefix, resolve_selection

    company, hiveflow_environment = resolve_selection()
    data_dir = Path(os.getenv("HIVEFLOW_DATA_DIR", str(DEFAULT_DATA_DIR)))
    s3_bucket = os.getenv("HIVEFLOW_S3_BUCKET", "").strip() or None
    raw_prefix = os.getenv("HIVEFLOW_S3_PREFIX", "").strip().strip("/") or None
    if not raw_prefix:
        raw_prefix = resolve_ingest_s3_prefix(company, hiveflow_environment, source=source_slug)

    return ConsolidateSettings(
        source=source_slug,
        data_dir=data_dir,
        s3_bucket=s3_bucket,
        raw_prefix=raw_prefix,
    )
