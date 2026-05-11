"""RAG package — hybrid retrieval over the bundled guideline corpus.

Workstream B (wk2-team-b-rag) implements:
  - corpus.py       — SQLite + sqlite-vec chunk store
  - chunker.py      — section-boundary chunker
  - embedder.py     — Voyage voyage-4-large (OpenAI fallback)
  - retriever.py    — HybridRetriever (BM25 + vector union, k=20)
  - reranker.py     — CohereReranker (local cross-encoder fallback)
  - ingestion/      — CDC ACIP, openFDA, HMS-LOE ingestors
  - _eval_mocks.py  — EvalEmbedder, EvalReranker for COPILOT_EVAL_MODE=1
  - phi_filter.py   — strip_phi() helper for query sanitisation
"""

import logging
import os
from pathlib import Path

from .contracts import GuidelineChunk, RecommendationGrade, SourceOrganization
from .corpus import DEFAULT_CORPUS_PATH, Corpus
from .phi_filter import strip_phi
from .retriever import HybridRetriever

logger = logging.getLogger(__name__)

CANDIDATE_POOL_K = 20


_FALLBACK_CHUNKS = [
    GuidelineChunk(
        chunk_id="fallback:cdc-acip:adult-immunization",
        source_id="cdc-acip-adult-immunization",
        source_organization="CDC-ACIP",
        source_name="Adult Immunization Schedule",
        page_or_section="General adult immunization guidance",
        text="Adults should be assessed for recommended vaccines at clinical encounters using age, risk factors, and immunization history.",
        recommendation_grade="A",
        source_year=2026,
        bm25_score=0.1,
        reranker="fallback",
    ),
    GuidelineChunk(
        chunk_id="fallback:hms-loe:abnormal-labs",
        source_id="hms-loe-abnormal-labs",
        source_organization="HMS-LOE",
        source_name="Clinical Evidence Review",
        page_or_section="Abnormal laboratory follow-up",
        text="Abnormal laboratory values should be interpreted against the reference range, prior trend, and clinical context before action is taken.",
        recommendation_grade="2b",
        source_year=2026,
        bm25_score=0.1,
        reranker="fallback",
    ),
    GuidelineChunk(
        chunk_id="fallback:fda:medication-safety",
        source_id="fda-medication-safety",
        source_organization="FDA",
        source_name="Medication Safety Labeling",
        page_or_section="Medication safety review",
        text="Medication review should consider active medications, allergies, recent labs, and patient-specific safety warnings.",
        recommendation_grade=None,
        source_year=2026,
        bm25_score=0.1,
        reranker="fallback",
    ),
]


def _fallback_retrieve(query: str, top_k: int) -> list[GuidelineChunk]:
    tokens = {t.lower() for t in query.replace("-", " ").split() if t}

    def score(chunk: GuidelineChunk) -> int:
        text = f"{chunk.source_name} {chunk.page_or_section} {chunk.text}".lower()
        return sum(1 for token in tokens if token in text)

    ranked = sorted(_FALLBACK_CHUNKS, key=score, reverse=True)
    return [chunk.model_copy() for chunk in ranked[:top_k]]


def retrieve_guidelines(query: str, top_k: int = 5) -> list[GuidelineChunk]:
    """Retrieve guideline chunks via hybrid BM25 + vector retrieval + reranker.

    Pipeline (AgDR-0062 — restores live path to design intent of AgDR-0032/0033/0034):
      1. ``strip_phi(query)`` — sanitize before any retrieval.
      2. ``HybridRetriever(corpus, embedder=get_embedder())`` — BM25 ∪ vector
         candidates, k=``CANDIDATE_POOL_K`` (20).
      3. ``CohereReranker().rerank(...)`` — Cohere Rerank 3.5 (or local
         cross-encoder fallback) trims the pool to top_k.

    Each stage degrades gracefully:
      - Embedder init failure → log + BM25-only retrieval (vector leg disabled).
      - Reranker failure → log + return retriever order truncated to top_k.
      - Corpus unavailable → fallback chunks (or raise if
        ``COPILOT_RAG_REQUIRE_CORPUS=1``).
    """

    sanitized_query = strip_phi(query)
    corpus_path = Path(os.getenv("COPILOT_RAG_CORPUS_PATH", str(DEFAULT_CORPUS_PATH)))
    if corpus_path.exists():
        try:
            embedder = None
            try:
                from .embedder import get_embedder

                embedder = get_embedder()
            except Exception as exc:  # noqa: BLE001 — best-effort init
                logger.warning(
                    "Embedder init failed (%s) — BM25-only retrieval for this query",
                    exc,
                )

            with Corpus(corpus_path) as corpus:
                retriever = HybridRetriever(corpus, embedder=embedder)
                candidates = retriever.query(sanitized_query, k=CANDIDATE_POOL_K)
                if not candidates:
                    return []

                try:
                    from .reranker import CohereReranker

                    reranker = CohereReranker(top_n=top_k)
                    return reranker.rerank(sanitized_query, candidates)
                except Exception as exc:  # noqa: BLE001 — best-effort rerank
                    logger.warning(
                        "Reranker failed (%s) — returning hybrid-retriever order", exc
                    )
                    return candidates[:top_k]
        except Exception:
            if os.getenv("COPILOT_RAG_REQUIRE_CORPUS") == "1":
                raise

    if os.getenv("COPILOT_RAG_REQUIRE_CORPUS") == "1":
        raise RuntimeError(f"RAG corpus unavailable at {corpus_path}")

    return _fallback_retrieve(sanitized_query, max(top_k, 1))

__all__ = [
    "GuidelineChunk",
    "RecommendationGrade",
    "SourceOrganization",
    "retrieve_guidelines",
    "strip_phi",
]
