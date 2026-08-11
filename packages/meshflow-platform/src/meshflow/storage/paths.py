from __future__ import annotations

from pathlib import Path

DATA_LAYERS = ("raw", "silver", "gold")


def layer_source_prefix(layer: str, source: str) -> str:
    """Build `{layer}/{source}` prefix inside the company data bucket."""
    layer_slug = layer.strip().strip("/").lower()
    source_slug = source.strip().strip("/").lower()
    if layer_slug not in DATA_LAYERS:
        raise ValueError(f"Unknown data layer {layer!r}. Expected one of: {', '.join(DATA_LAYERS)}")
    if not source_slug:
        raise ValueError("source is required for source-scoped layers")
    return f"{layer_slug}/{source_slug}"


def raw_source_prefix(source: str) -> str:
    return layer_source_prefix("raw", source)


def silver_source_prefix(source: str) -> str:
    return layer_source_prefix("silver", source)


def gold_prefix() -> str:
    return "gold"


def gold_dna_prefix() -> str:
    return "gold/dna"


def gold_dna_staging_prefix() -> str:
    return "gold/dna/_staging"


def gold_dna_entity_prefix(output_id: str) -> str:
    return f"{gold_dna_prefix()}/{output_id.strip().lower()}"


def gold_dna_entity_parquet_key(output_id: str) -> str:
    return f"{gold_dna_entity_prefix(output_id)}/{SILVER_ENTITY_FILENAME}"


def dna_definition_pack_prefix(pack_id: str, version: str) -> str:
    """Legacy path — prefer governance_* helpers for new writes."""
    return f"dna/definition_packs/v{version.strip()}/{pack_id.strip().lower()}"


def company_slug(company: str) -> str:
    """Normalize company name for governance pack ids (e.g. POC → poc)."""
    import re

    slug = re.sub(r"[^a-z0-9]+", "_", company.strip().lower()).strip("_")
    if not slug or not slug[0].isalpha():
        raise ValueError(f"company must start with a letter after normalization: {company!r}")
    return slug


def company_dna_config_id(company: str) -> str:
    """Canonical DNA pack id / filename stem: ``{company}_dna_config``."""
    return f"{company_slug(company)}_dna_config"


def company_reporting_config_id(company: str) -> str:
    """Canonical reporting pack id / filename stem: ``{company}_reporting_config``."""
    return f"{company_slug(company)}_reporting_config"


def governance_prefix() -> str:
    return "governance"


def governance_pack_prefix(pack_id: str) -> str:
    return f"{governance_prefix()}/{pack_id.strip().lower()}"


def governance_version_prefix(pack_id: str, version: str) -> str:
    return f"{governance_pack_prefix(pack_id)}/v{version.strip()}"


def governance_workflow_key(pack_id: str) -> str:
    return f"{governance_pack_prefix(pack_id)}/workflow.json"


def governance_manifest_key(pack_id: str, version: str) -> str:
    return f"{governance_version_prefix(pack_id, version)}/manifest.json"


def governance_dna_key(pack_id: str, version: str) -> str:
    """Versioned company DNA config YAML, e.g. ``governance/poc_dna_config/v1.0.0/poc_dna_config.yaml``."""
    pack = pack_id.strip().lower()
    return f"{governance_version_prefix(pack, version)}/{pack}.yaml"


def governance_dna_legacy_json_key(pack_id: str, version: str) -> str:
    """Pre-YAML governance DNA key (``dna.json``)."""
    return f"{governance_version_prefix(pack_id, version)}/dna.json"


def governance_reporting_key(pack_id: str, version: str, *, company: str | None = None) -> str:
    """Versioned reporting config YAML beside the DNA pack."""
    if company:
        name = company_reporting_config_id(company)
    elif pack_id.strip().lower().endswith("_dna_config"):
        name = pack_id.strip().lower()[: -len("_dna_config")] + "_reporting_config"
    else:
        name = "reporting"
    return f"{governance_version_prefix(pack_id, version)}/{name}.yaml"


def governance_reporting_legacy_json_key(pack_id: str, version: str) -> str:
    return f"{governance_version_prefix(pack_id, version)}/reporting.json"


def governance_docs_prefix(pack_id: str, version: str) -> str:
    return f"{governance_version_prefix(pack_id, version)}/docs"


def governance_proposals_prefix(pack_id: str) -> str:
    return f"{governance_pack_prefix(pack_id)}/proposals"


def governance_proposal_prefix(pack_id: str, proposal_id: str) -> str:
    pid = proposal_id.strip().lower()
    if not pid or ".." in pid or "/" in pid or "\\" in pid:
        raise ValueError(f"Invalid proposal id: {proposal_id!r}")
    return f"{governance_proposals_prefix(pack_id)}/{pid}"


def governance_proposal_meta_key(pack_id: str, proposal_id: str) -> str:
    return f"{governance_proposal_prefix(pack_id, proposal_id)}/meta.json"


def governance_proposal_dna_key(pack_id: str, proposal_id: str) -> str:
    return f"{governance_proposal_prefix(pack_id, proposal_id)}/dna.yaml"


def governance_proposal_reporting_key(pack_id: str, proposal_id: str) -> str:
    return f"{governance_proposal_prefix(pack_id, proposal_id)}/reporting.yaml"


def governance_proposal_conversation_key(pack_id: str, proposal_id: str) -> str:
    return f"{governance_proposal_prefix(pack_id, proposal_id)}/conversation.json"


def governance_doc_key(pack_id: str, version: str, filename: str) -> str:
    name = filename.strip().lstrip("/").replace("\\", "/")
    if not name or ".." in name.split("/"):
        raise ValueError(f"Invalid governance doc filename: {filename!r}")
    return f"{governance_docs_prefix(pack_id, version)}/{name}"


