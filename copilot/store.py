"""Vector store (Chroma, on disk) + local embeddings (fastembed, ONNX, CPU)."""
from __future__ import annotations

from functools import lru_cache

import chromadb

from . import config


@lru_cache(maxsize=1)
def _embedder():
    from fastembed import TextEmbedding
    return TextEmbedding(config.EMBED_MODEL, cache_dir=config.MODEL_CACHE)


def embed(texts: list[str]) -> list[list[float]]:
    return [v.tolist() for v in _embedder().embed(texts)]


def embed_query(q: str) -> list[float]:
    # bge models recommend a query instruction prefix for retrieval
    return _embedder().query_embed(q).__next__().tolist()


@lru_cache(maxsize=1)
def _client():
    config.CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(config.CHROMA_DIR))


def get_collection(reset: bool = False):
    client = _client()
    if reset:
        try:
            client.delete_collection(config.COLLECTION)
        except Exception:
            pass
    return client.get_or_create_collection(config.COLLECTION, metadata={"hnsw:space": "cosine"})
