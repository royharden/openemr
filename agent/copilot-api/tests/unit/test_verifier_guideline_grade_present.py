"""L1: Verifier rule guideline_grade_present — positive/negative/edge tests.

Plan §15.5.6 — per-rule unit tests with positive/negative/edge.
Coverage target: ≥95% of _rule_guideline_grade_present.

Anti-pattern §13.22: verifier rule edits must update these tests in the same PR.
"""

from __future__ import annotations

import pytest

from app.schemas import SourcePacket
from app.verifier import _rule_guideline_grade_present, VerifierIssue


def _acip_packet(grade: str | None = "A") -> SourcePacket:
    return SourcePacket(
        source_id="acip-pkt-1",
        patient_uuid="00000000-0000-0000-0000-000000000001",
        resource_type="GuidelineChunk",
        source_table="corpus",
        field="text",
        label="ACIP Recommendation",
        source_type="guideline_chunk",
        field_or_chunk_id="chunk-123",
        source_organization="CDC-ACIP",
        recommendation_grade=grade,
        source_year=2024,
    )


def _fda_packet(grade: str | None = None) -> SourcePacket:
    return SourcePacket(
        source_id="fda-pkt-1",
        patient_uuid="00000000-0000-0000-0000-000000000001",
        resource_type="GuidelineChunk",
        source_table="corpus",
        field="text",
        label="Drug Label",
        source_type="guideline_chunk",
        field_or_chunk_id="fda-chunk-1",
        source_organization="FDA",
        recommendation_grade=grade,
        source_year=2023,
    )


def _hms_packet(grade: str | None = "1a") -> SourcePacket:
    return SourcePacket(
        source_id="hms-pkt-1",
        patient_uuid="00000000-0000-0000-0000-000000000001",
        resource_type="GuidelineChunk",
        source_table="corpus",
        field="text",
        label="HMS-LOE Evidence",
        source_type="guideline_chunk",
        field_or_chunk_id="hms-chunk-1",
        source_organization="HMS-LOE",
        recommendation_grade=grade,
        source_year=2022,
    )


class TestGuidelineGradePresentPositive:
    def test_acip_grade_a_passes(self) -> None:
        issues: list[VerifierIssue] = []
        result = _rule_guideline_grade_present(_acip_packet("A"), 0, issues)
        assert result is False
        assert issues == []

    def test_acip_grade_b_passes(self) -> None:
        issues: list[VerifierIssue] = []
        result = _rule_guideline_grade_present(_acip_packet("B"), 0, issues)
        assert result is False
        assert issues == []

    def test_acip_grade_null_passes(self) -> None:
        # Null grade is acceptable for ACIP guidance without formal category.
        issues: list[VerifierIssue] = []
        result = _rule_guideline_grade_present(_acip_packet(None), 0, issues)
        assert result is False

    def test_fda_packet_exempt(self) -> None:
        # FDA labels never have recommendation grades — must not fire.
        issues: list[VerifierIssue] = []
        result = _rule_guideline_grade_present(_fda_packet(None), 0, issues)
        assert result is False
        assert issues == []

    def test_hms_packet_exempt(self) -> None:
        # HMS-LOE uses CEBM levels — rule must not fire for HMS-LOE.
        issues: list[VerifierIssue] = []
        result = _rule_guideline_grade_present(_hms_packet("1a"), 0, issues)
        assert result is False


class TestGuidelineGradePresentNegative:
    def test_acip_invalid_grade_fails(self) -> None:
        issues: list[VerifierIssue] = []
        result = _rule_guideline_grade_present(_acip_packet("X"), 0, issues)
        assert result is True
        assert len(issues) == 1
        assert issues[0].rule == "guideline_grade_present"
        assert "X" in issues[0].detail

    def test_acip_grade_c_fails(self) -> None:
        # "C" is a USPSTF grade, not a valid ACIP grade.
        issues: list[VerifierIssue] = []
        result = _rule_guideline_grade_present(_acip_packet("C"), 0, issues)
        assert result is True

    def test_non_guideline_packet_skipped(self) -> None:
        pkt = SourcePacket(
            source_id="openemr-pkt",
            patient_uuid="00000000-0000-0000-0000-000000000001",
            resource_type="Observation",
            source_table="procedure_result",
            field="result",
            label="Lab",
        )
        issues: list[VerifierIssue] = []
        result = _rule_guideline_grade_present(pkt, 0, issues)
        assert result is False


class TestGuidelineGradePresentEdge:
    def test_claim_index_in_issue(self) -> None:
        issues: list[VerifierIssue] = []
        _rule_guideline_grade_present(_acip_packet("Z"), 7, issues)
        assert issues[0].claim_index == 7

    def test_empty_string_grade_fails(self) -> None:
        # Empty string is not a valid ACIP grade.
        pkt = _acip_packet("")
        issues: list[VerifierIssue] = []
        result = _rule_guideline_grade_present(pkt, 0, issues)
        assert result is True

    def test_lowercase_grade_fails(self) -> None:
        # Grades are expected uppercase.
        issues: list[VerifierIssue] = []
        result = _rule_guideline_grade_present(_acip_packet("a"), 0, issues)
        assert result is True
