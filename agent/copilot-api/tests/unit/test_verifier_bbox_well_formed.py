"""Unit tests for verifier rule: bbox_well_formed (Wk2 Workstream A, §15.5).

Per §15.5.6: each rule needs positive / negative / edge cases.
Coverage target: ≥95% of the check_bbox_well_formed function.
"""

from __future__ import annotations

import pytest

from app.schemas import SourcePacket
from app.verifier import check_bbox_well_formed


def _make_packet(bypass_validation: bool = False, **overrides: object) -> SourcePacket:
    """Build a SourcePacket, optionally bypassing Pydantic validators.

    bypass_validation=True uses model_construct so we can test the verifier
    rule against out-of-range bboxes that Pydantic would normally reject.
    """
    base: dict[str, object] = {
        "source_id": "doc:aabbcc112233:page0:ldl",
        "patient_uuid": "patient-123",
        "resource_type": "DocumentFact",
        "source_table": "copilot_document_facts",
        "field": "ldl",
        "label": "Ldl",
        "value": 122.0,
        "source_type": "document_extract",
        "bbox": (0.10, 0.30, 0.55, 0.40),
        "bbox_unit": "exact",
    }
    base.update(overrides)
    if bypass_validation:
        return SourcePacket.model_construct(**base)  # type: ignore[arg-type]
    return SourcePacket(**base)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Positive tests — should return None (pass)
# ---------------------------------------------------------------------------


class TestBboxWellFormedPositive:
    def test_valid_exact_bbox_passes(self) -> None:
        pkt = _make_packet(bbox=(0.1, 0.3, 0.5, 0.4), bbox_unit="exact")
        assert check_bbox_well_formed(pkt) is None

    def test_valid_approximate_bbox_passes(self) -> None:
        pkt = _make_packet(bbox=(0.0, 0.0, 1.0, 1.0), bbox_unit="approximate")
        assert check_bbox_well_formed(pkt) is None

    def test_none_bbox_passes(self) -> None:
        """bbox=None means no bbox supplied — rule should pass."""
        pkt = _make_packet(bbox=None, bbox_unit=None)
        assert check_bbox_well_formed(pkt) is None

    def test_non_document_extract_packet_passes(self) -> None:
        """Rule only fires on document_extract packets."""
        pkt = _make_packet(source_type="openemr_packet", bbox=(0.1, 0.2, 0.3, 0.4), bbox_unit="exact")
        assert check_bbox_well_formed(pkt) is None

    def test_small_valid_bbox_passes(self) -> None:
        pkt = _make_packet(bbox=(0.01, 0.01, 0.02, 0.02), bbox_unit="exact")
        assert check_bbox_well_formed(pkt) is None


# ---------------------------------------------------------------------------
# Negative tests — should return VerifierIssue (fail)
# ---------------------------------------------------------------------------


class TestBboxWellFormedNegative:
    def test_x0_exceeds_1_fails(self) -> None:
        # bypass Pydantic to test the verifier sees out-of-range coords
        pkt = _make_packet(bypass_validation=True, bbox=(1.1, 0.3, 1.5, 0.4), bbox_unit="exact")
        issue = check_bbox_well_formed(pkt)
        assert issue is not None
        assert issue.rule == "bbox_well_formed"
        assert "x0" in issue.detail

    def test_negative_coordinate_fails(self) -> None:
        pkt = _make_packet(bypass_validation=True, bbox=(-0.1, 0.3, 0.5, 0.4), bbox_unit="exact")
        issue = check_bbox_well_formed(pkt)
        assert issue is not None
        assert "x0" in issue.detail

    def test_x0_equals_x1_fails(self) -> None:
        pkt = _make_packet(bypass_validation=True, bbox=(0.3, 0.2, 0.3, 0.5), bbox_unit="exact")
        issue = check_bbox_well_formed(pkt)
        assert issue is not None
        assert "x0" in issue.detail or "x1" in issue.detail

    def test_y0_equals_y1_fails(self) -> None:
        pkt = _make_packet(bypass_validation=True, bbox=(0.1, 0.5, 0.5, 0.5), bbox_unit="exact")
        issue = check_bbox_well_formed(pkt)
        assert issue is not None
        assert "y0" in issue.detail or "y1" in issue.detail

    def test_x0_greater_than_x1_fails(self) -> None:
        pkt = _make_packet(bypass_validation=True, bbox=(0.6, 0.2, 0.3, 0.5), bbox_unit="exact")
        issue = check_bbox_well_formed(pkt)
        assert issue is not None

    def test_y0_greater_than_y1_fails(self) -> None:
        pkt = _make_packet(bypass_validation=True, bbox=(0.1, 0.8, 0.5, 0.2), bbox_unit="exact")
        issue = check_bbox_well_formed(pkt)
        assert issue is not None

    def test_invalid_bbox_unit_fails(self) -> None:
        pkt = _make_packet(bypass_validation=True, bbox=(0.1, 0.2, 0.5, 0.6), bbox_unit="fuzzy")
        issue = check_bbox_well_formed(pkt)
        assert issue is not None
        assert "bbox_unit" in issue.detail

    def test_none_bbox_unit_fails_when_bbox_present(self) -> None:
        pkt = _make_packet(bypass_validation=True, bbox=(0.1, 0.2, 0.5, 0.6), bbox_unit=None)
        issue = check_bbox_well_formed(pkt)
        assert issue is not None


# ---------------------------------------------------------------------------
# Edge tests
# ---------------------------------------------------------------------------


class TestBboxWellFormedEdge:
    def test_boundary_zero_to_one_passes(self) -> None:
        pkt = _make_packet(bbox=(0.0, 0.0, 1.0, 1.0), bbox_unit="approximate")
        assert check_bbox_well_formed(pkt) is None

    def test_all_zeros_fails_non_degenerate_check(self) -> None:
        """(0, 0, 0, 0) has x0==x1 and y0==y1 — must fail."""
        pkt = _make_packet(bypass_validation=True, bbox=(0.0, 0.0, 0.0, 0.0), bbox_unit="exact")
        issue = check_bbox_well_formed(pkt)
        assert issue is not None

    def test_issue_references_source_id(self) -> None:
        pkt = _make_packet(bypass_validation=True, bbox=(0.9, 0.2, 0.1, 0.5), bbox_unit="exact")
        issue = check_bbox_well_formed(pkt)
        assert issue is not None
        assert "doc:aabbcc112233:page0:ldl" in issue.detail
