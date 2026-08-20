"""Local embedding + cross-encoder rerank wrappers (no per-query API cost)."""

from __future__ import annotations

import functools
import os

import numpy as np

from . import config


@functools.cache
def _embedder():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(config.EMBED_MODEL)


@functools.cache
def _reranker():
    from sentence_transformers import CrossEncoder

    name = (
        config.RERANK_MODEL_QUALITY
        if os.environ.get("FACTPACK_RERANKER") == "quality"
        else config.RERANK_MODEL
    )
    return CrossEncoder(name)


def embed_passages(texts: list[str], batch_size: int = 64) -> np.ndarray:
    return _embedder().encode(
        texts, batch_size=batch_size, normalize_embeddings=True, show_progress_bar=False
    ).astype(np.float32)


def embed_query(query: str) -> np.ndarray:
    return _embedder().encode(
        [config.EMBED_QUERY_PREFIX + query], normalize_embeddings=True, show_progress_bar=False
    ).astype(np.float32)[0]


def rerank(query: str, passages: list[str]) -> np.ndarray:
    """-> relevance scores aligned with passages"""
    return np.asarray(_reranker().predict([(query, p) for p in passages], show_progress_bar=False))
