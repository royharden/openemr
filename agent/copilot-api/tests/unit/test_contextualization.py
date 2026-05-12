"""AgDR-0079 — unit tests for Anthropic Contextual Retrieval (Plan §7.2.b).

Covers the deterministic eval-mode path, the disk-cache hit/miss/key paths,
the embed-and-upsert wrapper's branch on
``COPILOT_CONTEXTUAL_RETRIEVAL`` env var, and the corpus column extension.
Live Anthropic calls are NOT exercised here — the helper falls back to the
deterministic placeholder when ``ANTHROPIC_API_KEY`` is missing, which is
the test environment's posture.
"""

from __future__ import annotations

import os

import pytest

# Match the eval-mode bootstrapping pattern used by tests/integration/...
os.environ["COPILOT_EVAL_MODE"] = "1"

from app.rag.contextualization import (  # noqa: E402
    _cache_get,
    _cache_key,
    _cache_path,
    _cache_put,
    _eval_summary,
    _source_doc_hash,
    contextualize_text_for_embedding,
    embed_and_upsert_chunks,
    generate_context_summary,
    is_contextual_retrieval_enabled,
)
from app.rag.contracts import GuidelineChunk  # noqa: E402
from app.rag.corpus import Corpus  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_chunk(chunk_id: str, text: str) -> GuidelineChunk:
    return GuidelineChunk(
        chunk_id=chunk_id,
        source_id="test-source",
        source_organization="ADA",
        source_name="ADA Test Doc",
        page_or_section="§1 — Test",
        recommendation_grade="A",
        source_year=2026,
        text=text,
    )


class _StubEmbedder:
    """Records every embed call so tests can assert on the text passed."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        return [[float(len(t))] for t in texts]

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]


# ---------------------------------------------------------------------------
# is_contextual_retrieval_enabled
# ---------------------------------------------------------------------------


class TestEnvFlag:
    def test_default_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("COPILOT_CONTEXTUAL_RETRIEVAL", raising=False)
        assert is_contextual_retrieval_enabled() is False

    def test_explicit_on(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("COPILOT_CONTEXTUAL_RETRIEVAL", "1")
        assert is_contextual_retrieval_enabled() is True

    def test_non_one_treated_as_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A literal '1' is required — 'true' / 'yes' / '0' all stay off."""
        for val in ("0", "true", "True", "yes", "on", ""):
            monkeypatch.setenv("COPILOT_CONTEXTUAL_RETRIEVAL", val)
            assert is_contextual_retrieval_enabled() is False


# ---------------------------------------------------------------------------
# Cache key + disk cache
# ---------------------------------------------------------------------------


class TestCacheKey:
    def test_key_is_deterministic(self) -> None:
        k1 = _cache_key("src", "chunk", "doc body", "haiku-4.5")
        k2 = _cache_key("src", "chunk", "doc body", "haiku-4.5")
        assert k1 == k2

    def test_key_changes_on_source_id(self) -> None:
        a = _cache_key("src-a", "chunk", "doc", "haiku")
        b = _cache_key("src-b", "chunk", "doc", "haiku")
        assert a != b

    def test_key_changes_on_chunk_id(self) -> None:
        a = _cache_key("src", "chunk-a", "doc", "haiku")
        b = _cache_key("src", "chunk-b", "doc", "haiku")
        assert a != b

    def test_key_changes_on_source_doc_hash(self) -> None:
        """A source-document edit must invalidate the cache so the LLM is
        re-called with the fresher context."""
        a = _cache_key("src", "chunk", "doc original", "haiku")
        b = _cache_key("src", "chunk", "doc edited", "haiku")
        assert a != b

    def test_key_changes_on_model(self) -> None:
        a = _cache_key("src", "chunk", "doc", "haiku-4.5")
        b = _cache_key("src", "chunk", "doc", "haiku-3.5")
        assert a != b

    def test_source_doc_hash_is_stable(self) -> None:
        assert _source_doc_hash("hello") == _source_doc_hash("hello")
        assert _source_doc_hash("hello") != _source_doc_hash("world")


class TestDiskCache:
    def test_miss_returns_none(self, tmp_path) -> None:
        assert _cache_get(tmp_path, "nonexistent-key") is None

    def test_put_then_get(self, tmp_path) -> None:
        _cache_put(tmp_path, "test-key", "summary text", "src", "chunk", "haiku")
        assert _cache_get(tmp_path, "test-key") == "summary text"

    def test_corrupt_json_returns_none(self, tmp_path) -> None:
        path = _cache_path(tmp_path, "bad-key")
        path.write_text("not json {{{", encoding="utf-8")
        assert _cache_get(tmp_path, "bad-key") is None


# ---------------------------------------------------------------------------
# Eval-mode deterministic summary
# ---------------------------------------------------------------------------


class TestEvalSummary:
    def test_includes_org_and_year(self) -> None:
        s = _eval_summary("chunk body", {"source_organization": "ADA", "source_year": 2026})
        assert "ADA" in s
        assert "2026" in s

    def test_deterministic_for_same_input(self) -> None:
        info = {"source_organization": "FDA", "source_year": 2024}
        assert _eval_summary("body", info) == _eval_summary("body", info)

    def test_varies_with_chunk_text(self) -> None:
        info = {"source_organization": "FDA", "source_year": 2024}
        assert _eval_summary("body A", info) != _eval_summary("body B", info)


