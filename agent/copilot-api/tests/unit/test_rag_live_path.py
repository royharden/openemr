"""L1: Live RAG path wiring (AgDR-0062).

Regression guard: verifies that ``retrieve_guidelines()`` actually instantiates
an embedder and a reranker on the live (non-eval) path. Pre-AgDR-0062 the
live path silently fell back to BM25-only because ``HybridRetriever`` was
constructed without an embedder and the reranker was never called.

What this test catches:
  - A regression that re-removes ``get_embedder()`` from ``retrieve_guidelines``.
  - A regression that bypasses ``CohereReranker`` on the live path.
  - A regression that wraps embedder/reranker init in a swallow-all-errors
    block such that the spies never fire.

This test does NOT depend on any vendor API key. The embedder and reranker
modules are patched at the import sites used inside ``app.rag.__init__``.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.rag import retrieve_guidelines
from app.rag.contracts import GuidelineChunk


@pytest.fixture(autouse=True)
def _force_live_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure tests run on the live path, not eval mode."""
    monkeypatch.delenv("COPILOT_EVAL_MODE", raising=False)


@pytest.fixture
def fake_corpus(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Point retrieve_guidelines at a corpus.db path that exists so the live
    branch is taken — actual Corpus reads are patched below."""
    fake_db = tmp_path / "corpus.db"
    fake_db.write_bytes(b"")  # exists() only
    monkeypatch.setenv("COPILOT_RAG_CORPUS_PATH", str(fake_db))
    return fake_db


def _stub_chunk(chunk_id: str) -> GuidelineChunk:
    return GuidelineChunk(
        chunk_id=chunk_id,
        source_id="test",
        source_organization="HMS-LOE",
        source_name="Test guideline",
        page_or_section="test",
        text="Sample chunk text for live-path wiring assertion.",
        recommendation_grade=None,
        source_year=2026,
        bm25_score=1.0,
    )


def test_live_path_invokes_embedder_and_reranker(
    fake_corpus: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The live path must call get_embedder() and CohereReranker.rerank()."""

    embedder_spy = MagicMock(name="embedder")
    embedder_spy.embed_one.return_value = [0.0] * 1024

    get_embedder_calls = {"count": 0}

    def fake_get_embedder() -> Any:
        get_embedder_calls["count"] += 1
        return embedder_spy

    # The embedder is imported lazily inside retrieve_guidelines, so patch
    # the source module — Python's import cache will hand the spy back.
    monkeypatch.setattr("app.rag.embedder.get_embedder", fake_get_embedder)

    candidates = [_stub_chunk("c1"), _stub_chunk("c2")]

    class FakeRetriever:
        def __init__(self, corpus: Any, embedder: Any = None) -> None:
            assert embedder is embedder_spy, (
                "HybridRetriever must receive the live embedder; "
                "BM25-only construction is the bug AgDR-0062 fixes."
            )
            self.embedder = embedder

        def query(self, text: str, k: int = 20, **kwargs: Any) -> list[GuidelineChunk]:
            return candidates

    monkeypatch.setattr("app.rag.HybridRetriever", FakeRetriever)

    class FakeCorpus:
        def __init__(self, path: Path) -> None:
            self.path = path

        def __enter__(self) -> "FakeCorpus":
            return self

        def __exit__(self, *args: Any) -> None:
            return None

    monkeypatch.setattr("app.rag.Corpus", FakeCorpus)

    rerank_calls = {"count": 0}

    class FakeReranker:
        def __init__(self, top_n: int = 5) -> None:
            self.top_n = top_n

        def rerank(
            self, query: str, candidates: list[GuidelineChunk]
        ) -> list[GuidelineChunk]:
            rerank_calls["count"] += 1
            out = []
            for i, c in enumerate(candidates[: self.top_n]):
                c2 = c.model_copy()
                c2.rerank_score = 1.0 - (i * 0.1)
                c2.rerank_position = i
                c2.reranker = "test-spy"
                out.append(c2)
            return out

    monkeypatch.setattr("app.rag.reranker.CohereReranker", FakeReranker)

    chunks = retrieve_guidelines("does my patient need a vaccine?", top_k=5)

    assert get_embedder_calls["count"] == 1, "get_embedder() not invoked on live path"
    assert rerank_calls["count"] == 1, "CohereReranker.rerank() not invoked on live path"
    assert chunks, "retrieve_guidelines returned no chunks"
    assert all(c.reranker == "test-spy" for c in chunks), (
        "Returned chunks were not produced by the reranker — live path bypassed it."
    )


def test_live_path_uses_candidate_pool_of_twenty(
    fake_corpus: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The retriever must be asked for the full candidate pool (k=20),
    not just top_k, so the reranker has material to choose from."""

    requested_k: dict[str, int] = {}

    class FakeRetriever:
        def __init__(self, corpus: Any, embedder: Any = None) -> None:
            self.embedder = embedder

        def query(self, text: str, k: int = 20, **kwargs: Any) -> list[GuidelineChunk]:
            requested_k["k"] = k
            return [_stub_chunk(f"c{i}") for i in range(min(k, 20))]

    class FakeCorpus:
        def __init__(self, path: Path) -> None:
            self.path = path

        def __enter__(self) -> "FakeCorpus":
            return self

        def __exit__(self, *args: Any) -> None:
            return None

    class FakeReranker:
        def __init__(self, top_n: int = 5) -> None:
            self.top_n = top_n

        def rerank(self, query: str, candidates: list[GuidelineChunk]) -> list[GuidelineChunk]:
            return candidates[: self.top_n]

    embedder_spy = MagicMock()
    embedder_spy.embed_one.return_value = [0.0] * 1024

    monkeypatch.setattr("app.rag.embedder.get_embedder", lambda: embedder_spy)
    monkeypatch.setattr("app.rag.HybridRetriever", FakeRetriever)
    monkeypatch.setattr("app.rag.Corpus", FakeCorpus)
    monkeypatch.setattr("app.rag.reranker.CohereReranker", FakeReranker)

    retrieve_guidelines("test query", top_k=5)

    assert requested_k.get("k") == 20, (
        "Retriever must be queried with k=20 (CANDIDATE_POOL_K) so the reranker "
        "has a meaningful pool to choose from."
    )


def test_live_path_degrades_to_bm25_only_on_embedder_init_failure(
    fake_corpus: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When embedder init throws, retrieval must continue with embedder=None."""

    def boom() -> Any:
        raise RuntimeError("no VOYAGE_API_KEY")

    monkeypatch.setattr("app.rag.embedder.get_embedder", boom)

    observed_embedder: dict[str, Any] = {}

    class FakeRetriever:
        def __init__(self, corpus: Any, embedder: Any = None) -> None:
            observed_embedder["value"] = embedder

        def query(self, text: str, k: int = 20, **kwargs: Any) -> list[GuidelineChunk]:
            return [_stub_chunk("c1")]

    class FakeCorpus:
        def __init__(self, path: Path) -> None:
            pass

        def __enter__(self) -> "FakeCorpus":
            return self

        def __exit__(self, *args: Any) -> None:
            return None

    class FakeReranker:
        def __init__(self, top_n: int = 5) -> None:
            pass

        def rerank(self, query: str, candidates: list[GuidelineChunk]) -> list[GuidelineChunk]:
            return candidates[:top_n] if False else candidates

    monkeypatch.setattr("app.rag.HybridRetriever", FakeRetriever)
    monkeypatch.setattr("app.rag.Corpus", FakeCorpus)
    monkeypatch.setattr("app.rag.reranker.CohereReranker", FakeReranker)

    chunks = retrieve_guidelines("anything", top_k=5)

    assert observed_embedder["value"] is None, (
        "Embedder init failure should result in embedder=None to HybridRetriever, "
        "not a crash."
    )
    assert chunks, "Pipeline should still return chunks under embedder failure."