def governance_field_semantics_prefix(pack_id: str) -> str:
    return f"{governance_pack_prefix(pack_id)}/field_semantics"


def governance_field_semantics_draft_key(pack_id: str) -> str:
    return f"{governance_field_semantics_prefix(pack_id)}/draft.yaml"


def governance_field_semantics_workflow_key(pack_id: str) -> str:
    return f"{governance_field_semantics_prefix(pack_id)}/workflow.json"


def governance_field_semantics_version_prefix(pack_id: str, version: str) -> str:
    return f"{governance_field_semantics_prefix(pack_id)}/v{version.strip()}"


def governance_field_semantics_key(pack_id: str, version: str) -> str:
    return f"{governance_field_semantics_version_prefix(pack_id, version)}/field_semantics.yaml"


def governance_field_semantics_manifest_key(pack_id: str, version: str) -> str:
    return f"{governance_field_semantics_version_prefix(pack_id, version)}/manifest.json"


def governance_semantic_model_prefix(pack_id: str) -> str:
    return f"{governance_pack_prefix(pack_id)}/semantic_model"


def governance_semantic_model_draft_key(pack_id: str) -> str:
    return f"{governance_semantic_model_prefix(pack_id)}/draft.yaml"


def governance_semantic_model_workflow_key(pack_id: str) -> str:
    return f"{governance_semantic_model_prefix(pack_id)}/workflow.json"


def governance_semantic_model_version_prefix(pack_id: str, version: str) -> str:
    return f"{governance_semantic_model_prefix(pack_id)}/v{version.strip()}"


def governance_semantic_model_key(pack_id: str, version: str) -> str:
    return f"{governance_semantic_model_version_prefix(pack_id, version)}/semantic_model.yaml"


def governance_semantic_model_manifest_key(pack_id: str, version: str) -> str:
    return f"{governance_semantic_model_version_prefix(pack_id, version)}/manifest.json"


def governance_semantic_docs_prefix(pack_id: str) -> str:
    """Tenant-uploaded markdown references for semantic RAG (optional)."""
    return f"{governance_pack_prefix(pack_id)}/semantic_docs"


def governance_semantic_overrides_key(pack_id: str) -> str:
    """Tenant YAML overrides for semantic entities, joins, and column hints."""
    return f"{governance_pack_prefix(pack_id)}/semantic_overrides.yaml"


def governance_source_semantic_reference_prefix(source: str) -> str:
    """Cross-tenant approved semantic build snapshots for one silver source connector."""
    connector = source.strip().lower()
    if not connector:
        raise ValueError("source is required")
    return f"{governance_prefix()}/source_semantic_reference/{connector}"


def governance_source_semantic_reference_index_key(source: str) -> str:
    return f"{governance_source_semantic_reference_prefix(source)}/index.json"


def governance_source_semantic_reference_consensus_key(source: str) -> str:
    return f"{governance_source_semantic_reference_prefix(source)}/consensus.yaml"


def governance_source_semantic_latest_profile_key(source: str) -> str:
    """Merged documentation + approved-build baseline used for silver profiling."""
    return f"{governance_source_semantic_reference_prefix(source)}/latest_profile.yaml"


def governance_source_semantic_reference_build_key(source: str, pack_id: str, version: str) -> str:
    pack = pack_id.strip().lower()
    ver = version.strip().replace("/", "_")
    if not pack or not ver:
        raise ValueError("pack_id and version are required")
    return f"{governance_source_semantic_reference_prefix(source)}/builds/{pack}__v{ver}.yaml"


def governance_source_docs_overlay_key(source: str, filename: str) -> str:
    """Client overlay YAML under governance/source_semantic_reference/{source}/."""
    name = filename.strip().lstrip("/")
    if not name:
        raise ValueError("filename is required")
    return f"{governance_source_semantic_reference_prefix(source)}/{name}"


def governance_source_docs_gold_prefix(source: str) -> str:
    """Merged global+client source docs (gold) for one connector."""
    return f"{governance_source_semantic_reference_prefix(source)}/gold"


def governance_source_docs_gold_key(source: str, filename: str) -> str:
    name = filename.strip().lstrip("/")
    if not name:
        raise ValueError("filename is required")
    return f"{governance_source_docs_gold_prefix(source)}/{name}"


SILVER_ENTITY_FILENAME = "data.parquet"


def silver_entity_prefix(source: str, entity: str) -> str:
    return f"{silver_source_prefix(source)}/{entity.strip().lower()}"


def silver_entity_parquet_key(source: str, entity: str) -> str:
    return f"{silver_entity_prefix(source, entity)}/{SILVER_ENTITY_FILENAME}"


def legacy_silver_entity_parquet_key(source: str, entity: str) -> str:
    return f"{silver_source_prefix(source)}/{entity.strip().lower()}.parquet"


def raw_entity_run_prefix(source: str, run_id: str, entity: str) -> str:
    return f"{raw_source_prefix(source)}/{run_id.strip()}/{entity.strip().lower()}"


def raw_entity_parquet_key(source: str, run_id: str, entity: str) -> str:
    return f"{raw_entity_run_prefix(source, run_id, entity)}/{SILVER_ENTITY_FILENAME}"


def legacy_raw_entity_parquet_key(source: str, run_id: str, entity: str) -> str:
    return f"{raw_source_prefix(source)}/{run_id.strip()}/{entity.strip().lower()}.parquet"


def prefix_path(data_dir: Path, prefix: str, *parts: str) -> Path:
    segments = [segment for segment in prefix.strip("/").split("/") if segment]
    return data_dir.joinpath(*segments, *parts)
