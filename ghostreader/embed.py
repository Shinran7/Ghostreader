"""Unified embedding interface for Ghostreader.

Supports three backends:
    - **sentence-transformers** (default): local, no API key, ``all-MiniLM-L6-v2``
    - **OpenAI**: ``openai:<model>`` (e.g. ``openai:text-embedding-3-small``)
    - **stub**: deterministic hash-based vectors for testing
"""

from __future__ import annotations

import hashlib
import logging
from functools import lru_cache
from typing import Protocol

logger = logging.getLogger(__name__)

# Default model aligns with _EMBED_DIM=384 in indexer/chat.
DEFAULT_MODEL = "all-MiniLM-L6-v2"
_STUB_DIM = 384


class Embedder(Protocol):
    """Minimal embedding interface."""

    @property
    def dimension(self) -> int: ...

    def embed(self, texts: list[str]) -> list[list[float]]: ...


# ── Factory ──────────────────────────────────────────────────────────


def get_embedder(model: str = DEFAULT_MODEL) -> Embedder:
    """Return an Embedder for the given model string.

    Accepted formats:
        ``all-MiniLM-L6-v2``        → SentenceTransformer
        ``openai:text-embedding-3-small`` → OpenAI embeddings
        ``stub``                     → deterministic hash embeddings
    """
    if model == "stub":
        return StubEmbedder()

    if model.startswith("openai:"):
        openai_model = model.split(":", 1)[1]
        return _make_openai_embedder(openai_model)

    return _make_st_embedder(model)


# ── Sentence-Transformers ────────────────────────────────────────────


class SentenceTransformerEmbedder:
    """Wraps a sentence-transformers model."""

    def __init__(self, model_name: str) -> None:
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(model_name)
        self._dimension = self._model.get_embedding_dimension()

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed(self, texts: list[str]) -> list[list[float]]:
        embeddings = self._model.encode(texts, show_progress_bar=False)
        return [vec.tolist() for vec in embeddings]


@lru_cache(maxsize=1)
def _make_st_embedder(model_name: str) -> Embedder:
    """Cached factory — avoids reloading the model."""
    try:
        return SentenceTransformerEmbedder(model_name)
    except Exception as exc:
        logger.warning(
            "Could not load sentence-transformers model '%s': %s. Falling back to stub.",
            model_name, exc,
        )
        return StubEmbedder()


# ── OpenAI ───────────────────────────────────────────────────────────


class OpenAIEmbedder:
    """Wraps the OpenAI embeddings API via langchain-openai."""

    def __init__(self, model_name: str) -> None:
        from langchain_openai import OpenAIEmbeddings

        self._model = OpenAIEmbeddings(model=model_name)
        # OpenAI text-embedding-3-small produces 1536-dim by default.
        self._dimension = 1536

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self._model.embed_documents(texts)


def _make_openai_embedder(model_name: str) -> Embedder:
    try:
        return OpenAIEmbedder(model_name)
    except Exception as exc:
        logger.warning(
            "Could not initialize OpenAI embeddings '%s': %s. Falling back to stub.",
            model_name, exc,
        )
        return StubEmbedder()


# ── Stub (testing) ───────────────────────────────────────────────────


class StubEmbedder:
    """Deterministic hash-based embeddings for pipeline testing."""

    @property
    def dimension(self) -> int:
        return _STUB_DIM

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [_stub_embed(t) for t in texts]


def _stub_embed(text: str) -> list[float]:
    """Deterministic stub embedding — hash-based, normalized to [-1, 1]."""
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    values: list[float] = []
    for i in range(_STUB_DIM):
        byte_val = digest[i % len(digest)]
        values.append((byte_val / 255.0) * 2.0 - 1.0)
    return values


__all__ = [
    "DEFAULT_MODEL",
    "Embedder",
    "OpenAIEmbedder",
    "SentenceTransformerEmbedder",
    "StubEmbedder",
    "get_embedder",
]
