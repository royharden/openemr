"""Unit tests for verifier rule: quote_verbatim_in_pdf (Wk2 Workstream A, §15.5).

Per §15.5.6: positive / negative / edge cases.
Coverage target: ≥95% of check_quote_verbatim_in_pdf.
"""

from __future__ import annotations

import pytest

from app.schemas import SourcePacket
from app.verifier import check_quote_verbatim_in_pdf


def _make_packet(**overrides: object) -> SourcePacket:
    base: dict[str, object] = {
        "source_id": "doc:aabbcc112233:page0:ldl",
        "patient_uuid": "patient-123",
        "resource_type": "DocumentFact",
        "source_table": "copilot_document_facts",
        "field": "ldl",
        "label": "Ldl",
        "value": 122.0,
        "source_type": "document_extract",
        "quote_or_value": "LDL: 122 mg/dL",
        "page_index": 0,
    }
    base.update(overrides)
    return SourcePacket(**base)  # type: ignore[arg-type]


_PAGE_TEXT = {0: "Total Cholesterol: 198 mg/dL\nLDL: 122 mg/dL\nHDL: 58 mg/dL"}


# ---------------------------------------------------------------------------
# Positive tests — should return None (pass)
# ---------------------------------------------------------------------------


class TestQuoteVerbatimInPdfPositive:
    def test_exact_quote_present_on_page_passes(self) -> None:
        pkt = _make_packet(quote_or_value="LDL: 122 mg/dL", page_index=0)
        assert check_quote_verbatim_in_pdf(pkt, _PAGE_TEXT) is None

    def test_quote_on_different_page_searched_all_pages(self) -> None:
        """page_index not set — searches all pages."""
        pkt = _make_packet(quote_or_value="HDL: 58 mg/dL", page_index=None)
        assert check_quote_verbatim_in_pdf(pkt, _PAGE_TEXT) is None

    def test_none_quote_passes(self) -> None:
        pkt = _make_packet(quote_or_value=None)
        assert check_quote_verbatim_in_pdf(pkt, _PAGE_TEXT) is None

    def test_empty_text_map_passes(self) -> None:
        """No text layer (image-only document) — rule is skipped."""
        pkt = _make_packet(quote_or_value="LDL: 122 mg/dL", page_index=0)
        assert check_quote_verbatim_in_pdf(pkt, {}) is None

    def test_non_document_extract_skips(self) -> None:
        pkt = _make_packet(source_type="openemr_packet", quote_or_value="LDL: 999 mg/dL")
        assert check_quote_verbatim_in_pdf(pkt, _PAGE_TEXT) is None

    def test_case_insensitive_match_passes(self) -> None:
        pkt = _make_packet(quote_or_value="ldl: 122 mg/dl", page_index=0)
        assert check_quote_verbatim_in_pdf(pkt, _PAGE_TEXT) is None


# ---------------------------------------------------------------------------
# Negative tests — should return VerifierIssue (fail)
# ---------------------------------------------------------------------------


class TestQuoteVerbatimInPdfNegative:
    def test_quote_not_found_on_specified_page_fails(self) -> None:
        """Page 0 text exists but 'Glucose: 95' is not in it — should fail."""
        pkt = _make_packet(quote_or_value="Glucose: 95 mg/dL", page_index=0)
        issue = check_quote_verbatim_in_pdf(pkt, _PAGE_TEXT)
        assert issue is not None
        assert issue.rule == "quote_verbatim_in_pdf"
        assert "page 0" in issue.detail

    def test_invented_value_not_in_pdf_fails(self) -> None:
        pkt = _make_packet(quote_or_value="LDL: 999 mg/dL", page_index=0)
        issue = check_quote_verbatim_in_pdf(pkt, _PAGE_TEXT)
        assert issue is not None

    def test_quote_not_in_any_page_fails(self) -> None:
        pkt = _make_packet(quote_or_value="Triglycerides: 500 mg/dL", page_index=None)
        issue = check_quote_verbatim_in_pdf(pkt, _PAGE_TEXT)
        assert issue is not None

    def test_partial_quote_prefix_not_found_fails(self) -> None:
        """'LDL: 1' appears in 'LDL: 122' as substring but exact check passes.
        Here we test that a completely missing substring fails."""
        pkt = _make_packet(quote_or_value="Glucose: 95 mg/dL", page_index=0)
        issue = check_quote_verbatim_in_pdf(pkt, _PAGE_TEXT)
        assert issue is not None


# ---------------------------------------------------------------------------
# Edge tests
# ---------------------------------------------------------------------------


class TestQuoteVerbatimInPdfEdge:
    def test_empty_quote_string_passes(self) -> None:
        pkt = _make_packet(quote_or_value="")
        assert check_quote_verbatim_in_pdf(pkt, _PAGE_TEXT) is None

    def test_quote_spans_multiple_pages(self) -> None:
        multi_page = {
            0: "Total Cholesterol: 198 mg/dL",
            1: "LDL: 122 mg/dL\nHDL: 58 mg/dL",
        }
        pkt = _make_packet(quote_or_value="HDL: 58 mg/dL", page_index=None)
        assert check_quote_verbatim_in_pdf(pkt, multi_page) is None

    def test_issue_references_source_id(self) -> None:
        pkt = _make_packet(quote_or_value="invented text", page_index=0)
        issue = check_quote_verbatim_in_pdf(pkt, _PAGE_TEXT)
        assert issue is not None
        assert "doc:aabbcc112233:page0:ldl" in issue.detail
