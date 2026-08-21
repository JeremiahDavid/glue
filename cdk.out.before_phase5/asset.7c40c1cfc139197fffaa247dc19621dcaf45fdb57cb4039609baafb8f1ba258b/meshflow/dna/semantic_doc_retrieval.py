"""Embedding-based retrieval over connector docs and tenant semantic references."""

from __future__ import annotations

import json
import math
import os
import re
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Callable

from meshflow.dna.settings import DnaSettings

DEFAULT_BEDROCK_EMBED_MODEL_ID = "amazon.titan-embed-text-v2:0"
_TOKEN_RE = re.compile(r"[a-z0-9_]+")


@dataclass(frozen=True)
class DocumentChunk:
    chunk_id: str
    source: str
    title: str
    text: str
    metadata: dict[str, Any]


@dataclass
class RetrievedChunk:
    chunk: DocumentChunk
    score: float


def chunk_markdown_by_heading(text: str, *, source: str, title_prefix: str = "") -> list[DocumentChunk]:
    """Split markdown on level-2/3 headings into retrieval chunks."""
    lines = text.splitlines()
    chunks: list[DocumentChunk] = []
    current_title = title_prefix or source
    current_lines: list[str] = []
    chunk_index = 0

    def flush() -> None:
        nonlocal chunk_index, current_lines
        body = "\n".join(current_lines).strip()
        if not body:
            current_lines = []
            return
        chunk_index += 1
        chunks.append(
            DocumentChunk(
                chunk_id=f"{source}#{chunk_index}",
                source=source,
                title=current_title,
                text=body,
                metadata={"heading": current_title},
            )
        )
        current_lines = []

    for line in lines:
        if line.startswith("## ") or line.startswith("### "):
            flush()
            current_title = line.lstrip("#").strip()
            continue
        current_lines.append(line)
    flush()
    if not chunks and text.strip():
        chunks.append(
            DocumentChunk(
                chunk_id=f"{source}#1",
                source=source,
                title=title_prefix or source,
                text=text.strip(),
                metadata={},
            )
        )
    return chunks


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _tfidf_vector(tokens: list[str], idf: dict[str, float]) -> dict[str, float]:
    counts = Counter(tokens)
    total = float(sum(counts.values()) or 1)
    vector: dict[str, float] = {}
    for token, count in counts.items():
        weight = (count / total) * idf.get(token, 0.0)
        if weight:
            vector[token] = weight
    return vector


def _build_idf(chunks: list[DocumentChunk]) -> dict[str, float]:
    doc_count = max(len(chunks), 1)
    doc_freq: Counter[str] = Counter()
    for chunk in chunks:
        tokens = set(_tokenize(chunk.text))
        for token in tokens:
            doc_freq[token] += 1
    return {token: math.log((doc_count + 1) / (freq + 1)) + 1.0 for token, freq in doc_freq.items()}


def _cosine_sparse(left: dict[str, float], right: dict[str, float]) -> float:
    if not left or not right:
        return 0.0
    dot = sum(weight * right.get(token, 0.0) for token, weight in left.items())
    left_norm = math.sqrt(sum(weight * weight for weight in left.values()))
    right_norm = math.sqrt(sum(weight * weight for weight in right.values()))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return dot / (left_norm * right_norm)


def load_semantic_document_corpus(settings: DnaSettings) -> list[DocumentChunk]:
    """Load built-in connector docs plus optional tenant markdown references."""
    from meshflow.dna.semantic_knowledge_base import load_semantic_knowledge_corpus

    return load_semantic_knowledge_corpus(settings)


EmbedFn = Callable[[list[str]], list[list[float]]]


def _bedrock_embed_texts(texts: list[str], *, model_id: str) -> list[list[float]] | None:
    if not texts:
        return []
    try:
        import boto3
    except ImportError:
        return None
    try:
        client = boto3.client("bedrock-runtime")
        vectors: list[list[float]] = []
        for text in texts:
            response = client.invoke_model(
                modelId=model_id,
                body=json.dumps({"inputText": text[:8000]}),
                contentType="application/json",
                accept="application/json",
            )
            payload = json.loads(response["body"].read())
            embedding = payload.get("embedding")
            if not isinstance(embedding, list):
                return None
            vectors.append([float(value) for value in embedding])
        return vectors
    except Exception:  # noqa: BLE001 — fall back to local retrieval
        return None


