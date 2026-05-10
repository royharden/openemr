"""Reranker: Cohere Rerank 3.5 primary; local cross-encoder fallback.

Decision #8 (AgDR-0034): Cohere Rerank 3.5 trial (1k calls/month — forbids
commercial use; README documents this caveat).

Fallback trigger conditions:
  - ``COHERE_API_KEY`` absent / empty
  - ``COPILOT_EVAL_MODE=1`` (deterministic mock via ``_eval_mocks.py``)
  - Cohere raises an exception during the rerank call

Fallback model: ``cross-encoder/ms-marco-MiniLM-L-6-v2`` from
sentence-transformers.  This is a tiny (22 MB) model and fast on CPU.
"""

from __future__ import annotations

import logging
import os
from typing import Sequence

from .contracts import GuidelineChunk

logger = logging.getLogger(__name__)

TOP_N = 5
COHERE_MODEL = "rerank-v3.5"
LOCAL_CROSS_ENCODER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"


class CohereReranker:
    """Cohere Rerank 3.5 with local cross-encoder fallback.

    The fallback is seamlessly activated on Cohere outage.  The returned
    chunks carry ``reranker="cohere"`` or ``reranker="fallback"`` so the
    verifier can distinguish the two paths.
    """

    def __init__(
        self,
        api_key: str | None = None,
        top_n: int = TOP_N,
    ) -> None:
        self._api_key = api_key or os.environ.get("COHERE_API_KEY", "")
        self._top_n = top_n
        self._local_model: object | None = None  # lazy-loaded

    def rerank(
        self, query: str, candidates: list[GuidelineChunk]
    ) -> list[GuidelineChunk]:
        """Return top-N chunks ordered by relevance score."""
        if not candidates:
            return []

        if os.environ.get("COPILOT_EVAL_MODE") == "1":
            from ._eval_mocks import EvalReranker
            return EvalReranker(top_n=self._top_n).rerank(query, candidates)

        if self._api_key:
            try:
                return self._cohere_rerank(query, candidates)
            except Exception as exc:
                logger.warning(
                    "Cohere rerank failed (%s) — using local cross-encoder fallback", exc
                )

        return self._local_rerank(query, candidates)

    def _cohere_rerank(
        self, query: str, candidates: list[GuidelineChunk]
    ) -> list[GuidelineChunk]:
        import cohere  # type: ignore[import]

        client = cohere.Client(api_key=self._api_key)
        docs = [c.text for c in candidates]
        response = client.rerank(
            model=COHERE_MODEL,
            query=query,
            documents=docs,
            top_n=self._top_n,
        )
        results: list[GuidelineChunk] = []
        for i, result in enumerate(response.results):
            chunk = candidates[result.index].model_copy()
            chunk.rerank_score = result.relevance_score
            chunk.rerank_position = i
            chunk.reranker = "cohere"
            results.append(chunk)
        return results

    def _local_rerank(
        self, query: str, candidates: list[GuidelineChunk]
    ) -> list[GuidelineChunk]:
        try:
            from sentence_transformers import CrossEncoder  # type: ignore[import]
        except ImportError:
            logger.error("sentence-transformers not installed — returning BM25/vec order")
            top = candidates[: self._top_n]
            for i, c in enumerate(top):
                c.rerank_score = 1.0 - (i / len(top))
                c.rerank_position = i
                c.reranker = "fallback"
            return top

        if self._local_model is None:
            logger.info("Loading local cross-encoder %s", LOCAL_CROSS_ENCODER_MODEL)
            self._local_model = CrossEncoder(LOCAL_CROSS_ENCODER_MODEL)

        pairs = [(query, c.text) for c in candidates]
        scores = self._local_model.predict(pairs)  # type: ignore[attr-defined]

        ranked = sorted(
            zip(candidates, scores), key=lambda x: x[1], reverse=True
        )

        results: list[GuidelineChunk] = []
        for i, (chunk, score) in enumerate(ranked[: self._top_n]):
            chunk = chunk.model_copy()
            chunk.rerank_score = float(score)
            chunk.rerank_position = i
            chunk.reranker = "fallback"
            results.append(chunk)
        return results
