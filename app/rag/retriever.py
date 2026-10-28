"""Reads the pre-built ChromaDB folder (chroma_store/) and searches it. Read-only at runtime."""
import os

import chromadb

from app.core.config import settings
from app.rag.embeddings import get_embedder

_client = None


def _get_client():
    global _client
    if _client is None:
        if not os.path.isdir(settings.CHROMA_DIR):
            raise FileNotFoundError("chroma_store/ not found. Run: python scripts/ingest.py")
        _client = chromadb.PersistentClient(path=settings.CHROMA_DIR)
    return _client


def get_collection():
    # embedding_function=None: we always pass our own (Gemini) vectors
    return _get_client().get_collection(settings.RAG_COLLECTION, embedding_function=None)


def count_chunks() -> int:
    try:
        return get_collection().count()
    except Exception:
        return 0


def search(query: str, k: int | None = None) -> list[dict]:
    """Returns the top-k chunks: [{'text', 'metadata', 'score'}], best first. score = cosine similarity."""
    k = k or settings.RAG_TOP_K
    query_vec = get_embedder().embed_query(query)
    res = get_collection().query(
        query_embeddings=[query_vec],
        n_results=k,
        include=["documents", "metadatas", "distances"],
    )
    results = []
    for doc, meta, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0]):
        results.append({"text": doc, "metadata": meta, "score": round(1.0 - float(dist), 4)})
    return results


def is_confident(results: list[dict]) -> bool:
    """False => the Procedure Guide agent must say 'I do not know' instead of guessing."""
    return bool(results) and results[0]["score"] >= settings.RAG_MIN_SCORE
