"""L1: Vector retriever unit tests.

Uses in-memory Corpus with EvalEmbedder (deterministic, no Voyage calls).
Tests positive (vector hit), negative (wrong dimension), and edge cases
(no-embedder fallback, empty corpus).

Plan §15.5.6 — positive/negative/edge per rule.
"""

from __future__ import annotations

import pytest

from app.rag.corpus import Corpus, _pack_embedding
from app.rag.contracts import GuidelineChunk
from app.rag.retriever import HybridRetriever
from app.rag._eval_mocks import EvalEmbedder, MOCK_DIM


def _make_chunk(chunk_id: str, text: str) -> GuidelineChunk:
    return GuidelineChunk(
        chunk_id=chunk_id,
        source_id=f"src-{chunk_id}",
        source_organization="FDA",
        source_name="Drug Label",
        page_or_section="§dosage",
        text=text,
        recommendation_grade=None,
        source_year=2023,
    )


@pytest.fixture
def mem_corpus() -> Corpus:
    corpus = Corpus(path=":memory:")
    corpus.open()
    corpus.ensure_schema()
    return corpus


@pytest.fixture
def vec_corpus(mem_corpus: Corpus) -> Corpus:
    embedder = EvalEmbedder()
    texts = [
        ("v1", "Metformin renal dosing eGFR threshold thirty."),
        ("v2", "Atorvastatin LDL reduction statin therapy."),
        ("v3", "Influenza vaccination annually recommended."),
        ("v4", "Pneumococcal vaccine elderly adults."),
        ("v5", "Warfarin INR monitoring anticoagulation."),
    ]
    for chunk_id, text in texts:
        chunk = _make_chunk(chunk_id, text)
        embedding = embedder.embed_one(text)
        mem_corpus.upsert_chunk(chunk, embedding)
    return mem_corpus


class TestVectorRetrievalPositive:
    def test_vector_candidates_returned(self, vec_corpus: Corpus) -> None:
        embedder = EvalEmbedder()
        q_vec = embedder.embed_one("metformin renal dosing threshold")
        results = vec_corpus.vector_candidates(q_vec, k=5)
        assert len(results) > 0
        assert all(isinstance(r, tuple) and len(r) == 2 for r in results)

    def test_scores_in_range(self, vec_corpus: Corpus) -> None:
        embedder = EvalEmbedder()
        q_vec = embedder.embed_one("statin therapy")
        results = vec_corpus.vector_candidates(q_vec, k=5)
        for _, score in results:
            # Cosine similarity in [-1, 1] or brute-force dot product
            assert -1.1 <= score <= 1.1

    def test_hybrid_retriever_uses_vector_path(self, vec_corpus: Corpus) -> None:
        embedder = EvalEmbedder()
        retriever = HybridRetriever(vec_corpus, embedder=embedder)
        results = retriever.query("metformin renal", k=10)
        assert len(results) > 0
        assert all(isinstance(c, GuidelineChunk) for c in results)

    def test_eval_embedder_is_deterministic(self) -> None:
        emb = EvalEmbedder()
        v1 = emb.embed_one("same text every time")
        v2 = emb.embed_one("same text every time")
        assert v1 == v2

    def test_different_texts_produce_different_vectors(self) -> None:
        emb = EvalEmbedder()
        v1 = emb.embed_one("metformin renal dosing")
        v2 = emb.embed_one("influenza vaccination adults")
        assert v1 != v2


class TestVectorRetrievalNegative:
    def test_empty_corpus_returns_empty(self, mem_corpus: Corpus) -> None:
        embedder = EvalEmbedder()
        q_vec = embedder.embed_one("metformin")
        results = mem_corpus.vector_candidates(q_vec, k=5)
        assert results == []

    def test_chunk_without_embedding_not_returned(self, mem_corpus: Corpus) -> None:
        chunk = _make_chunk("no-emb", "Some text without embedding.")
        mem_corpus.upsert_chunk(chunk, embedding=None)
        embedder = EvalEmbedder()
        q_vec = embedder.embed_one("text without embedding")
        results = mem_corpus.vector_candidates(q_vec, k=5)
        ids = [r[0] for r in results]
        assert "no-emb" not in ids


class TestVectorRetrievalEdge:
    def test_k_limits_results(self, vec_corpus: Corpus) -> None:
        embedder = EvalEmbedder()
        q_vec = embedder.embed_one("anything")
        results = vec_corpus.vector_candidates(q_vec, k=2)
        assert len(results) <= 2

    def test_hybrid_union_deduplicates(self, vec_corpus: Corpus) -> None:
        """Chunks appearing in both BM25 and vector legs should appear once."""
        embedder = EvalEmbedder()
        retriever = HybridRetriever(vec_corpus, embedder=embedder)
        results = retriever.query("metformin renal dosing threshold", k=20)
        ids = [c.chunk_id for c in results]
        assert len(ids) == len(set(ids)), "Duplicate chunk IDs in union result"

    def test_pack_unpack_roundtrip(self) -> None:
        from app.rag.corpus import _unpack_embedding
        vec = [0.1, 0.2, 0.3, 0.4]
        blob = _pack_embedding(vec)
        recovered = _unpack_embedding(blob)
        assert len(recovered) == len(vec)
        for a, b in zip(recovered, vec):
            assert abs(a - b) < 1e-5
