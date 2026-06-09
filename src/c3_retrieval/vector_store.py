"""
C3 — Vector Store for hybrid RAG retrieval.
Embeds SourceChunks using sentence-transformers, indexes them with FAISS,
and provides semantic search with source_type hard-filtering.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

import faiss
import numpy as np

from src.schemas import SourceChunk

logger = logging.getLogger(__name__)

DEFAULT_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"


def _get_embedding_model(model_name: str):
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(model_name)


class VectorStore:
    """FAISS-backed vector store for SourceChunks."""

    def __init__(self, model_name: str = DEFAULT_MODEL_NAME):
        self._model_name = model_name
        self._model = None  # lazy-loaded
        self._index: Optional[faiss.IndexFlatIP] = None
        self._chunks: list[SourceChunk] = []
        self._dimension: int = 0

    @property
    def model(self):
        if self._model is None:
            self._model = _get_embedding_model(self._model_name)
        return self._model

    @property
    def size(self) -> int:
        return len(self._chunks)

    def _embed(self, texts: list[str]) -> np.ndarray:
        vectors = self.model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return np.asarray(vectors, dtype=np.float32)

    def build(self, chunks: list[SourceChunk]) -> None:
        """Embed and index all chunks."""
        if not chunks:
            self._chunks = []
            self._index = None
            self._dimension = 0
            return

        self._chunks = list(chunks)
        texts = [c.content for c in self._chunks]
        embeddings = self._embed(texts)
        self._dimension = embeddings.shape[1]

        self._index = faiss.IndexFlatIP(self._dimension)
        self._index.add(embeddings)
        logger.info("Built vector index: %d chunks, dim=%d", len(self._chunks), self._dimension)

    def search(
        self,
        query: str,
        top_k: int = 20,
        allowed_source_types: Optional[list[str]] = None,
    ) -> list[tuple[SourceChunk, float]]:
        """
        Return up to top_k (chunk, score) pairs ranked by cosine similarity.
        If allowed_source_types is given, only chunks matching those types are returned
        (hard filter applied post-search with over-fetching to compensate).
        """
        if self._index is None or not self._chunks:
            return []

        query_vec = self._embed([query])

        if allowed_source_types is not None:
            allowed_set = set(allowed_source_types)
            search_k = min(self._index.ntotal, top_k * 3)
        else:
            allowed_set = None
            search_k = min(self._index.ntotal, top_k)

        scores, indices = self._index.search(query_vec, search_k)

        results: list[tuple[SourceChunk, float]] = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0:
                continue
            chunk = self._chunks[idx]
            if allowed_set is not None and chunk.source_type not in allowed_set:
                continue
            results.append((chunk, float(score)))
            if len(results) >= top_k:
                break

        return results

    def save(self, directory: str | Path) -> None:
        """Persist FAISS index + chunk metadata to disk."""
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)

        if self._index is None:
            raise ValueError("No index to save — call build() first")

        faiss.write_index(self._index, str(directory / "index.faiss"))

        meta = {
            "model_name": self._model_name,
            "dimension": self._dimension,
            "chunks": [c.model_dump() for c in self._chunks],
        }
        with open(directory / "meta.json", "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False)

    def load(self, directory: str | Path) -> None:
        """Restore FAISS index + chunk metadata from disk."""
        directory = Path(directory)

        self._index = faiss.read_index(str(directory / "index.faiss"))

        with open(directory / "meta.json", encoding="utf-8") as f:
            meta = json.load(f)

        self._model_name = meta["model_name"]
        self._dimension = meta["dimension"]
        self._chunks = [SourceChunk(**d) for d in meta["chunks"]]

        if self._model is not None and self._model.get_sentence_embedding_dimension() != self._dimension:
            self._model = None