def _cosine_dense(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=False))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return dot / (left_norm * right_norm)


class SemanticDocIndex:
    """In-memory semantic document index with Bedrock or TF-IDF fallback."""

    def __init__(
        self,
        chunks: list[DocumentChunk],
        *,
        embed_fn: EmbedFn | None = None,
    ) -> None:
        self.chunks = chunks
        self._idf = _build_idf(chunks)
        self._tfidf_vectors = [_tfidf_vector(_tokenize(chunk.text), self._idf) for chunk in chunks]
        self._dense_vectors: list[list[float]] | None = None
        if embed_fn and chunks:
            vectors = embed_fn([chunk.text for chunk in chunks])
            if vectors and len(vectors) == len(chunks):
                self._dense_vectors = vectors

    def retrieve(self, query: str, *, top_k: int = 4) -> list[RetrievedChunk]:
        if not self.chunks or not query.strip():
            return []
        if self._dense_vectors is not None:
            query_vectors = _bedrock_embed_texts([query], model_id=_resolve_embed_model_id())
            if query_vectors and len(query_vectors) == 1:
                scored = [
                    RetrievedChunk(chunk=chunk, score=_cosine_dense(query_vectors[0], vector))
                    for chunk, vector in zip(self.chunks, self._dense_vectors, strict=False)
                ]
                scored.sort(key=lambda item: item.score, reverse=True)
                return [item for item in scored[:top_k] if item.score > 0.05]

        query_vector = _tfidf_vector(_tokenize(query), self._idf)
        scored = [
            RetrievedChunk(chunk=chunk, score=_cosine_sparse(query_vector, vector))
            for chunk, vector in zip(self.chunks, self._tfidf_vectors, strict=False)
        ]
        scored.sort(key=lambda item: item.score, reverse=True)
        return [item for item in scored[:top_k] if item.score > 0.01]


def _resolve_embed_model_id() -> str:
    return os.getenv("MESHFLOW_BEDROCK_EMBED_MODEL_ID", DEFAULT_BEDROCK_EMBED_MODEL_ID).strip()


def _default_embed_fn(texts: list[str]) -> list[list[float]]:
    vectors = _bedrock_embed_texts(texts, model_id=_resolve_embed_model_id())
    return vectors or []


@lru_cache(maxsize=16)
def _cached_index(cache_key: str, chunks_tuple: tuple[tuple[str, str, str, str], ...]) -> SemanticDocIndex:
    chunks = [
        DocumentChunk(
            chunk_id=item[0],
            source=item[1],
            title=item[2],
            text=item[3],
            metadata={},
        )
        for item in chunks_tuple
    ]
    return SemanticDocIndex(chunks, embed_fn=_default_embed_fn)


def get_semantic_doc_index(settings: DnaSettings) -> SemanticDocIndex:
    chunks = load_semantic_document_corpus(settings)
    cache_key = f"{settings.dna_config_id}:{settings.source}"
    chunks_tuple = tuple((c.chunk_id, c.source, c.title, c.text) for c in chunks)
    return _cached_index(cache_key, chunks_tuple)


def retrieve_semantic_docs(
    settings: DnaSettings,
    query: str,
    *,
    top_k: int = 4,
) -> list[RetrievedChunk]:
    return get_semantic_doc_index(settings).retrieve(query, top_k=top_k)


def format_retrieved_chunks(chunks: list[RetrievedChunk], *, max_chars: int = 12000) -> str:
    if not chunks:
        return ""
    parts: list[str] = []
    used = 0
    for item in chunks:
        header = f"## {item.chunk.title} (source: {item.chunk.source}, score: {item.score:.2f})"
        body = item.chunk.text.strip()
        block = f"{header}\n{body}"
        if used + len(block) > max_chars:
            remaining = max_chars - used
            if remaining > 200:
                parts.append(block[:remaining] + "\n\n[truncated]")
            break
        parts.append(block)
        used += len(block) + 2
    return "\n\n---\n\n".join(parts)
