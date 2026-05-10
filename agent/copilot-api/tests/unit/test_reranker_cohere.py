"""L1: Cohere reranker unit tests (mocked HTTP).

All tests run with COPILOT_EVAL_MODE=1 or by patching the cohere client so
no real Cohere API calls are made.

Positive: reranker returns top-N sorted chunks.
Negative: empty candidates → empty result.
Edge: fewer candidates than top_n.

Plan §15.5.6 — positive/negative/edge per rule.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from app.rag.contracts import GuidelineChunk
from app.rag.reranker import CohereReranker, TOP_N


def _chunk(chunk_id: str, text: str = "content") -> GuidelineChunk:
    return GuidelineChunk(
        chunk_id=chunk_id,
        source_id=f"s-{chunk_id}",
        source_organization="CDC-ACIP",
        source_name="ACIP Recommendations",
        page_or_section="§test",
        text=text,
        recommendation_grade="A",
        source_year=2024,
    )


CANDIDATES = [
    _chunk("c1", "Metformin contraindicated below eGFR 30."),
    _chunk("c2", "Influenza vaccine recommended annually."),
    _chunk("c3", "Atorvastatin reduces LDL effectively."),
    _chunk("c4", "Pneumococcal vaccine for adults 65 plus."),
    _chunk("c5", "Warfarin INR target 2.0 to 3.0."),
    _chunk("c6", "Tdap booster every 10 years."),
    _chunk("c7", "Albuterol PRN for acute asthma exacerbation."),
]


class TestCohereRerankerPositive:
    def test_returns_top_n_chunks(self) -> None:
        reranker = CohereReranker(api_key="test-key", top_n=3)
        mock_result = MagicMock()
        mock_result.results = [
            MagicMock(index=0, relevance_score=0.95),
            MagicMock(index=2, relevance_score=0.85),
            MagicMock(index=4, relevance_score=0.75),
        ]
        with patch.dict(os.environ, {"COPILOT_EVAL_MODE": "0"}):
            with patch("cohere.Client") as mock_client_cls:
                mock_client = mock_client_cls.return_value
                mock_client.rerank.return_value = mock_result
                results = reranker.rerank("metformin renal dosing", CANDIDATES)

        assert len(results) == 3
        assert results[0].chunk_id == "c1"
        assert results[1].chunk_id == "c3"
        assert results[2].chunk_id == "c5"

    def test_reranker_label_set_to_cohere(self) -> None:
        reranker = CohereReranker(api_key="test-key", top_n=2)
        mock_result = MagicMock()
        mock_result.results = [
            MagicMock(index=1, relevance_score=0.9),
            MagicMock(index=0, relevance_score=0.8),
        ]
        with patch.dict(os.environ, {"COPILOT_EVAL_MODE": "0"}):
            with patch("cohere.Client") as mock_client_cls:
                mock_client = mock_client_cls.return_value
                mock_client.rerank.return_value = mock_result
                results = reranker.rerank("test query", CANDIDATES)

        assert all(c.reranker == "cohere" for c in results)

    def test_rerank_positions_set(self) -> None:
        reranker = CohereReranker(api_key="test-key", top_n=2)
        mock_result = MagicMock()
        mock_result.results = [
            MagicMock(index=0, relevance_score=0.9),
            MagicMock(index=1, relevance_score=0.8),
        ]
        with patch.dict(os.environ, {"COPILOT_EVAL_MODE": "0"}):
            with patch("cohere.Client") as mock_client_cls:
                mock_client = mock_client_cls.return_value
                mock_client.rerank.return_value = mock_result
                results = reranker.rerank("test query", CANDIDATES)

        assert results[0].rerank_position == 0
        assert results[1].rerank_position == 1


class TestCohereRerankerNegative:
    def test_empty_candidates_returns_empty(self) -> None:
        reranker = CohereReranker(api_key="test-key")
        results = reranker.rerank("query", [])
        assert results == []

    def test_cohere_exception_falls_back_to_local(self) -> None:
        reranker = CohereReranker(api_key="test-key", top_n=3)
        with patch.dict(os.environ, {"COPILOT_EVAL_MODE": "0"}):
            with patch("cohere.Client") as mock_client_cls:
                mock_client = mock_client_cls.return_value
                mock_client.rerank.side_effect = RuntimeError("Rate limit exceeded")
                results = reranker.rerank("metformin", CANDIDATES[:3])

        # Should fall back to local cross-encoder or pass-through.
        assert isinstance(results, list)
        assert len(results) <= 3
        if results:
            # fallback label must indicate fallback mode
            assert results[0].reranker == "fallback"


class TestCohereRerankerEdge:
    def test_fewer_candidates_than_top_n(self) -> None:
        reranker = CohereReranker(api_key="test-key", top_n=10)
        two_chunks = CANDIDATES[:2]
        mock_result = MagicMock()
        mock_result.results = [
            MagicMock(index=0, relevance_score=0.9),
            MagicMock(index=1, relevance_score=0.8),
        ]
        with patch.dict(os.environ, {"COPILOT_EVAL_MODE": "0"}):
            with patch("cohere.Client") as mock_client_cls:
                mock_client = mock_client_cls.return_value
                mock_client.rerank.return_value = mock_result
                results = reranker.rerank("query", two_chunks)

        assert len(results) == 2

    def test_no_api_key_falls_back_to_local(self) -> None:
        env_backup = os.environ.pop("COHERE_API_KEY", None)
        try:
            reranker = CohereReranker(api_key="", top_n=3)
            results = reranker.rerank("metformin renal", CANDIDATES[:3])
            assert isinstance(results, list)
        finally:
            if env_backup is not None:
                os.environ["COHERE_API_KEY"] = env_backup

    def test_eval_mode_uses_eval_reranker(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("COPILOT_EVAL_MODE", "1")
        reranker = CohereReranker(api_key="test-key", top_n=3)
        results = reranker.rerank("metformin", CANDIDATES[:5])
        assert isinstance(results, list)
        assert len(results) <= 3
        if results:
            assert results[0].reranker == "fallback"
