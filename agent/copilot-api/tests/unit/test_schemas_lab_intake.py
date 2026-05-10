"""L1: Pydantic round-trip + validation for Wk2 LabResult/IntakeFields/ExtractedDocument shells (W0.5)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas import (
    ExtractedDocument,
    ExtractedField,
    IntakeFields,
    LabResult,
    SourcePacket,
)

# Convenience: a 64-char placeholder hex string for document_sha256 fields.
_SHA64 = "a" * 64


def _packet(field: str = "ldl") -> SourcePacket:
    return SourcePacket(
        source_id=f"doc:{_SHA64}:{field}",
        patient_uuid="uuid-A",
        resource_type="DocumentReference",
        source_table="copilot_document_facts",
        field=field,
        label=field,
        value="120",
        source_type="document_extract",
        page_or_section="Lipid Panel",
        field_or_chunk_id=field,
        quote_or_value="LDL 120 mg/dL",
        bbox=(0.1, 0.2, 0.3, 0.25),
        bbox_unit="exact",
        confidence=1.0,
        page_index=0,
    )


class TestExtractedField:
    def test_minimal_round_trip(self) -> None:
        f = ExtractedField(name="ldl")
        assert f.name == "ldl"
        assert f.value is None
        assert f.citation is None

    def test_with_citation(self) -> None:
        f = ExtractedField(name="ldl", value="120", unit="mg/dL", citation=_packet())
        round_tripped = ExtractedField.model_validate(f.model_dump())
        assert round_tripped == f

    def test_name_max_length(self) -> None:
        with pytest.raises(ValidationError):
            ExtractedField(name="x" * 200)


class TestLabResult:
    def test_round_trip_empty_fields(self) -> None:
        r = LabResult(
            document_sha256=_SHA64,
            page_count=1,
            extracted_at="2026-05-09T20:00:00Z",
            extracted_by_model="claude-sonnet-4-6",
        )
        assert r.fields == []
        assert LabResult.model_validate(r.model_dump()) == r

    def test_with_fields(self) -> None:
        r = LabResult(
            document_sha256=_SHA64,
            page_count=2,
            extracted_at="2026-05-09T20:00:00Z",
            extracted_by_model="claude-sonnet-4-6",
            fields=[
                ExtractedField(name="ldl", value="120", unit="mg/dL", citation=_packet()),
                ExtractedField(name="hdl", value="55", unit="mg/dL"),
            ],
        )
        assert len(r.fields) == 2
        assert LabResult.model_validate(r.model_dump()) == r

    def test_sha256_must_be_64_chars(self) -> None:
        with pytest.raises(ValidationError):
            LabResult(
                document_sha256="abc",
                page_count=1,
                extracted_at="2026-05-09T20:00:00Z",
                extracted_by_model="claude-sonnet-4-6",
            )

    def test_page_count_min(self) -> None:
        with pytest.raises(ValidationError):
            LabResult(
                document_sha256=_SHA64,
                page_count=0,
                extracted_at="2026-05-09T20:00:00Z",
                extracted_by_model="claude-sonnet-4-6",
            )


class TestIntakeFields:
    def test_round_trip(self) -> None:
        i = IntakeFields(
            document_sha256=_SHA64,
            page_count=1,
            extracted_at="2026-05-09T20:00:00Z",
            extracted_by_model="claude-sonnet-4-6",
            fields=[ExtractedField(name="chief_complaint", value="chest pain")],
        )
        assert IntakeFields.model_validate(i.model_dump()) == i


class TestExtractedDocument:
    def test_lab_envelope(self) -> None:
        result = LabResult(
            document_sha256=_SHA64,
            page_count=1,
            extracted_at="2026-05-09T20:00:00Z",
            extracted_by_model="claude-sonnet-4-6",
            fields=[ExtractedField(name="ldl", value="120", citation=_packet())],
        )
        env = ExtractedDocument(
            doc_type="lab_pdf",
            document_sha256=_SHA64,
            result=result,
            source_packets=[_packet()],
            extracted_field_count=1,
        )
        assert env.doc_type == "lab_pdf"
        assert isinstance(env.result, LabResult)
        assert ExtractedDocument.model_validate(env.model_dump()) == env

    def test_intake_envelope(self) -> None:
        result = IntakeFields(
            document_sha256=_SHA64,
            page_count=1,
            extracted_at="2026-05-09T20:00:00Z",
            extracted_by_model="claude-sonnet-4-6",
        )
        env = ExtractedDocument(
            doc_type="intake_form",
            document_sha256=_SHA64,
            result=result,
        )
        assert env.doc_type == "intake_form"
        assert isinstance(env.result, IntakeFields)

    def test_doc_type_enum(self) -> None:
        result = LabResult(
            document_sha256=_SHA64,
            page_count=1,
            extracted_at="2026-05-09T20:00:00Z",
            extracted_by_model="claude-sonnet-4-6",
        )
        with pytest.raises(ValidationError):
            ExtractedDocument(doc_type="discharge_summary", document_sha256=_SHA64, result=result)  # type: ignore[arg-type]
