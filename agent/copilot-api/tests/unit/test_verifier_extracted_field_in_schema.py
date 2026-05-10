"""Unit tests for verifier rule: extracted_field_in_schema (Wk2 Workstream A, §15.5).

Per §15.5.6: positive / negative / edge cases.
Coverage target: ≥95% of check_extracted_field_in_schema.
"""

from __future__ import annotations

import pytest

from app.schemas import ExtractedField, SourcePacket
from app.verifier import check_extracted_field_in_schema


def _make_field(name: str, value: object = 122.0) -> ExtractedField:
    return ExtractedField(name=name, value=value)


# ---------------------------------------------------------------------------
# Positive tests — should return None (pass)
# ---------------------------------------------------------------------------


class TestExtractedFieldInSchemaPositive:
    def test_known_lab_field_passes(self) -> None:
        field = _make_field("ldl")
        assert check_extracted_field_in_schema(field, "lab_pdf") is None

    def test_known_dotted_intake_field_passes(self) -> None:
        field = _make_field("vitals.bp_systolic")
        assert check_extracted_field_in_schema(field, "intake_form") is None

    def test_cholesterol_total_passes(self) -> None:
        assert check_extracted_field_in_schema(_make_field("cholesterol_total"), "lab_pdf") is None

    def test_chief_complaint_passes(self) -> None:
        assert check_extracted_field_in_schema(_make_field("chief_complaint"), "intake_form") is None

    def test_hba1c_passes_lab(self) -> None:
        assert check_extracted_field_in_schema(_make_field("hba1c"), "lab_pdf") is None

    def test_allergies_self_reported_passes_intake(self) -> None:
        assert check_extracted_field_in_schema(_make_field("allergies.self_reported"), "intake_form") is None

    def test_wbc_passes_lab(self) -> None:
        assert check_extracted_field_in_schema(_make_field("wbc"), "lab_pdf") is None


# ---------------------------------------------------------------------------
# Negative tests — should return VerifierIssue (fail / warning)
# ---------------------------------------------------------------------------


class TestExtractedFieldInSchemaNegative:
    def test_unknown_lab_field_fails(self) -> None:
        field = _make_field("fictional_marker_xyz")
        issue = check_extracted_field_in_schema(field, "lab_pdf")
        assert issue is not None
        assert issue.rule == "extracted_field_in_schema"

    def test_intake_field_in_lab_context_fails(self) -> None:
        """vitals is an intake prefix, not a lab prefix."""
        field = _make_field("vitals.bp_systolic")
        issue = check_extracted_field_in_schema(field, "lab_pdf")
        assert issue is not None

    def test_lab_field_in_intake_context_fails(self) -> None:
        """ldl is a lab field, not in the intake allowlist."""
        field = _make_field("ldl")
        issue = check_extracted_field_in_schema(field, "intake_form")
        assert issue is not None

    def test_unknown_doc_type_fails(self) -> None:
        field = _make_field("ldl")
        issue = check_extracted_field_in_schema(field, "unknown_type")
        assert issue is not None
        assert "unknown doc_type" in issue.detail

    def test_field_with_invalid_chars_fails(self) -> None:
        field = _make_field("LDL VALUE!")
        issue = check_extracted_field_in_schema(field, "lab_pdf")
        assert issue is not None


# ---------------------------------------------------------------------------
# Edge tests
# ---------------------------------------------------------------------------


class TestExtractedFieldInSchemaEdge:
    def test_empty_field_name_fails(self) -> None:
        field = _make_field("")
        issue = check_extracted_field_in_schema(field, "lab_pdf")
        assert issue is not None
        assert "empty" in issue.detail

    def test_whitespace_only_name_fails(self) -> None:
        field = ExtractedField(name="   ")
        issue = check_extracted_field_in_schema(field, "lab_pdf")
        assert issue is not None

    def test_urinalysis_field_passes(self) -> None:
        field = _make_field("ua_protein")
        assert check_extracted_field_in_schema(field, "lab_pdf") is None

    def test_deeply_nested_dotted_intake_field_passes(self) -> None:
        """review_of_systems.anything — root is known."""
        field = _make_field("review_of_systems.cardiovascular")
        assert check_extracted_field_in_schema(field, "intake_form") is None

    def test_uppercase_root_fails(self) -> None:
        """Field names must be snake_case (lowercase first char)."""
        field = _make_field("LDL")
        issue = check_extracted_field_in_schema(field, "lab_pdf")
        assert issue is not None
