"""L1: Domain-specific source filters for evidence retrieval (AgDR-0080).

Two layers under test:
  1. ``HybridRetriever.query(..., filters=RetrievalFilters(...))`` —
     filters at retrieval time (BM25 post-hoc; vector pushed to SQL).
  2. ``app.graph.nodes._classify_question_for_filter`` — deterministic
     keyword classifier that picks a source-organization filter set
     based on the question text. The intent (per Plan §7.2.d) is the
     cheap quality lever: vaccine questions don't consider openFDA;
     drug-safety questions don't consider CDC ACIP.

Plan §15.5.6 — positive/negative/edge per rule.
"""

from __future__ import annotations

import pytest

from app.graph.nodes import _classify_question_for_filter
from app.rag._eval_mocks import EvalEmbedder
from app.rag.contracts import GuidelineChunk
from app.rag.corpus import Corpus
from app.rag.retriever import HybridRetriever, RetrievalFilters


def _make_chunk(
    chunk_id: str,
    text: str,
    org: str,
    grade: str | None = None,
    year: int = 2024,
) -> GuidelineChunk:
    return GuidelineChunk(
        chunk_id=chunk_id,
        source_id=f"src-{chunk_id}",
        source_organization=org,
        source_name=f"{org} document",
        page_or_section="§test",
        text=text,
        recommendation_grade=grade,
        source_year=year,
    )


@pytest.fixture
def mixed_corpus() -> Corpus:
    """A corpus with one chunk per source organization so we can assert
    the source filter actually eliminates rows."""
    corpus = Corpus(path=":memory:")
    corpus.open()
    corpus.ensure_schema()
    embedder = EvalEmbedder()
    chunks = [
        _make_chunk("acip-tdap", "Tdap booster every ten years for adults age 19+ vaccine immunization schedule", "CDC-ACIP", grade="A", year=2024),
        _make_chunk("acip-flu", "Influenza vaccination annually recommended adults age 65+ immunization", "CDC-ACIP", grade="A", year=2024),
        _make_chunk("fda-metformin", "Metformin renal dosing creatinine clearance threshold drug safety contraindicated below 30", "FDA", grade=None, year=2023),
        _make_chunk("fda-warfarin", "Warfarin INR monitoring drug safety bleeding risk anticoagulation", "FDA", grade=None, year=2022),
        _make_chunk("ada-statin", "Statin therapy hyperlipidemia diabetes guideline grade A recommendation", "ADA", grade="A", year=2024),
        _make_chunk("acc-ldl", "LDL target secondary prevention atorvastatin grade B recommendation", "ACC-AHA", grade="B", year=2024),
        _make_chunk("hms-loe-ckd", "Chronic kidney disease management glomerular filtration rate evidence summary", "HMS-LOE", grade="C", year=2025),
    ]
    for chunk in chunks:
        corpus.upsert_chunk(chunk, embedding=embedder.embed_one(chunk.text))
    return corpus


# ---------------------------------------------------------------------------
# Question classifier (positive / negative / edge)
# ---------------------------------------------------------------------------


class TestQuestionClassifierPositive:
    def test_vaccine_question_routes_to_acip(self) -> None:
        category, sources = _classify_question_for_filter("Is the patient due for a Tdap vaccine?")
        assert category == "vaccine"
        assert sources == ["CDC-ACIP"]

    def test_immunization_synonym_routes_to_acip(self) -> None:
        category, sources = _classify_question_for_filter("What is her immunization status?")
        assert category == "vaccine"
        assert sources == ["CDC-ACIP"]

    def test_booster_synonym_routes_to_acip(self) -> None:
        category, sources = _classify_question_for_filter("Does he need a flu booster this year?")
        assert category == "vaccine"
        assert sources == ["CDC-ACIP"]

    def test_drug_safety_question_excludes_acip(self) -> None:
        category, sources = _classify_question_for_filter("Is metformin safe at this eGFR?")
        assert category == "drug_safety"
        assert sources is not None
        assert "CDC-ACIP" not in sources
        assert "FDA" in sources

    def test_contraindication_synonym_routes_to_drug_safety(self) -> None:
        category, sources = _classify_question_for_filter("Are there any contraindications to warfarin?")
        assert category == "drug_safety"
        assert sources is not None and "FDA" in sources

    def test_dose_keyword_routes_to_drug_safety(self) -> None:
        category, sources = _classify_question_for_filter("What's the right dose for atorvastatin?")
        assert category == "drug_safety"
        assert sources is not None and "FDA" in sources


class TestQuestionClassifierNegative:
    def test_lab_interpretation_question_is_broad(self) -> None:
        """Lab interp questions should NOT trigger a filter (broad)."""
        category, sources = _classify_question_for_filter("What's her A1c trend?")
        assert category == "broad"
        assert sources is None

    def test_general_status_question_is_broad(self) -> None:
        category, sources = _classify_question_for_filter("Summarize this patient's chart for me.")
        assert category == "broad"
        assert sources is None


