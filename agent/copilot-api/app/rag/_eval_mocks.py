"""Deterministic vendor mocks for COPILOT_EVAL_MODE=1.

Decision #19 (AgDR-0042): vendor boundaries (Voyage, Cohere) must be mocked
in eval/CI mode so vendor outages cannot block PR merges.

These mocks produce stable, hash-derived outputs so:
  - The same input always yields the same output (deterministic).
  - Different inputs yield different outputs (discriminative).
  - No network calls are made.

Team C imports ``EvalEmbedder`` and ``EvalReranker`` from here via the
eval runner when ``COPILOT_EVAL_MODE=1``.

Cache-key contract (§15.5.9)
------------------------------
The mock cache key must include:
  - text content hash (SHA-256[:16])
  - mock version constant (bump when mock behavior changes)

Bumping ``MOCK_VERSION`` invalidates the deterministic cache for all
cases — use when the mock logic changes semantically.
"""

from __future__ import annotations

import hashlib

from .contracts import GuidelineChunk

MOCK_VERSION = "v1"
MOCK_DIM = 16  # small fixed dimension for tests — real dim is 1024


def _text_hash(text: str) -> str:
    return hashlib.sha256(
        (MOCK_VERSION + "|" + text).encode()
    ).hexdigest()


def _hash_to_vector(text: str, dim: int = MOCK_DIM) -> list[float]:
    """Produce a deterministic unit-ish float vector from text.

    Uses byte values mapped linearly to [-1, 1] to avoid NaN/Inf from raw
    float32 unpacking of arbitrary byte sequences.
    """
    digest = hashlib.sha256((MOCK_VERSION + "|" + text).encode()).digest()
    # Repeat digest bytes to cover dim values.
    repeated = (digest * ((dim // len(digest)) + 1))[:dim]
    # Map each byte [0, 255] to [-1, 1].
    raw = [(b - 127.5) / 127.5 for b in repeated]
    # Normalise to unit vector.
    mag = (sum(v * v for v in raw) ** 0.5) or 1.0
    return [v / mag for v in raw]


class EvalEmbedder:
    """Deterministic embedder — returns fixed vectors per text hash."""

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [_hash_to_vector(t, MOCK_DIM) for t in texts]

    def embed_one(self, text: str) -> list[float]:
        return _hash_to_vector(text, MOCK_DIM)


class EvalReranker:
    """Deterministic reranker — ranks by hash value (stable, not random)."""

    def __init__(self, top_n: int = 5) -> None:
        self._top_n = top_n

    def rerank(
        self, query: str, candidates: list[GuidelineChunk]
    ) -> list[GuidelineChunk]:
        query_hash = _text_hash(query)

        def _score(chunk: GuidelineChunk) -> float:
            combined = (query_hash + "|" + chunk.chunk_id)
            digest = hashlib.sha256(combined.encode()).digest()
            return int.from_bytes(digest[:4], "big") / 0xFFFFFFFF

        ranked = sorted(candidates, key=_score, reverse=True)[: self._top_n]
        results: list[GuidelineChunk] = []
        for i, chunk in enumerate(ranked):
            chunk = chunk.model_copy()
            chunk.rerank_score = _score(chunk)
            chunk.rerank_position = i
            chunk.reranker = "fallback"
            results.append(chunk)
        return results
