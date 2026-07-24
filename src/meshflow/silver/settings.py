from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from meshflow.config import DEFAULT_DATA_DIR


@dataclass(frozen=True)
class ConsolidateSettings:
    source: str
    data_dir: Path
    s3_bucket: str | None = None
    s3_prefix: str = "qbo"

    @property
    def consolidated_prefix(self) -> str:
        return f"{self.s3_prefix.strip('/')}/_consolidated"


def load_consolidate_settings(source: str) -> ConsolidateSettings:
    source_slug = source.strip().lower()
    if not source_slug:
        raise ValueError("source is required")

    data_dir = Path(os.getenv("MESHFLOW_DATA_DIR", str(DEFAULT_DATA_DIR)))
    s3_bucket = os.getenv("MESHFLOW_S3_BUCKET", "").strip() or None
    prefix = os.getenv("MESHFLOW_S3_PREFIX", source_slug).strip().strip("/") or source_slug

    return ConsolidateSettings(
        source=source_slug,
        data_dir=data_dir,
        s3_bucket=s3_bucket,
        s3_prefix=prefix,
    )
