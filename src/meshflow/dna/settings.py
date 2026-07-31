from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class DnaSettings:
    source: str
    data_dir: Path
    s3_bucket: str | None = None
    pack_id: str = "bc_intra_v1"
    pack_version: str | None = None

    @property
    def silver_prefix(self) -> str:
        return f"silver/{self.source}"

    @property
    def dna_prefix(self) -> str:
        return "dna"

    @property
    def gold_dna_prefix(self) -> str:
        return "gold/dna"

    @property
    def gold_dna_staging_prefix(self) -> str:
        return "gold/dna/_staging"
