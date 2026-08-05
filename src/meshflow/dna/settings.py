from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from meshflow.storage.paths import company_dna_config_id, company_reporting_config_id


@dataclass
class DnaSettings:
    source: str
    data_dir: Path
    s3_bucket: str | None = None
    company: str = ""
    pack_id: str = ""
    pack_version: str | None = None

    def __post_init__(self) -> None:
        if self.company and not self.pack_id:
            self.pack_id = company_dna_config_id(self.company)
        if not self.pack_id:
            self.pack_id = "bc_intra_v1"

    @property
    def silver_prefix(self) -> str:
        return f"silver/{self.source}"

    @property
    def dna_prefix(self) -> str:
        return "dna"

    @property
    def governance_prefix(self) -> str:
        return "governance"

    @property
    def gold_dna_prefix(self) -> str:
        return "gold/dna"

    @property
    def gold_dna_staging_prefix(self) -> str:
        return "gold/dna/_staging"

    @property
    def dna_config_id(self) -> str:
        """Company DNA config pack id used by gold compile."""
        if self.company:
            return company_dna_config_id(self.company)
        return self.pack_id

    @property
    def reporting_config_id(self) -> str:
        """Company reporting config id used for portal layout contract."""
        if self.company:
            return company_reporting_config_id(self.company)
        pack = (self.pack_id or "").strip().lower()
        if pack.endswith("_dna_config"):
            return pack[: -len("_dna_config")] + "_reporting_config"
        return "reporting"