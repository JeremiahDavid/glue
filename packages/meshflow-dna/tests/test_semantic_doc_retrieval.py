"""Tests for semantic document retrieval."""

from __future__ import annotations

from pathlib import Path

import pytest

from meshflow.dna.init_client import init_client_governance
from meshflow.dna.semantic_doc_retrieval import (
    SemanticDocIndex,
    chunk_markdown_by_heading,
    load_semantic_document_corpus,
    retrieve_semantic_docs,
)
from meshflow.dna.semantic_model import ensure_semantic_model_seed
from meshflow.dna.settings import DnaSettings
from meshflow.dna.store import write_text_artifact
from meshflow.storage.paths import governance_semantic_docs_prefix


@pytest.fixture
def seeded_settings(tmp_path: Path) -> DnaSettings:
    settings = DnaSettings(source="dbc", data_dir=tmp_path, company="POC")
    init_client_governance(settings, company="POC")
    ensure_semantic_model_seed(settings)
    return settings


def test_chunk_markdown_by_heading_splits_sections() -> None:
    text = "# Root\n\nIntro\n\n## Sales invoices\n\nInvoice headers.\n\n## Customers\n\nCustomer master."
    chunks = chunk_markdown_by_heading(text, source="test.md")
    assert len(chunks) >= 2
    assert any("Invoice headers" in chunk.text for chunk in chunks)


def test_retrieve_semantic_docs_prefers_relevant_section(seeded_settings: DnaSettings) -> None:
    key = f"{governance_semantic_docs_prefix(seeded_settings.dna_config_id)}/revenue.md"
    write_text_artifact(
        seeded_settings,
        key,
        "## Sales invoice lines\n\nNet amount and posting date on invoice line revenue.",
    )
    results = retrieve_semantic_docs(
        seeded_settings,
        "sales invoice lines net amount revenue posting date",
        top_k=3,
    )
    assert results
    joined = " ".join(item.chunk.text.lower() for item in results)
    assert "invoice" in joined or "sales" in joined


def test_tenant_docs_are_indexed(seeded_settings: DnaSettings) -> None:
    key = f"{governance_semantic_docs_prefix(seeded_settings.dna_config_id)}/custom.md"
    write_text_artifact(
        seeded_settings,
        key,
        "## Custom metric\n\nUse backlogAmount for open order value.",
    )
    index = SemanticDocIndex(load_semantic_document_corpus(seeded_settings))
    results = index.retrieve("backlog amount open orders", top_k=2)
    assert any("backlogAmount" in item.chunk.text for item in results)
