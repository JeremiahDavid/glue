"""DNA — Semantic Engine: versioned definition packs → certified gold tables."""

from pkgutil import extend_path

__path__ = extend_path(__path__, __name__)

from meshflow.dna.compile import compile_pack
from meshflow.dna.governance import load_governance_dna, save_governance_version
from meshflow.dna.init_client import ensure_client_governance, init_client_governance
from meshflow.dna.ingest_docs import draft_pack_from_documents, draft_pack_from_files
from meshflow.dna.publish import publish_staging
from meshflow.dna.schema import DefinitionPack, load_definition_pack_file, starter_pack_path
from meshflow.dna.validate import run_validation
from meshflow.dna.workflow import load_production_pack, promote_pack, save_definition_pack

__all__ = [
    "DefinitionPack",
    "compile_pack",
    "draft_pack_from_documents",
    "draft_pack_from_files",
    "ensure_client_governance",
    "init_client_governance",
    "load_definition_pack_file",
    "load_governance_dna",
    "load_production_pack",
    "promote_pack",
    "publish_staging",
    "run_validation",
    "save_definition_pack",
    "save_governance_version",
    "starter_pack_path",
]