class TestQuestionClassifierEdge:
    def test_vaccine_wins_when_both_keywords_present(self) -> None:
        """'is the booster safe given her allergies?' contains both 'booster'
        (vaccine) AND 'safe' (drug-safety). Vaccine wins because the canonical
        vaccine question 'is X safe given my history' would otherwise route
        to drug-safety on the 'safe' keyword and miss the ACIP citation."""
        category, sources = _classify_question_for_filter("Is the booster safe given her allergies?")
        assert category == "vaccine"
        assert sources == ["CDC-ACIP"]

    def test_empty_question_is_broad(self) -> None:
        category, sources = _classify_question_for_filter("")
        assert category == "broad"
        assert sources is None

    def test_case_insensitive(self) -> None:
        category, _ = _classify_question_for_filter("VACCINE schedule for adults?")
        assert category == "vaccine"


# ---------------------------------------------------------------------------
# HybridRetriever filter behavior (positive / negative / edge)
# ---------------------------------------------------------------------------


class TestRetrieverFilterPositive:
    def test_vaccine_filter_yields_only_acip_chunks(self, mixed_corpus: Corpus) -> None:
        """Plan §7.2.d coverage: vaccine query yields only CDC-ACIP chunks."""
        retriever = HybridRetriever(mixed_corpus, embedder=EvalEmbedder())
        results = retriever.query(
            "Tdap vaccine immunization booster",
            k=20,
            filters=RetrievalFilters(source_organizations=("CDC-ACIP",)),
        )
        orgs = {c.source_organization for c in results}
        assert orgs <= {"CDC-ACIP"}, (
            f"Vaccine filter leaked non-ACIP source(s): {orgs - {'CDC-ACIP'}}"
        )
        assert len(results) >= 1, "vaccine filter eliminated all chunks"

    def test_drug_safety_filter_excludes_acip(self, mixed_corpus: Corpus) -> None:
        """Plan §7.2.d coverage: drug-safety query excludes ACIP."""
        retriever = HybridRetriever(mixed_corpus, embedder=EvalEmbedder())
        results = retriever.query(
            "metformin drug safety contraindication renal",
            k=20,
            filters=RetrievalFilters(
                source_organizations=("FDA", "ACC-AHA", "ADA", "HMS-LOE"),
            ),
        )
        orgs = {c.source_organization for c in results}
        assert "CDC-ACIP" not in orgs, (
            "drug-safety filter leaked CDC-ACIP into results"
        )
        assert orgs <= {"FDA", "ACC-AHA", "ADA", "HMS-LOE"}

    def test_no_filter_returns_mixed_orgs(self, mixed_corpus: Corpus) -> None:
        """Sanity check: with no filter, multi-org results are possible."""
        retriever = HybridRetriever(mixed_corpus, embedder=EvalEmbedder())
        results = retriever.query("vaccine drug renal lab", k=20)
        orgs = {c.source_organization for c in results}
        assert len(orgs) >= 2, (
            f"Expected at least 2 orgs in unfiltered result, got {orgs}"
        )


class TestRetrieverFilterNegative:
    def test_filter_to_nonexistent_org_returns_empty(self, mixed_corpus: Corpus) -> None:
        """Filtering to an organization not in the corpus produces zero results
        — eval-case ``min_candidates`` floor catches over-tight configurations."""
        retriever = HybridRetriever(mixed_corpus, embedder=EvalEmbedder())
        results = retriever.query(
            "any query",
            k=20,
            filters=RetrievalFilters(source_organizations=("NOT-A-REAL-ORG",)),
        )
        assert results == []


class TestRetrieverFilterEdge:
    def test_year_window_filter(self, mixed_corpus: Corpus) -> None:
        """year_window restricts vector results at the SQL layer and BM25
        post-hoc. 2024-only window should drop the FDA-warfarin (2022) and
        FDA-metformin (2023) chunks."""
        retriever = HybridRetriever(mixed_corpus, embedder=EvalEmbedder())
        results = retriever.query(
            "drug safety vaccine guideline",
            k=20,
            filters=RetrievalFilters(year_window=(2024, 2024)),
        )
        years = {c.source_year for c in results}
        assert years <= {2024}, f"year_window filter let through: {years - {2024}}"

    def test_min_grade_drops_lower_graded_chunks(self, mixed_corpus: Corpus) -> None:
        """min_grade='B' should accept A+B chunks, drop C, and KEEP ungraded
        (FDA labels have grade=None — not on the ABCD scale, bypassed)."""
        retriever = HybridRetriever(mixed_corpus, embedder=EvalEmbedder())
        results = retriever.query(
            "vaccine statin LDL CKD drug",
            k=20,
            filters=RetrievalFilters(min_grade="B"),
        )
        # No graded chunk above B should appear.
        for c in results:
            if c.recommendation_grade in {"C", "D"}:
                pytest.fail(
                    f"min_grade=B filter let through {c.chunk_id} with grade {c.recommendation_grade}"
                )

    def test_filters_compose(self, mixed_corpus: Corpus) -> None:
        """Filters AND together — an FDA-only + 2024-only query returns
        nothing because both FDA chunks are 2022/2023."""
        retriever = HybridRetriever(mixed_corpus, embedder=EvalEmbedder())
        results = retriever.query(
            "metformin warfarin",
            k=20,
            filters=RetrievalFilters(
                source_organizations=("FDA",), year_window=(2024, 2024),
            ),
        )
        assert results == []
