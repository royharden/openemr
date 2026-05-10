"""Hybrid retriever: BM25 union vector search, k=20.

Decision #5 (AgDR-0032): SQLite + sqlite-vec embedded retrieval.
Decision #6 (AgDR-0032): rank-bm25 in-process sparse retrieval.

The retriever holds an in-memory BM25Index built from the corpus on first
query.  Vector search goes to the Corpus.  Results are union-merged and
returned as a flat list of ``GuidelineChunk`` candidates (k=20 total).

The ``HybridRetriever`` is instantiated once at sidecar startup and reused;
``_bm25_index`` is rebuilt only when the corpus changes (checked via
content_hash comparison).
"""

from __future__ import annotations

import logging
import re
from typing import Sequence

from .contracts import GuidelineChunk
from .corpus import Corpus, _tokenize

logger = logging.getLogger(__name__)


class BM25Index:
    """Thin wrapper around rank_bm25.BM25Okapi."""

    def __init__(self, rows: list[dict]) -> None:
        from rank_bm25 import BM25Okapi  # type: ignore[import]

        self._ids = [r["id"] for r in rows]
        tokenized = [r["bm25_terms"].split() for r in rows]
        self._bm25 = BM25Okapi(tokenized) if tokenized else None

    def query(self, text: str, k: int) -> list[tuple[str, float]]:
        if self._bm25 is None:
            return []
        tokens = _tokenize(text).split()
        if not tokens:
            return []
        scores = self._bm25.get_scores(tokens)
        indexed = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
        return [
            (self._ids[i], float(score))
            for i, score in indexed[:k]
            if score > 0.0
        ]


class HybridRetriever:
    """Union of BM25 + vector candidates, deduped, returning k=20 chunks."""

    def __init__(self, corpus: Corpus, embedder: object | None = None) -> None:
        self._corpus = corpus
        self._embedder = embedder
        self._bm25: BM25Index | None = None
        self._last_hash: str | None = None

    def _ensure_bm25(self) -> BM25Index:
        current_hash = self._corpus.content_hash()
        if self._bm25 is None or self._last_hash != current_hash:
            rows = self._corpus.all_rows()
            self._bm25 = BM25Index(rows)
            self._last_hash = current_hash
            logger.debug("BM25 index rebuilt (%d chunks)", len(rows))
        return self._bm25

    def query(self, text: str, k: int = 20) -> list[GuidelineChunk]:
        """Return up to *k* candidate chunks (BM25 ∪ vector)."""
        half_k = k // 2

        # --- BM25 leg ---
        bm25_index = self._ensure_bm25()
        bm25_hits: dict[str, float] = dict(bm25_index.query(text, half_k))

        # --- Vector leg ---
        vec_hits: dict[str, float] = {}
        if self._embedder is not None:
            try:
                q_vec = self._embedder.embed_one(text)
                for chunk_id, score in self._corpus.vector_candidates(q_vec, half_k):
                    vec_hits[chunk_id] = score
            except Exception as exc:
                logger.warning("Vector search failed (%s) — BM25 only", exc)

        # --- Union (max score wins for dedup) ---
        all_ids: dict[str, float] = {}
        for cid, score in bm25_hits.items():
            all_ids[cid] = max(all_ids.get(cid, 0.0), score)
        for cid, score in vec_hits.items():
            all_ids[cid] = max(all_ids.get(cid, 0.0), score)

        ranked = sorted(all_ids.items(), key=lambda x: x[1], reverse=True)[:k]

        chunks: list[GuidelineChunk] = []
        for chunk_id, _ in ranked:
            chunk = self._corpus.get_chunk(chunk_id)
            if chunk is None:
                continue
            chunk.bm25_score = bm25_hits.get(chunk_id)
            chunk.vector_score = vec_hits.get(chunk_id)
            chunks.append(chunk)

        return chunks
