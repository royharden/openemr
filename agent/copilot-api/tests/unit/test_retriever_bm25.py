"""L1: BM25 retriever unit tests.

Uses an in-memory Corpus backed by :memory: SQLite.
Tests positive (hit), negative (no match), and edge cases (empty corpus,
empty query, query with stop words).

Plan §15.5.6 — positive/negative/edge per rule.
"""

from __future__ import annotations

import pytest

from app.rag.corpus import Corpus
from app.rag.contracts import GuidelineChunk
from app.rag.retriever import BM25Index, HybridRetriever


def _make_chunk(chunk_id: str, text: str, org: str = "CDC-ACIP") -> GuidelineChunk:
    return GuidelineChunk(
        chunk_id=chunk_id,
        source_id=f"src-{chunk_id}",
        source_organization=org,
        source_name="Test Source",
        page_or_section="§test",
        text=text,
        recommendation_grade=None,
        source_year=2024,
    )


@pytest.fixture
def mem_corpus() -> Corpus:
    corpus = Corpus(path=":memory:")
    corpus.open()
    corpus.ensure_schema()
    return corpus


@pytest.fixture
def populated_corpus(mem_corpus: Corpus) -> Corpus:
    chunks = [
        _make_chunk("c1", "Metformin is contraindicated when eGFR falls below 30."),
        _make_chunk("c2", "Atorvastatin reduces LDL cholesterol effectively."),
        _make_chunk("c3", "Adult influenza vaccination is recommended annually."),
        _make_chunk("c4", "Pneumococcal vaccine for adults aged 65 and older."),
        _make_chunk("c5", "Warfarin dosing requires regular INR monitoring."),
    ]
    for chunk in chunks:
        mem_corpus.upsert_chunk(chunk, embedding=None)
    return mem_corpus


class TestBM25IndexPositive:
    def test_relevant_query_returns_hit(self, populated_corpus: Corpus) -> None:
        rows = populated_corpus.all_rows()
        idx = BM25Index(rows)
        results = idx.query("metformin renal dosing", k=3)
        ids = [r[0] for r in results]
        assert "c1" in ids

    def test_scores_are_positive_for_match(self, populated_corpus: Corpus) -> None:
        rows = populated_corpus.all_rows()
        idx = BM25Index(rows)
        results = idx.query("metformin egfr", k=5)
        assert all(score > 0 for _, score in results)

    def test_ranked_by_score_descending(self, populated_corpus: Corpus) -> None:
        rows = populated_corpus.all_rows()
        idx = BM25Index(rows)
        results = idx.query("influenza vaccination adults", k=5)
        scores = [score for _, score in results]
        assert scores == sorted(scores, reverse=True)


class TestBM25IndexNegative:
    def test_completely_unrelated_query_returns_empty(self, populated_corpus: Corpus) -> None:
        rows = populated_corpus.all_rows()
        idx = BM25Index(rows)
        # "xylophone" is not in any chunk.
        results = idx.query("xylophone zither", k=5)
        assert results == []

    def test_empty_query_returns_empty(self, populated_corpus: Corpus) -> None:
        rows = populated_corpus.all_rows()
        idx = BM25Index(rows)
        results = idx.query("", k=5)
        assert results == []


class TestBM25IndexEdge:
    def test_empty_corpus_returns_empty(self) -> None:
        idx = BM25Index([])
        results = idx.query("metformin", k=5)
        assert results == []

    def test_k_limits_results(self, populated_corpus: Corpus) -> None:
        rows = populated_corpus.all_rows()
        idx = BM25Index(rows)
        results = idx.query("adults vaccine", k=2)
        assert len(results) <= 2

    def test_stop_words_only_query(self, populated_corpus: Corpus) -> None:
        rows = populated_corpus.all_rows()
        idx = BM25Index(rows)
        # "is" and "the" appear in many docs — result may be empty or non-empty
        # but should never raise.
        results = idx.query("is the and", k=5)
        assert isinstance(results, list)


class TestHybridRetrieverBM25Only:
    """HybridRetriever with no embedder — tests BM25 path exclusively."""

    def test_retrieves_relevant_chunk(self, populated_corpus: Corpus) -> None:
        retriever = HybridRetriever(populated_corpus, embedder=None)
        results = retriever.query("metformin renal dosing", k=5)
        ids = [c.chunk_id for c in results]
        assert "c1" in ids

    def test_returns_guideline_chunk_objects(self, populated_corpus: Corpus) -> None:
        retriever = HybridRetriever(populated_corpus, embedder=None)
        results = retriever.query("influenza", k=5)
        assert all(isinstance(c, GuidelineChunk) for c in results)

    def test_k_limits_results(self, populated_corpus: Corpus) -> None:
        retriever = HybridRetriever(populated_corpus, embedder=None)
        results = retriever.query("vaccine adults dosing monitoring", k=2)
        assert len(results) <= 2

    def test_empty_corpus_returns_empty(self, mem_corpus: Corpus) -> None:
        retriever = HybridRetriever(mem_corpus, embedder=None)
        results = retriever.query("metformin", k=5)
        assert results == []
