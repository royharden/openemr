"""Unit tests for app/extractors/intake_form.py (Wk2 Workstream A, §15.5)."""

from __future__ import annotations

import hashlib
import os
from unittest.mock import patch

import pytest

os.environ["COPILOT_EVAL_MODE"] = "1"

from app.extractors.intake_form import (
    _detect_media_type,
    _sha256_bytes,
    _words_match,
    extract_intake_form,
)


FAKE_SHA256 = "b" * 64
PATIENT_HASH = hashlib.sha256(b"patient-uuid-intake").hexdigest()


def _make_minimal_pdf() -> bytes:
    return b"""%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]>>endobj
xref
0 4
0000000000 65535 f\r
0000000009 00000 n\r
0000000058 00000 n\r
0000000115 00000 n\r
trailer<</Size 4/Root 1 0 R>>
startxref
214
%%EOF
"""


_PNG_HEADER = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100


# ---------------------------------------------------------------------------
# Positive tests
# ---------------------------------------------------------------------------


class TestExtractIntakeFormPositive:
    def test_chen_intake_has_chief_complaint(self) -> None:
        pdf = _make_minimal_pdf()
        result = extract_intake_form(
            content=pdf,
            patient_uuid_hash=PATIENT_HASH,
            document_sha256=FAKE_SHA256,
            filename="p01-chen-intake-typed.pdf",
        )
        names = [f["name"] for f in result["result"]["fields"]]
        assert "chief_complaint" in names

    def test_chen_intake_has_vitals(self) -> None:
        pdf = _make_minimal_pdf()
        result = extract_intake_form(
            content=pdf,
            patient_uuid_hash=PATIENT_HASH,
            document_sha256=FAKE_SHA256,
            filename="p01-chen-intake-typed.pdf",
        )
        names = [f["name"] for f in result["result"]["fields"]]
        assert any("vitals" in n for n in names)

    def test_doc_type_is_intake_form(self) -> None:
        pdf = _make_minimal_pdf()
        result = extract_intake_form(
            content=pdf,
            patient_uuid_hash=PATIENT_HASH,
            document_sha256=FAKE_SHA256,
            filename="p01-chen-intake-typed.pdf",
        )
        assert result["doc_type"] == "intake_form"

    def test_whitaker_intake_has_smoking_status(self) -> None:
        pdf = _make_minimal_pdf()
        result = extract_intake_form(
            content=pdf,
            patient_uuid_hash=PATIENT_HASH,
            document_sha256=FAKE_SHA256,
            filename="p02-whitaker-intake.pdf",
        )
        names = [f["name"] for f in result["result"]["fields"]]
        assert "smoking_status" in names

    def test_source_packets_have_correct_source_type(self) -> None:
        pdf = _make_minimal_pdf()
        result = extract_intake_form(
            content=pdf,
            patient_uuid_hash=PATIENT_HASH,
            document_sha256=FAKE_SHA256,
            filename="p01-chen-intake-typed.pdf",
        )
        for pkt in result["source_packets"]:
            assert pkt["source_type"] == "document_extract"


# ---------------------------------------------------------------------------
# Negative tests
# ---------------------------------------------------------------------------


class TestExtractIntakeFormNegative:
    def test_unknown_fixture_returns_empty(self) -> None:
        pdf = _make_minimal_pdf()
        result = extract_intake_form(
            content=pdf,
            patient_uuid_hash=PATIENT_HASH,
            document_sha256=FAKE_SHA256,
            filename="xyz-unknown.pdf",
        )
        assert result["extracted_field_count"] == 0

    def test_too_many_pages_raises(self) -> None:
        pdf = _make_minimal_pdf()
        import app.extractors._eval_mocks_a as _mocks_mod
        original = _mocks_mod._EVAL_MODE
        _mocks_mod._EVAL_MODE = False
        try:
            with patch("app.extractors.intake_form._get_page_count_pdf", return_value=11):
                with pytest.raises(ValueError, match="maximum is 10"):
                    extract_intake_form(
                        content=pdf,
                        patient_uuid_hash=PATIENT_HASH,
                        document_sha256=FAKE_SHA256,
                        filename="big.pdf",
                    )
        finally:
            _mocks_mod._EVAL_MODE = original

    def test_reyes_intake_handwritten_has_no_bbox(self) -> None:
        """Handwritten (image) intake forms yield None bbox — acceptable."""
        pdf = _make_minimal_pdf()
        result = extract_intake_form(
            content=pdf,
            patient_uuid_hash=PATIENT_HASH,
            document_sha256=FAKE_SHA256,
            filename="p03-reyes-intake.png",
        )
        for pkt in result["source_packets"]:
            assert pkt["bbox"] is None


# ---------------------------------------------------------------------------
# Edge tests
# ---------------------------------------------------------------------------


class TestExtractIntakeFormEdge:
    def test_detect_media_type_pdf(self) -> None:
        assert _detect_media_type(b"%PDF-1.4") == "application/pdf"

    def test_detect_media_type_png(self) -> None:
        assert _detect_media_type(_PNG_HEADER) == "image/png"

    def test_detect_media_type_jpeg(self) -> None:
        assert _detect_media_type(b"\xff\xd8\xff\xe0") == "image/jpeg"

    def test_detect_media_type_fallback_by_extension(self) -> None:
        assert _detect_media_type(b"", "form.png") == "image/png"

    def test_kowalski_intake_has_bp(self) -> None:
        pdf = _make_minimal_pdf()
        result = extract_intake_form(
            content=pdf,
            patient_uuid_hash=PATIENT_HASH,
            document_sha256=FAKE_SHA256,
            filename="p04-kowalski-intake.png",
        )
        names = [f["name"] for f in result["result"]["fields"]]
        assert any("bp" in n for n in names)
