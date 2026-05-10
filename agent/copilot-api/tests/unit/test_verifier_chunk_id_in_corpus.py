"""L1: Verifier rule chunk_id_in_corpus — positive/negative/edge tests.

Plan §15.5.6 — per-rule unit tests with positive/negative/edge.
Coverage target: ≥95% of _rule_chunk_id_in_corpus.

Anti-pattern §13.22: verifier rule edits must update these tests in the same PR.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.schemas import SourcePacket
from app.verifier import (
    _rule_chunk_id_in_corpus,
    set_corpus_for_verifier,
    VerifierIssue,
)


def _guideline_packet(chunk_id: str | None = "chunk-abc123") -> SourcePacket:
    return SourcePacket(
        source_id="pkt-1",
        patient_uuid="00000000-0000-0000-0000-000000000001",
        resource_type="GuidelineChunk",
        source_table="corpus",
        field="text",
        label="ACIP Recommendation",
        source_type="guideline_chunk",
        field_or_chunk_id=chunk_id,
        source_organization="CDC-ACIP",
        recommendation_grade="A",
        source_year=2024,
    )


def _openemr_packet() -> SourcePacket:
    return SourcePacket(
        source_id="pkt-openemr",
        patient_uuid="00000000-0000-0000-0000-000000000001",
        resource_type="Observation",
        source_table="procedure_result",
        field="result",
        label="Lab Result",
    )


@pytest.fixture(autouse=True)
def reset_corpus() -> None:
    set_corpus_for_verifier(None)
    yield
    set_corpus_for_verifier(None)


class TestChunkIdInCorpusPositive:
    def test_chunk_exists_passes(self) -> None:
        mock_corpus = MagicMock()
        mock_corpus.chunk_exists.return_value = True
        set_corpus_for_verifier(mock_corpus)

        issues: list[VerifierIssue] = []
        result = _rule_chunk_id_in_corpus(_guideline_packet("chunk-abc"), 0, issues)
        assert result is False
        assert issues == []

    def test_non_guideline_packet_always_passes(self) -> None:
        mock_corpus = MagicMock()
        mock_corpus.chunk_exists.return_value = False
        set_corpus_for_verifier(mock_corpus)

        issues: list[VerifierIssue] = []
        result = _rule_chunk_id_in_corpus(_openemr_packet(), 0, issues)
        assert result is False
        assert issues == []

    def test_no_corpus_registered_passes(self) -> None:
        set_corpus_for_verifier(None)
        issues: list[VerifierIssue] = []
        result = _rule_chunk_id_in_corpus(_guideline_packet("any-id"), 0, issues)
        assert result is False


class TestChunkIdInCorpusNegative:
    def test_chunk_absent_fails(self) -> None:
        mock_corpus = MagicMock()
        mock_corpus.chunk_exists.return_value = False
        set_corpus_for_verifier(mock_corpus)

        issues: list[VerifierIssue] = []
        result = _rule_chunk_id_in_corpus(_guideline_packet("missing-chunk"), 0, issues)
        assert result is True
        assert len(issues) == 1
        assert issues[0].rule == "chunk_id_in_corpus"
        assert "missing-chunk" in issues[0].detail

    def test_missing_field_or_chunk_id_fails(self) -> None:
        mock_corpus = MagicMock()
        set_corpus_for_verifier(mock_corpus)

        issues: list[VerifierIssue] = []
        result = _rule_chunk_id_in_corpus(_guideline_packet(None), 0, issues)
        assert result is True
        assert issues[0].rule == "chunk_id_in_corpus"


class TestChunkIdInCorpusEdge:
    def test_corpus_exception_passes_through(self) -> None:
        mock_corpus = MagicMock()
        mock_corpus.chunk_exists.side_effect = RuntimeError("DB error")
        set_corpus_for_verifier(mock_corpus)

        issues: list[VerifierIssue] = []
        result = _rule_chunk_id_in_corpus(_guideline_packet("some-id"), 0, issues)
        # Exception is swallowed — should not drop the claim.
        assert result is False

    def test_claim_index_propagated(self) -> None:
        mock_corpus = MagicMock()
        mock_corpus.chunk_exists.return_value = False
        set_corpus_for_verifier(mock_corpus)

        issues: list[VerifierIssue] = []
        _rule_chunk_id_in_corpus(_guideline_packet("x"), 42, issues)
        assert issues[0].claim_index == 42

    def test_document_extract_packet_skipped(self) -> None:
        mock_corpus = MagicMock()
        mock_corpus.chunk_exists.return_value = False
        set_corpus_for_verifier(mock_corpus)

        pkt = SourcePacket(
            source_id="doc-pkt",
            patient_uuid="00000000-0000-0000-0000-000000000001",
            resource_type="DocumentField",
            source_table="copilot_document_facts",
            field="ldl",
            label="LDL",
            source_type="document_extract",
            field_or_chunk_id="lab.ldl",
        )
        issues: list[VerifierIssue] = []
        result = _rule_chunk_id_in_corpus(pkt, 0, issues)
        assert result is False
