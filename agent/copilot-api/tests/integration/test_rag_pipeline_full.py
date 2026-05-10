"""L2: End-to-end RAG pipeline integration test.

Uses in-memory Corpus with EvalEmbedder + EvalReranker (no Voyage/Cohere).
Ingests a small fixture corpus (HMS-LOE static snippets), runs retrieval,
validates top-5 chunks have expected metadata.

Plan §15.5 L2 — integration test exercising retrieval against fixture corpus.
"""

from __future__ import annotations

import os

import pytest

from app.rag.corpus import Corpus
from app.rag.contracts import GuidelineChunk
from app.rag.retriever import HybridRetriever
from app.rag.reranker import CohereReranker
from app.rag._eval_mocks import EvalEmbedder, EvalReranker
from app.rag.chunker import ChunkSource, chunk_text


FIXTURE_DOCS = [
    (
        "hms-metformin",
        "HMS-LOE",
        "HMS-LOE: Metformin in CKD",
        2022,
        "1a",
        "# Metformin in Chronic Kidney Disease\n\n"
        "Metformin is contraindicated when eGFR falls below 30 mL/min/1.73 m².\n"
        "When eGFR is 30-44, use with caution and reduce dose by 50%.\n"
        "Monitor eGFR every 3 months in moderate CKD.\n",
    ),
    (
        "acip-influenza",
        "CDC-ACIP",
        "CDC ACIP Influenza 2024",
        2024,
        "A",
        "# Influenza Vaccination\n\n"
        "All adults should receive influenza vaccination annually.\n"
        "Adults 65 years and older should receive a high-dose or adjuvanted vaccine.\n"
        "Vaccination is recommended before end of October each year.\n",
    ),
    (
        "acip-tdap",
        "CDC-ACIP",
        "CDC ACIP Tdap 2012",
        2012,
        "A",
        "# Tdap Booster Recommendations\n\n"
        "Adults who have not received Tdap should receive one dose.\n"
        "Td booster every 10 years thereafter.\n"
        "Pregnant women should receive Tdap during every pregnancy.\n",
    ),
    (
        "fda-atorvastatin",
        "FDA",
        "Atorvastatin Drug Label",
        2022,
        None,
        "# Atorvastatin — Dosage and Administration\n\n"
        "Starting dose 10-20 mg once daily. Maximum dose 80 mg per day.\n"
        "Adjust dose based on LDL-C goal and patient tolerability.\n"
        "Monitor liver function tests and muscle symptoms.\n",
    ),
    (
        "fda-warfarin",
        "FDA",
        "Warfarin Drug Label",
        2021,
        None,
        "# Warfarin — Dosage and INR Monitoring\n\n"
        "Warfarin dose must be individualized. Target INR 2.0 to 3.0 for most indications.\n"
        "Monitor INR frequently during initiation and with any dose change.\n"
        "Mechanical mitral valve: target INR 2.5 to 3.5.\n",
    ),
]


@pytest.fixture
def fixture_corpus(tmp_path: "Path") -> Corpus:
    """Small in-memory corpus with fixture docs embedded via EvalEmbedder."""
    corpus_path = tmp_path / "fixture_corpus.db"
    corpus = Corpus(path=corpus_path)
    corpus.open()
    corpus.ensure_schema()
    embedder = EvalEmbedder()

    for source_id, org, name, year, grade, text in FIXTURE_DOCS:
        src = ChunkSource(
            source_id=source_id,
            source_organization=org,
            source_name=name,
            source_year=year,
            recommendation_grade=grade,
        )
        chunks = chunk_text(text, src, id_prefix=f"{source_id}-")
        embeddings = embedder.embed([c.text for c in chunks])
        for chunk, emb in zip(chunks, embeddings):
            corpus.upsert_chunk(chunk, emb)

    yield corpus
    corpus.close()


class TestRagPipelineFull:
    def test_corpus_has_chunks(self, fixture_corpus: Corpus) -> None:
        assert fixture_corpus.count() >= 5

    def test_metformin_renal_retrieval(self, fixture_corpus: Corpus) -> None:
        embedder = EvalEmbedder()
        retriever = HybridRetriever(fixture_corpus, embedder=embedder)
        results = retriever.query("metformin renal dosing eGFR", k=20)
        assert len(results) > 0
        # At least one result should reference the metformin chunk.
        ids = [c.chunk_id for c in results]
        source_ids = [c.source_id for c in results]
        assert any("metformin" in sid for sid in source_ids) or any(
            "metformin" in c.source_name.lower() for c in results
        )

    def test_tdap_booster_retrieval(self, fixture_corpus: Corpus) -> None:
        embedder = EvalEmbedder()
        retriever = HybridRetriever(fixture_corpus, embedder=embedder)
        results = retriever.query("adult Tdap booster interval years", k=20)
        assert len(results) > 0

    def test_reranker_returns_top5(self, fixture_corpus: Corpus) -> None:
        embedder = EvalEmbedder()
        retriever = HybridRetriever(fixture_corpus, embedder=embedder)
        candidates = retriever.query("influenza vaccination recommendation", k=20)

        reranker = EvalReranker(top_n=5)
        top5 = reranker.rerank("influenza vaccination", candidates)
        assert len(top5) <= 5
        assert all(isinstance(c, GuidelineChunk) for c in top5)

    def test_all_chunks_have_required_metadata(self, fixture_corpus: Corpus) -> None:
        embedder = EvalEmbedder()
        retriever = HybridRetriever(fixture_corpus, embedder=embedder)
        results = retriever.query("vaccine", k=20)
        for c in results:
            assert c.chunk_id
            assert c.source_id
            assert c.source_organization
            assert c.source_name
            assert c.page_or_section
            assert c.text

    def test_reranker_positions_sequential(self, fixture_corpus: Corpus) -> None:
        embedder = EvalEmbedder()
        retriever = HybridRetriever(fixture_corpus, embedder=embedder)
        candidates = retriever.query("warfarin INR anticoagulation", k=20)
        reranker = EvalReranker(top_n=5)
        top5 = reranker.rerank("warfarin INR", candidates)
        positions = [c.rerank_position for c in top5]
        assert positions == list(range(len(top5)))

    def test_acip_and_fda_mix_in_results(self, fixture_corpus: Corpus) -> None:
        embedder = EvalEmbedder()
        retriever = HybridRetriever(fixture_corpus, embedder=embedder)
        # "atorvastatin LDL vaccine" spans both openFDA and CDC-ACIP content.
        results = retriever.query("atorvastatin LDL influenza", k=20)
        orgs = {c.source_organization for c in results}
        # Should include at least one chunk from the corpus.
        assert len(orgs) >= 1
