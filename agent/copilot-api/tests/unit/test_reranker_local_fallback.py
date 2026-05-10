"""L1: Local cross-encoder fallback reranker unit tests.

Tests that EvalReranker (used in COPILOT_EVAL_MODE=1) and the pass-through
fallback when sentence-transformers is absent produce valid results.

Positive: deterministic ranking, reranker label = 'fallback'.
Negative: empty candidates → empty result.
Edge: single candidate, top_n > len(candidates).

Plan §15.5.6 — positive/negative/edge per rule.
"""

from __future__ import annotations

import pytest

from app.rag._eval_mocks import EvalReranker, MOCK_VERSION, _text_hash
from app.rag.contracts import GuidelineChunk


def _chunk(chunk_id: str, text: str = "clinical content") -> GuidelineChunk:
    return GuidelineChunk(
        chunk_id=chunk_id,
        source_id=f"src-{chunk_id}",
        source_organization="HMS-LOE",
        source_name="HMS Evidence",
        page_or_section="§evidence",
        text=text,
        recommendation_grade="1a",
        source_year=2023,
    )


CANDIDATES = [_chunk(f"c{i}", f"Chunk text {i}: content about topic {i}.") for i in range(7)]


class TestEvalRerankerPositive:
    def test_returns_top_n_results(self) -> None:
        reranker = EvalReranker(top_n=3)
        results = reranker.rerank("metformin renal dosing", CANDIDATES)
        assert len(results) == 3

    def test_reranker_label_is_fallback(self) -> None:
        reranker = EvalReranker(top_n=3)
        results = reranker.rerank("any query", CANDIDATES)
        assert all(c.reranker == "fallback" for c in results)

    def test_deterministic_same_query(self) -> None:
        reranker = EvalReranker(top_n=5)
        r1 = [c.chunk_id for c in reranker.rerank("influenza vaccination", CANDIDATES)]
        r2 = [c.chunk_id for c in reranker.rerank("influenza vaccination", CANDIDATES)]
        assert r1 == r2

    def test_positions_sequential(self) -> None:
        reranker = EvalReranker(top_n=4)
        results = reranker.rerank("query", CANDIDATES)
        positions = [c.rerank_position for c in results]
        assert positions == list(range(len(results)))

    def test_rerank_scores_set(self) -> None:
        reranker = EvalReranker(top_n=3)
        results = reranker.rerank("query", CANDIDATES)
        assert all(c.rerank_score is not None for c in results)


class TestEvalRerankerNegative:
    def test_empty_candidates_returns_empty(self) -> None:
        reranker = EvalReranker(top_n=5)
        results = reranker.rerank("any query", [])
        assert results == []

    def test_different_queries_produce_different_rankings(self) -> None:
        reranker = EvalReranker(top_n=5)
        r1 = [c.chunk_id for c in reranker.rerank("metformin", CANDIDATES)]
        r2 = [c.chunk_id for c in reranker.rerank("influenza vaccination", CANDIDATES)]
        # Very unlikely to be identical for different queries.
        assert r1 != r2 or len(CANDIDATES) == 1


class TestEvalRerankerEdge:
    def test_top_n_larger_than_candidates(self) -> None:
        reranker = EvalReranker(top_n=100)
        results = reranker.rerank("query", CANDIDATES[:2])
        assert len(results) == 2  # capped at len(candidates)

    def test_single_candidate_returned(self) -> None:
        reranker = EvalReranker(top_n=5)
        results = reranker.rerank("query", [CANDIDATES[0]])
        assert len(results) == 1
        assert results[0].chunk_id == CANDIDATES[0].chunk_id

    def test_mock_version_in_hash(self) -> None:
        h1 = _text_hash("test text")
        # Changing MOCK_VERSION would change the hash (tested conceptually —
        # version is embedded in the hash prefix).
        import hashlib
        expected = hashlib.sha256(
            (MOCK_VERSION + "|" + "test text").encode()
        ).hexdigest()
        assert h1 == expected

    def test_original_chunks_not_mutated(self) -> None:
        reranker = EvalReranker(top_n=3)
        originals = [c.model_copy() for c in CANDIDATES[:3]]
        reranker.rerank("query", CANDIDATES[:3])
        # Original CANDIDATES objects must be unchanged.
        for orig, cand in zip(originals, CANDIDATES[:3]):
            assert orig.reranker == cand.reranker
            assert orig.rerank_score == cand.rerank_score
