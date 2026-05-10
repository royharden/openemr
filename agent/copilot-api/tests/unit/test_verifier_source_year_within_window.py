"""L1: Verifier rule source_year_within_window — positive/negative/edge tests.

Plan §15.5.6 — per-rule unit tests with positive/negative/edge.
Coverage target: ≥95% of _rule_source_year_within_window.

Anti-pattern §13.22: verifier rule edits must update these tests in the same PR.
"""

from __future__ import annotations

import datetime
from unittest.mock import patch

import pytest

from app.schemas import SourcePacket
from app.verifier import (
    _rule_source_year_within_window,
    SOURCE_YEAR_WINDOW_YEARS,
    VerifierIssue,
)

CURRENT_YEAR = datetime.date.today().year
CUTOFF = CURRENT_YEAR - SOURCE_YEAR_WINDOW_YEARS


def _guideline_packet(year: int | None = 2024, org: str = "CDC-ACIP") -> SourcePacket:
    return SourcePacket(
        source_id="pkt-year",
        patient_uuid="00000000-0000-0000-0000-000000000001",
        resource_type="GuidelineChunk",
        source_table="corpus",
        field="text",
        label="Recommendation",
        source_type="guideline_chunk",
        field_or_chunk_id="chunk-1",
        source_organization=org,
        source_year=year,
    )


class TestSourceYearWithinWindowPositive:
    def test_recent_year_passes(self) -> None:
        issues: list[VerifierIssue] = []
        pkt = _guideline_packet(year=CURRENT_YEAR)
        result = _rule_source_year_within_window(pkt, 0, issues)
        assert result is False
        assert issues == []

    def test_year_at_cutoff_passes(self) -> None:
        issues: list[VerifierIssue] = []
        pkt = _guideline_packet(year=CUTOFF)
        result = _rule_source_year_within_window(pkt, 0, issues)
        assert result is False

    def test_null_year_passes(self) -> None:
        issues: list[VerifierIssue] = []
        pkt = _guideline_packet(year=None)
        result = _rule_source_year_within_window(pkt, 0, issues)
        assert result is False
        assert issues == []

    def test_non_guideline_packet_skipped(self) -> None:
        pkt = SourcePacket(
            source_id="openemr-pkt",
            patient_uuid="00000000-0000-0000-0000-000000000001",
            resource_type="Observation",
            source_table="procedure_result",
            field="result",
            label="Lab",
            source_year=1990,  # old year but not a guideline chunk
        )
        issues: list[VerifierIssue] = []
        result = _rule_source_year_within_window(pkt, 0, issues)
        assert result is False


class TestSourceYearWithinWindowNegative:
    def test_old_year_fails(self) -> None:
        issues: list[VerifierIssue] = []
        pkt = _guideline_packet(year=CUTOFF - 1)
        result = _rule_source_year_within_window(pkt, 0, issues)
        assert result is True
        assert len(issues) == 1
        assert issues[0].rule == "source_year_within_window"
        assert str(CUTOFF - 1) in issues[0].detail

    def test_very_old_year_fails(self) -> None:
        issues: list[VerifierIssue] = []
        pkt = _guideline_packet(year=1990)
        result = _rule_source_year_within_window(pkt, 0, issues)
        assert result is True

    def test_fda_old_chunk_fails(self) -> None:
        # FDA is not exempt from year staleness check.
        issues: list[VerifierIssue] = []
        pkt = _guideline_packet(year=CUTOFF - 5, org="FDA")
        result = _rule_source_year_within_window(pkt, 0, issues)
        assert result is True


class TestSourceYearWithinWindowEdge:
    def test_claim_index_propagated(self) -> None:
        issues: list[VerifierIssue] = []
        pkt = _guideline_packet(year=CUTOFF - 1)
        _rule_source_year_within_window(pkt, 99, issues)
        assert issues[0].claim_index == 99

    def test_year_one_above_cutoff_passes(self) -> None:
        issues: list[VerifierIssue] = []
        pkt = _guideline_packet(year=CUTOFF + 1)
        result = _rule_source_year_within_window(pkt, 0, issues)
        assert result is False

    def test_document_extract_packet_skipped(self) -> None:
        pkt = SourcePacket(
            source_id="doc-pkt",
            patient_uuid="00000000-0000-0000-0000-000000000001",
            resource_type="DocumentField",
            source_table="copilot_document_facts",
            field="ldl",
            label="LDL",
            source_type="document_extract",
            source_year=1990,
        )
        issues: list[VerifierIssue] = []
        result = _rule_source_year_within_window(pkt, 0, issues)
        assert result is False

    def test_window_constant_matches_implementation(self) -> None:
        # SOURCE_YEAR_WINDOW_YEARS is the public constant used by callers.
        assert SOURCE_YEAR_WINDOW_YEARS == 10
