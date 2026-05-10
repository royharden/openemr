"""L1: Wk2 SourcePacket extension fields (bbox, citation contract). Backward-compatible with Wk1 packets."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas import SourcePacket


def _wk1_packet() -> dict:
    return {
        "source_id": "lab:a1c:jan",
        "patient_uuid": "uuid-A",
        "resource_type": "Observation",
        "source_table": "procedure_result",
        "field": "result",
        "label": "A1c",
        "value": "7.4",
        "unit": "%",
        "observed_at": "2026-01-15",
        "freshness": "recent",
        "status": "final",
    }


class TestBackwardCompat:
    def test_wk1_packet_validates_unchanged(self) -> None:
        p = SourcePacket(**_wk1_packet())
        assert p.source_type is None
        assert p.bbox is None
        assert p.confidence is None

    def test_wk1_packet_round_trip(self) -> None:
        raw = _wk1_packet()
        p = SourcePacket(**raw)
        # Dumped form: new fields should appear with their None defaults but
        # round-trip must equal the original instance.
        assert SourcePacket.model_validate(p.model_dump()) == p


class TestBboxValidator:
    def test_valid_bbox(self) -> None:
        p = SourcePacket(
            **_wk1_packet(),
            source_type="document_extract",
            bbox=(0.1, 0.2, 0.3, 0.5),
            bbox_unit="exact",
        )
        assert p.bbox == (0.1, 0.2, 0.3, 0.5)

    def test_bbox_out_of_unit_range_rejected(self) -> None:
        with pytest.raises(ValidationError, match="\\[0, 1\\]"):
            SourcePacket(**_wk1_packet(), bbox=(0.0, 0.0, 1.5, 0.5))

    def test_bbox_inverted_rejected(self) -> None:
        with pytest.raises(ValidationError, match="x0<x1"):
            SourcePacket(**_wk1_packet(), bbox=(0.6, 0.1, 0.4, 0.5))

    def test_bbox_zero_area_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SourcePacket(**_wk1_packet(), bbox=(0.5, 0.5, 0.5, 0.5))


class TestConfidenceValidator:
    def test_valid_confidence(self) -> None:
        p = SourcePacket(**_wk1_packet(), confidence=0.85)
        assert p.confidence == 0.85

    def test_confidence_above_one_rejected(self) -> None:
        with pytest.raises(ValidationError, match="\\[0, 1\\]"):
            SourcePacket(**_wk1_packet(), confidence=1.5)

    def test_confidence_negative_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SourcePacket(**_wk1_packet(), confidence=-0.1)

    def test_confidence_zero_allowed(self) -> None:
        # Edge: confidence=0.0 is meaningful (extractor refused to commit).
        p = SourcePacket(**_wk1_packet(), confidence=0.0)
        assert p.confidence == 0.0


class TestSourceTypeLiteral:
    def test_known_source_types(self) -> None:
        for s in ("openemr_packet", "document_extract", "guideline_chunk"):
            SourcePacket(**_wk1_packet(), source_type=s)

    def test_unknown_source_type_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SourcePacket(**_wk1_packet(), source_type="invented")  # type: ignore[arg-type]


class TestBboxUnitLiteral:
    def test_valid_units(self) -> None:
        for u in ("exact", "approximate"):
            SourcePacket(**_wk1_packet(), bbox_unit=u)

    def test_invalid_unit_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SourcePacket(**_wk1_packet(), bbox_unit="approx")  # type: ignore[arg-type]
