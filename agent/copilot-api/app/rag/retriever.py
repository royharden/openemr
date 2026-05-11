"""Hybrid retriever: BM25 union vector search, k=20.

Decision #5 (AgDR-0032): SQLite + sqlite-vec embedded retrieval.
Decision #6 (AgDR-0032): rank-bm25 in-process sparse retrieval.
Decision (AgDR-0078): Reciprocal Rank Fusion (RRF) for hybrid score merge.
Decision (AgDR-0080): Domain-specific filters at retrieval time.

The retriever holds an in-memory BM25Index built from the corpus on first
query.  Vector search goes to the Corpus.  Results are union-merged via RRF
and returned as a flat list of ``GuidelineChunk`` candidates (k=20 total).

The ``HybridRetriever`` is instantiated once at sidecar startup and reused;
``_bm25_index`` is rebuilt only when the corpus changes (checked via
content_hash comparison).  The metadata map (chunk_id → source_organization
+ recommendation_grade + source_year) is rebuilt at the same time and used
to apply AgDR-0080 filters at query time without a second DB roundtrip.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Sequence

from .contracts import GuidelineChunk
from .corpus import Corpus, _tokenize

logger = logging.getLogger(__name__)

# Standard RRF constant from Cormack, Clarke & Buettcher (SIGIR 2009).
# Larger values dampen the contribution of top-ranked items relative to
# tail items; 60 is the widely-cited default and the value Anthropic /
# Pinecone / Weaviate use.
RRF_K = 60

# AgDR-0080: recommendation-grade ordering. Lower is "stronger" so the
# *minimum* grade filter accepts grades alphabetically <= the threshold.
# "A" passes when min_grade="C"; "C" only passes when min_grade="C". Empty
# / None grade chunks (e.g., openFDA labels) are kept regardless because
# they aren't on the ABCD scale.
_GRADE_ORDER: dict[str, int] = {"A": 0, "B": 1, "C": 2, "D": 3}


@dataclass(frozen=True)
class RetrievalFilters:
    """Domain-specific filters applied to hybrid retrieval (AgDR-0080).

    All fields are optional; the empty filter (default) is a no-op.

    * ``source_organizations`` — accept only chunks whose
      ``source_organization`` is in this list. Case-sensitive against the
      canonical names stored in the corpus (``CDC-ACIP``, ``FDA``,
      ``ACC-AHA``, ``ADA``, ``HMS-LOE``).

    * ``min_grade`` — accept only chunks whose ``recommendation_grade`` is
      at or above the supplied letter on the A-B-C-D ordering ("A" is
      strongest). Chunks with no grade (e.g., openFDA labels) are kept;
      ungraded sources are not penalized by this filter.

    * ``year_window`` — ``(min_year, max_year)`` inclusive on
      ``source_year``. Pushed down to SQL when applied to the vector leg.
    """

    source_organizations: tuple[str, ...] | None = None
    min_grade: str | None = None
    year_window: tuple[int, int] | None = None

    def is_noop(self) -> bool:
        return (
            self.source_organizations is None
            and self.min_grade is None
            and self.year_window is None
        )


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
        # AgDR-0080: chunk_id → metadata used for post-hoc BM25 filtering.
        # Built alongside the BM25 index from the same all_rows() call so
        # the filter check is a dict lookup, not a second DB roundtrip.
        self._metadata: dict[str, dict[str, object]] = {}

    def _ensure_bm25(self) -> BM25Index:
        current_hash = self._corpus.content_hash()
        if self._bm25 is None or self._last_hash != current_hash:
            rows = self._corpus.all_rows()
            self._bm25 = BM25Index(rows)
            self._metadata = {
                row["id"]: {
                    "source_organization": row.get("source_organization"),
                    "recommendation_grade": row.get("recommendation_grade"),
                    "source_year": row.get("source_year"),
                }
                for row in rows
            }
            self._last_hash = current_hash
            logger.debug("BM25 index rebuilt (%d chunks)", len(rows))
        return self._bm25

    def _passes_filters(
        self, chunk_id: str, filters: RetrievalFilters
    ) -> bool:
        """Apply AgDR-0080 filters using the cached metadata map."""
        if filters.is_noop():
            return True
        meta = self._metadata.get(chunk_id)
        if meta is None:
            # Unknown chunk — should not happen for BM25 hits, but if it
            # does we fall back to "let it through" since the vector leg
            # already filtered at SQL time.
            return True
        if filters.source_organizations is not None:
            if meta.get("source_organization") not in filters.source_organizations:
                return False
        if filters.min_grade is not None:
            grade = meta.get("recommendation_grade")
            if isinstance(grade, str) and grade in _GRADE_ORDER:
                if _GRADE_ORDER[grade] > _GRADE_ORDER[filters.min_grade]:
                    return False
            # Ungraded chunks (openFDA, CDC-ACIP) bypass the grade filter.
        if filters.year_window is not None:
            year = meta.get("source_year")
            if isinstance(year, int):
                lo, hi = filters.year_window
                if year < lo or year > hi:
                    return False
        return True

    def query(
        self,
        text: str,
        k: int = 20,
        *,
        filters: RetrievalFilters | None = None,
    ) -> list[GuidelineChunk]:
        """Return up to *k* candidate chunks (BM25 ∪ vector).

        AgDR-0080: when ``filters`` is supplied, BM25 hits are filtered
        post-hoc against the cached metadata map and vector hits are
        filtered at the SQL layer (pushed down to ``vector_candidates``).
        Both legs request the FULL ``half_k`` pool first so that filtering
        does not silently shrink the candidate count below the eval-case
        ``min_candidates: 1`` floor on tight queries.
        """
        filters = filters or RetrievalFilters()
        half_k = k // 2

        # --- BM25 leg ---
        bm25_index = self._ensure_bm25()
        bm25_raw = bm25_index.query(text, half_k)
        bm25_hits: dict[str, float] = {
            cid: score
            for cid, score in bm25_raw
            if self._passes_filters(cid, filters)
        }

        # --- Vector leg ---
        vec_hits: dict[str, float] = {}
        if self._embedder is not None:
            try:
                q_vec = self._embedder.embed_one(text)
                vec_kwargs: dict[str, object] = {}
                if filters.source_organizations is not None:
                    vec_kwargs["source_organizations"] = list(
                        filters.source_organizations
                    )
                if filters.year_window is not None:
                    vec_kwargs["year_window"] = filters.year_window
                for chunk_id, score in self._corpus.vector_candidates(
                    q_vec, half_k, **vec_kwargs  # type: ignore[arg-type]
                ):
                    # min_grade still needs the metadata-map check because
                    # grade ordering is application-level, not SQL-level.
                    if filters.min_grade is not None and not self._passes_filters(
                        chunk_id, RetrievalFilters(min_grade=filters.min_grade)
                    ):
                        continue
                    vec_hits[chunk_id] = score
            except Exception as exc:
                logger.warning("Vector search failed (%s) — BM25 only", exc)

        # --- Reciprocal Rank Fusion (AgDR-0078) ---
        # BM25 scores (TF-IDF-ish, unbounded positive) and vector cosine
        # scores (roughly [-1, 1]) live on incompatible scales — taking
        # max() across them gave whichever modality had the more aggressive
        # tail too much weight. RRF discards raw scores, ranks each modality
        # independently, and sums 1/(K + rank) contributions. Chunks that
        # appear in BOTH legs naturally outrank single-modality chunks
        # because they accumulate two RRF terms.
        fused: dict[str, float] = {}
        bm25_ranked = sorted(bm25_hits.items(), key=lambda x: x[1], reverse=True)
        for rank, (cid, _score) in enumerate(bm25_ranked):
            fused[cid] = fused.get(cid, 0.0) + 1.0 / (RRF_K + rank + 1)
        vec_ranked = sorted(vec_hits.items(), key=lambda x: x[1], reverse=True)
        for rank, (cid, _score) in enumerate(vec_ranked):
            fused[cid] = fused.get(cid, 0.0) + 1.0 / (RRF_K + rank + 1)

        ranked = sorted(fused.items(), key=lambda x: x[1], reverse=True)[:k]

        chunks: list[GuidelineChunk] = []
        for chunk_id, _ in ranked:
            chunk = self._corpus.get_chunk(chunk_id)
            if chunk is None:
                continue
            chunk.bm25_score = bm25_hits.get(chunk_id)
            chunk.vector_score = vec_hits.get(chunk_id)
            chunks.append(chunk)

        return chunks