class TestGenerateContextSummary:
    def test_eval_mode_short_circuits(self) -> None:
        """COPILOT_EVAL_MODE=1 returns the deterministic placeholder without
        touching the disk cache or the network."""
        result = generate_context_summary(
            "chunk text",
            "source doc",
            {"source_organization": "ADA", "source_year": 2026},
            source_id="src",
            chunk_id="c1",
        )
        assert "ADA" in result
        assert "2026" in result


# ---------------------------------------------------------------------------
# contextualize_text_for_embedding
# ---------------------------------------------------------------------------


class TestContextualizeTextForEmbedding:
    def test_prepends_summary(self) -> None:
        out = contextualize_text_for_embedding("chunk body", "context blurb")
        assert out == "context blurb\n\nchunk body"

    def test_empty_summary_returns_chunk_unchanged(self) -> None:
        assert contextualize_text_for_embedding("chunk body", "") == "chunk body"


# ---------------------------------------------------------------------------
# embed_and_upsert_chunks — env-var branching
# ---------------------------------------------------------------------------


class TestEmbedAndUpsertChunks:
    def test_disabled_falls_back_to_verbatim_embed(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """With COPILOT_CONTEXTUAL_RETRIEVAL unset, the embedder receives the
        verbatim chunk text — byte-identical to the pre-AgDR-0079 path."""

        monkeypatch.delenv("COPILOT_CONTEXTUAL_RETRIEVAL", raising=False)

        corpus = Corpus(path=tmp_path / "corpus.db")
        corpus.open()
        try:
            corpus.ensure_schema()
            embedder = _StubEmbedder()
            chunks = [
                _make_chunk("c1", "first chunk"),
                _make_chunk("c2", "second chunk"),
            ]
            embed_and_upsert_chunks(corpus, embedder, chunks, "full doc")

            assert embedder.calls == [["first chunk", "second chunk"]]
            row = corpus.conn.execute(
                "SELECT context_summary FROM chunks WHERE id = 'c1'"
            ).fetchone()
            assert row["context_summary"] is None
        finally:
            corpus.close()

    def test_enabled_embeds_contextualized_text(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """With the env var on (and eval mode supplying the placeholder),
        the embedder sees the prepended-context form and the new
        context_summary column is populated."""

        monkeypatch.setenv("COPILOT_CONTEXTUAL_RETRIEVAL", "1")

        corpus = Corpus(path=tmp_path / "corpus.db")
        corpus.open()
        try:
            corpus.ensure_schema()
            embedder = _StubEmbedder()
            chunks = [_make_chunk("c1", "first chunk")]
            embed_and_upsert_chunks(corpus, embedder, chunks, "full doc body")

            # Embedder saw the prepended-context form.
            assert len(embedder.calls) == 1
            embedded = embedder.calls[0][0]
            assert "first chunk" in embedded
            assert "Context:" in embedded  # eval placeholder prefix
            assert embedded.startswith("Context:")

            # context_summary persisted on the row.
            row = corpus.conn.execute(
                "SELECT context_summary, text FROM chunks WHERE id = 'c1'"
            ).fetchone()
            assert row["context_summary"] is not None
            assert row["context_summary"].startswith("Context:")
            # The verbatim text column is unchanged.
            assert row["text"] == "first chunk"
        finally:
            corpus.close()

    def test_empty_chunk_list_is_noop(self, tmp_path) -> None:
        corpus = Corpus(path=tmp_path / "corpus.db")
        corpus.open()
        try:
            corpus.ensure_schema()
            embedder = _StubEmbedder()
            embed_and_upsert_chunks(corpus, embedder, [], "doc")
            assert embedder.calls == []
            assert corpus.count() == 0
        finally:
            corpus.close()


# ---------------------------------------------------------------------------
# Corpus column extension — verbatim text always returned to consumers
# ---------------------------------------------------------------------------


class TestCorpusContextSummaryColumn:
    def test_get_chunk_returns_verbatim_text_when_context_set(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """AgDR-0079 invariant: consumers always see the original chunk text,
        never the LLM-generated context blurb. The blurb is metadata for
        retrieval (BM25 + embedding) only."""

        monkeypatch.setenv("COPILOT_CONTEXTUAL_RETRIEVAL", "1")

        corpus = Corpus(path=tmp_path / "corpus.db")
        corpus.open()
        try:
            corpus.ensure_schema()
            embedder = _StubEmbedder()
            embed_and_upsert_chunks(
                corpus, embedder, [_make_chunk("c1", "verbatim chunk body")], "doc"
            )
            chunk = corpus.get_chunk("c1")
            assert chunk is not None
            assert chunk.text == "verbatim chunk body"
        finally:
            corpus.close()

    def test_bm25_terms_include_context_when_set(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """BM25 token index covers both the context summary and the chunk
        text — that's the retrieval-quality lever the technique pays for."""

        monkeypatch.setenv("COPILOT_CONTEXTUAL_RETRIEVAL", "1")

        corpus = Corpus(path=tmp_path / "corpus.db")
        corpus.open()
        try:
            corpus.ensure_schema()
            embedder = _StubEmbedder()
            embed_and_upsert_chunks(
                corpus,
                embedder,
                [_make_chunk("c1", "ldl cholesterol")],
                "doc body",
            )
            row = corpus.conn.execute(
                "SELECT bm25_terms FROM chunks WHERE id = 'c1'"
            ).fetchone()
            terms = row["bm25_terms"]
            # Eval placeholder contains "context", "ada", "guideline"
            assert "context" in terms
            # Chunk body words present.
            assert "ldl" in terms
            assert "cholesterol" in terms
        finally:
            corpus.close()
