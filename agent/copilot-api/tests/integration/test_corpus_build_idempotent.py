"""L2: Corpus build idempotency integration test.

Runs the HMS-LOE ingestor twice against the same corpus and verifies the
content hash is identical after both runs.  No network calls — uses
EvalEmbedder.

Plan §15.5 L2 — integration; exercises build_corpus idempotency guarantee.
"""

from __future__ import annotations

import pytest

from app.rag.corpus import Corpus
from app.rag._eval_mocks import EvalEmbedder
from app.rag.ingestion import hms_loe


@pytest.fixture
def empty_corpus(tmp_path: "Path") -> Corpus:
    corpus = Corpus(path=tmp_path / "idempotent.db")
    corpus.open()
    corpus.ensure_schema()
    yield corpus
    corpus.close()


class TestCorpusBuildIdempotent:
    def test_hms_loe_ingest_idempotent(self, empty_corpus: Corpus) -> None:
        embedder = EvalEmbedder()

        n1 = hms_loe.ingest(empty_corpus, embedder)
        h1 = empty_corpus.content_hash()
        c1 = empty_corpus.count()

        n2 = hms_loe.ingest(empty_corpus, embedder)
        h2 = empty_corpus.content_hash()
        c2 = empty_corpus.count()

        assert h1 == h2, "Content hash must be identical after re-ingest"
        assert c1 == c2, "Chunk count must be stable after re-ingest"
        assert n1 > 0, "First ingest should produce chunks"

    def test_ingest_produces_nonzero_chunks(self, empty_corpus: Corpus) -> None:
        embedder = EvalEmbedder()
        count = hms_loe.ingest(empty_corpus, embedder)
        assert count > 0

    def test_all_chunks_have_source_year(self, empty_corpus: Corpus) -> None:
        embedder = EvalEmbedder()
        hms_loe.ingest(empty_corpus, embedder)
        # All HMS-LOE chunks should have source_year set.
        from app.rag.corpus import Corpus as _C
        cur = empty_corpus.conn.execute(
            "SELECT id, source_year, source_organization FROM chunks"
        )
        rows = cur.fetchall()
        for row in rows:
            if row["source_organization"] == "HMS-LOE":
                assert row["source_year"] is not None, (
                    f"chunk {row['id']} missing source_year"
                )

    def test_all_chunks_have_text(self, empty_corpus: Corpus) -> None:
        embedder = EvalEmbedder()
        hms_loe.ingest(empty_corpus, embedder)
        cur = empty_corpus.conn.execute("SELECT id, text FROM chunks")
        for row in cur:
            assert row["text"] and len(row["text"].strip()) > 10, (
                f"chunk {row['id']} has empty/short text"
            )

    def test_hash_before_after_is_defined_type(self, empty_corpus: Corpus) -> None:
        h_empty = empty_corpus.content_hash()
        assert isinstance(h_empty, str)
        assert len(h_empty) == 64

        embedder = EvalEmbedder()
        hms_loe.ingest(empty_corpus, embedder)
        h_full = empty_corpus.content_hash()
        assert isinstance(h_full, str)
        assert len(h_full) == 64
        # Non-empty corpus must have a different hash than empty.
        assert h_empty != h_full
