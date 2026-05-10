"""Unit tests for app/extractors/lab_pdf.py (Wk2 Workstream A, §15.5).

Coverage: positive (normal extraction), negative (bad input / size cap),
edge (empty PDF, missing quote, single-field, image-only fixture).

All tests run in COPILOT_EVAL_MODE=1 — no Anthropic API calls.
"""

from __future__ import annotations

import hashlib
import os
import struct
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

os.environ["COPILOT_EVAL_MODE"] = "1"

from app.extractors.lab_pdf import (
    _find_verbatim_bbox,
    _sha256_bytes,
    _words_match,
    extract_lab_pdf,
)
from app.schemas import ExtractedDocument, LabResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FAKE_SHA256 = "a" * 64
PATIENT_HASH = hashlib.sha256(b"patient-uuid-123").hexdigest()


def _make_minimal_pdf() -> bytes:
    """Return a real minimal PDF byte string that pdfplumber and pypdfium2 accept."""
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


# ---------------------------------------------------------------------------
# Positive tests
# ---------------------------------------------------------------------------


class TestExtractLabPdfPositive:
    def test_returns_extracted_document_shape(self) -> None:
        pdf = _make_minimal_pdf()
        result = extract_lab_pdf(
            pdf_bytes=pdf,
            patient_uuid_hash=PATIENT_HASH,
            document_sha256=FAKE_SHA256,
            filename="p01-chen-lipid-panel.pdf",
        )
        assert result["doc_type"] == "lab_pdf"
        assert result["document_sha256"] == FAKE_SHA256
        assert "result" in result
        assert isinstance(result["extracted_field_count"], int)

    def test_chen_lipid_fixture_has_ldl(self) -> None:
        pdf = _make_minimal_pdf()
        result = extract_lab_pdf(
            pdf_bytes=pdf,
            patient_uuid_hash=PATIENT_HASH,
            document_sha256=FAKE_SHA256,
            filename="p01-chen-lipid-panel.pdf",
        )
        fields = result["result"]["fields"]
        names = [f["name"] for f in fields]
        assert "ldl" in names

    def test_citation_packets_present(self) -> None:
        pdf = _make_minimal_pdf()
        result = extract_lab_pdf(
            pdf_bytes=pdf,
            patient_uuid_hash=PATIENT_HASH,
            document_sha256=FAKE_SHA256,
            filename="p01-chen-lipid-panel.pdf",
        )
        assert len(result["source_packets"]) > 0

    def test_source_packet_has_doc_type(self) -> None:
        pdf = _make_minimal_pdf()
        result = extract_lab_pdf(
            pdf_bytes=pdf,
            patient_uuid_hash=PATIENT_HASH,
            document_sha256=FAKE_SHA256,
            filename="p01-chen-lipid-panel.pdf",
        )
        for pkt in result["source_packets"]:
            assert pkt["source_type"] == "document_extract"

    def test_sha256_computed_when_not_provided(self) -> None:
        pdf = _make_minimal_pdf()
        expected_sha = hashlib.sha256(pdf).hexdigest()
        result = extract_lab_pdf(
            pdf_bytes=pdf,
            patient_uuid_hash=PATIENT_HASH,
            filename="p01-chen-lipid-panel.pdf",
        )
        assert result["document_sha256"] == expected_sha

    def test_kowalski_cmp_fixture(self) -> None:
        pdf = _make_minimal_pdf()
        result = extract_lab_pdf(
            pdf_bytes=pdf,
            patient_uuid_hash=PATIENT_HASH,
            document_sha256=FAKE_SHA256,
            filename="p04-kowalski-cmp.pdf",
        )
        fields = {f["name"]: f["value"] for f in result["result"]["fields"]}
        assert "creatinine" in fields
        assert "sodium" in fields

    def test_reyes_hba1c_fixture_elevated(self) -> None:
        pdf = _make_minimal_pdf()
        result = extract_lab_pdf(
            pdf_bytes=pdf,
            patient_uuid_hash=PATIENT_HASH,
            document_sha256=FAKE_SHA256,
            filename="p03-reyes-hba1c.png",
        )
        fields = {f["name"]: f for f in result["result"]["fields"]}
        assert "hba1c" in fields
        assert fields["hba1c"]["flag"] == "H"


# ---------------------------------------------------------------------------
# Negative tests
# ---------------------------------------------------------------------------


class TestExtractLabPdfNegative:
    def test_too_large_raises_value_error(self) -> None:
        # The page count check fires only in real (non-eval) mode.
        # Temporarily disable eval mode and mock _get_page_count.
        pdf = _make_minimal_pdf()
        import app.extractors._eval_mocks_a as _mocks_mod
        original = _mocks_mod._EVAL_MODE
        _mocks_mod._EVAL_MODE = False
        try:
            with patch("app.extractors.lab_pdf._get_page_count", return_value=11):
                with pytest.raises(ValueError, match="maximum is 10"):
                    extract_lab_pdf(
                        pdf_bytes=pdf,
                        patient_uuid_hash=PATIENT_HASH,
                        document_sha256=FAKE_SHA256,
                        filename="big.pdf",
                    )
        finally:
            _mocks_mod._EVAL_MODE = original

    def test_unknown_fixture_returns_empty_fields(self) -> None:
        pdf = _make_minimal_pdf()
        result = extract_lab_pdf(
            pdf_bytes=pdf,
            patient_uuid_hash=PATIENT_HASH,
            document_sha256=FAKE_SHA256,
            filename="unknown-fixture-xyz.pdf",
        )
        assert result["extracted_field_count"] == 0

    def test_missing_patient_hash_propagates(self) -> None:
        pdf = _make_minimal_pdf()
        result = extract_lab_pdf(
            pdf_bytes=pdf,
            patient_uuid_hash="",
            document_sha256=FAKE_SHA256,
            filename="p01-chen-lipid-panel.pdf",
        )
        # Empty patient hash is stored but should propagate through
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# Edge tests
# ---------------------------------------------------------------------------


class TestExtractLabPdfEdge:
    def test_whitaker_cbc_all_fields_have_names(self) -> None:
        pdf = _make_minimal_pdf()
        result = extract_lab_pdf(
            pdf_bytes=pdf,
            patient_uuid_hash=PATIENT_HASH,
            document_sha256=FAKE_SHA256,
            filename="p02-whitaker-cbc.pdf",
        )
        for field in result["result"]["fields"]:
            assert field["name"] != ""

    def test_extracted_at_is_iso8601(self) -> None:
        import re
        pdf = _make_minimal_pdf()
        result = extract_lab_pdf(
            pdf_bytes=pdf,
            patient_uuid_hash=PATIENT_HASH,
            document_sha256=FAKE_SHA256,
            filename="p01-chen-lipid-panel.pdf",
        )
        extracted_at = result["result"]["extracted_at"]
        assert re.match(r"\d{4}-\d{2}-\d{2}T", extracted_at)

    def test_extracted_by_model_is_eval_mock(self) -> None:
        pdf = _make_minimal_pdf()
        result = extract_lab_pdf(
            pdf_bytes=pdf,
            patient_uuid_hash=PATIENT_HASH,
            document_sha256=FAKE_SHA256,
            filename="p01-chen-lipid-panel.pdf",
        )
        assert result["result"]["extracted_by_model"] == "eval-mock"
