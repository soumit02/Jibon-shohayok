"""
Embeddings through the Gemini API (REST), so the server needs NO local model (bge-m3 is 2.3 GB).

IMPORTANT: the SAME model + dimension must be used for ingest.py (index) and for queries (runtime).
If you change EMBED_MODEL or EMBED_DIM you must run scripts/ingest.py again.
"""
import math
import time

import httpx

from app.core.config import settings

API_BASE = "https://generativelanguage.googleapis.com/v1beta"


class EmbeddingError(RuntimeError):
    pass


def _normalize(vec: list[float]) -> list[float]:
    # Gemini returns un-normalized vectors when output dimension < 3072, so we normalize ourselves
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


class GeminiEmbedder:
    def __init__(self, api_key: str | None = None, model: str | None = None, dim: int | None = None):
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.model = model or settings.EMBED_MODEL
        self.dim = dim or settings.EMBED_DIM
        self._query_cache: dict[str, list[float]] = {}

    def _call(self, texts: list[str], task_type: str) -> list[list[float]]:
        if not self.api_key:
            raise EmbeddingError("GEMINI_API_KEY is missing in the environment.")

        url = f"{API_BASE}/models/{self.model}:batchEmbedContents"
        payload = {
            "requests": [
                {
                    "model": f"models/{self.model}",
                    "content": {"parts": [{"text": t}]},
                    "taskType": task_type,
                    "outputDimensionality": self.dim,
                }
                for t in texts
            ]
        }
        headers = {"x-goog-api-key": self.api_key, "Content-Type": "application/json"}

        last_problem = "unknown error"
        for attempt in range(1, 6):
            try:
                resp = httpx.post(url, json=payload, headers=headers, timeout=60)
            except httpx.HTTPError as exc:
                last_problem = f"network error: {exc}"
                time.sleep(min(30, 3 * attempt))
                continue

            if resp.status_code == 429 or resp.status_code >= 500:  # rate limit / server problem -> wait, retry
                last_problem = f"HTTP {resp.status_code}: {resp.text[:200]}"
                time.sleep(min(60, 8 * attempt))
                continue
            if resp.status_code != 200:
                raise EmbeddingError(f"Gemini embedding error {resp.status_code}: {resp.text[:400]}")

            data = resp.json()
            return [_normalize(item["values"]) for item in data["embeddings"]]

        raise EmbeddingError(f"Gemini embedding failed after retries ({last_problem})")

    # ---------- public API ----------
    def embed_query(self, text: str) -> list[float]:
        text = text.strip()
        if text in self._query_cache:
            return self._query_cache[text]
        vec = self._call([text], "RETRIEVAL_QUERY")[0]
        if len(self._query_cache) > 256:
            self._query_cache.clear()
        self._query_cache[text] = vec
        return vec

    def embed_documents(self, texts: list[str], batch_size: int = 20) -> list[list[float]]:
        """Embeds many chunks while staying under the free-tier tokens-per-minute limit."""
        vectors: list[list[float]] = []
        tokens_per_second = max(settings.EMBED_TPM_BUDGET / 60.0, 1.0)
        for start in range(0, len(texts), batch_size):
            batch = texts[start:start + batch_size]
            vectors.extend(self._call(batch, "RETRIEVAL_DOCUMENT"))
            # rough token estimate: Bangla needs ~1 token per 2 characters (conservative)
            est_tokens = sum(len(t) for t in batch) / 2
            time.sleep(est_tokens / tokens_per_second)
            print(f"   embedded {min(start + batch_size, len(texts))}/{len(texts)} chunks")
        return vectors


_embedder: GeminiEmbedder | None = None


def get_embedder() -> GeminiEmbedder:
    global _embedder
    if _embedder is None:
        _embedder = GeminiEmbedder()
    return _embedder
