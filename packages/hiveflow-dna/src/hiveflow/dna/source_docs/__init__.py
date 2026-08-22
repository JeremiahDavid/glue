"""Connector source documentation — global MS Learn catalogs and per-client gold merge."""

from meshflow.dna.source_docs.gold import run_source_docs_gold_job
from meshflow.dna.source_docs.reference import (
    GOLD_ARTIFACTS,
    GOLD_BUILD_SOURCES,
    load_source_docs_gold,
    load_source_docs_gold_artifact,
    normalize_reference_source,
    source_docs_gold_key,
    source_supports_gold_build,
)
from meshflow.dna.source_docs.scrape import (
    DEFAULT_SOURCE,
    DEFAULT_SOURCE_DOCS_BUCKET,
    build_source_properties_catalog,
    catalog_to_yaml,
    extract_entity_properties_doc,
    run_source_docs_scrape_job,
    scrape_ms_learn_entity_pages,
    slug_to_silver_entity,
    source_docs_bucket_name,
    source_docs_object_key,
    source_docs_relationships_object_key,
    source_docs_tags_object_key,
    source_docs_uri,
)

__all__ = [
    "DEFAULT_SOURCE",
    "DEFAULT_SOURCE_DOCS_BUCKET",
    "build_source_properties_catalog",
    "catalog_to_yaml",
    "extract_entity_properties_doc",
    "GOLD_ARTIFACTS",
    "GOLD_BUILD_SOURCES",
    "load_source_docs_gold",
    "load_source_docs_gold_artifact",
    "normalize_reference_source",
    "run_source_docs_gold_job",
    "run_source_docs_scrape_job",
    "scrape_ms_learn_entity_pages",
    "slug_to_silver_entity",
    "source_docs_bucket_name",
    "source_docs_gold_key",
    "source_docs_object_key",
    "source_docs_relationships_object_key",
    "source_docs_tags_object_key",
    "source_docs_uri",
    "source_supports_gold_build",
]
