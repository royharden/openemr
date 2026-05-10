"""L1: Corpus idempotency unit tests.

Verifies that upserting the same chunks twice leaves the corpus content hash
unchanged (idempotent upsert) and that the hash changes only when content
actually changes.

Positive: hash stable on re-upsert.
Negative: hash changes on content update.
Edge: empty corpus hash, single-chunk corpus.

Plan §15.5.6 — positive/negative/edge per rule.
"""

from __future__ import annotations

import pytest

from app.rag.corpus import Corpus
from app.rag.contracts import GuidelineChunk


def _chunk(chunk_id: str, text: str = "Some content.") -> GuidelineChunk:
    return GuidelineChunk(
        chunk_id=chunk_id,
        source_id=f"src-{chunk_id}",
        source_organization="CDC-ACIP",
        source_name="ACIP Test",
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
    yield corpus
    corpus.close()


class TestCorpusIdempotencyPositive:
    def test_hash_stable_on_re_upsert(self, mem_corpus: Corpus) -> None:
        chunk = _chunk("c1", "Metformin is contraindicated when eGFR < 30.")
        mem_corpus.upsert_chunk(chunk, embedding=[0.1, 0.2, 0.3])
        h1 = mem_corpus.content_hash()
        # Upsert the same chunk again — hash must be identical.
        mem_corpus.upsert_chunk(chunk, embedding=[0.1, 0.2, 0.3])
        h2 = mem_corpus.content_hash()
        assert h1 == h2

    def test_count_stable_on_re_upsert(self, mem_corpus: Corpus) -> None:
        chunk = _chunk("c1")
        mem_corpus.upsert_chunk(chunk, embedding=None)
        n1 = mem_corpus.count()
        mem_corpus.upsert_chunk(chunk, embedding=None)
        n2 = mem_corpus.count()
        assert n1 == n2 == 1

    def test_multiple_chunks_idempotent(self, mem_corpus: Corpus) -> None:
        chunks = [_chunk(f"c{i}", f"Content {i}.") for i in range(5)]
        for c in chunks:
            mem_corpus.upsert_chunk(c, embedding=None)
        h1 = mem_corpus.content_hash()
        for c in chunks:
            mem_corpus.upsert_chunk(c, embedding=None)
        h2 = mem_corpus.content_hash()
        assert h1 == h2


class TestCorpusIdempotencyNegative:
    def test_hash_changes_on_text_update(self, mem_corpus: Corpus) -> None:
        chunk = _chunk("c1", "Original text.")
        mem_corpus.upsert_chunk(chunk, embedding=None)
        h1 = mem_corpus.content_hash()
        # Update the chunk text — hash must differ.
        updated = _chunk("c1", "Updated text that is different.")
        mem_corpus.upsert_chunk(updated, embedding=None)
        h2 = mem_corpus.content_hash()
        assert h1 != h2

    def test_hash_changes_on_embedding_update(self, mem_corpus: Corpus) -> None:
        chunk = _chunk("c1", "Fixed text.")
        mem_corpus.upsert_chunk(chunk, embedding=[0.1, 0.2])
        h1 = mem_corpus.content_hash()
        mem_corpus.upsert_chunk(chunk, embedding=[0.9, 0.8])
        h2 = mem_corpus.content_hash()
        assert h1 != h2

    def test_new_chunk_changes_hash(self, mem_corpus: Corpus) -> None:
        chunk1 = _chunk("c1")
        mem_corpus.upsert_chunk(chunk1, embedding=None)
        h1 = mem_corpus.content_hash()
        chunk2 = _chunk("c2", "Completely different chunk.")
        mem_corpus.upsert_chunk(chunk2, embedding=None)
        h2 = mem_corpus.content_hash()
        assert h1 != h2


class TestCorpusIdempotencyEdge:
    def test_empty_corpus_hash_is_deterministic(self, mem_corpus: Corpus) -> None:
        h1 = mem_corpus.content_hash()
        h2 = mem_corpus.content_hash()
        assert h1 == h2

    def test_single_chunk_hash(self, mem_corpus: Corpus) -> None:
        chunk = _chunk("solo", "Only chunk in corpus.")
        mem_corpus.upsert_chunk(chunk, embedding=None)
        h = mem_corpus.content_hash()
        assert isinstance(h, str) and len(h) == 64

    def test_chunk_exists_after_upsert(self, mem_corpus: Corpus) -> None:
        chunk = _chunk("exists-test")
        assert not mem_corpus.chunk_exists("exists-test")
        mem_corpus.upsert_chunk(chunk, embedding=None)
        assert mem_corpus.chunk_exists("exists-test")

    def test_get_chunk_round_trip(self, mem_corpus: Corpus) -> None:
        chunk = _chunk("roundtrip", "Round-trip text.")
        mem_corpus.upsert_chunk(chunk, embedding=None)
        fetched = mem_corpus.get_chunk("roundtrip")
        assert fetched is not None
        assert fetched.chunk_id == "roundtrip"
        assert fetched.text == "Round-trip text."
