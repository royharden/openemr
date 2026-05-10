"""Unit tests for pdfplumber bbox text-matching logic (Wk2 Workstream A, §15.5).

Tests the _find_verbatim_bbox and _words_match helpers directly.
"""

from __future__ import annotations

import pytest

from app.extractors.lab_pdf import _find_verbatim_bbox, _words_match


# ---------------------------------------------------------------------------
# _words_match tests
# ---------------------------------------------------------------------------


class TestWordsMatch:
    def test_exact_match(self) -> None:
        assert _words_match(["Total", "Cholesterol:"], ["Total", "Cholesterol:"]) is True

    def test_case_insensitive(self) -> None:
        assert _words_match(["ldl"], ["LDL"]) is True

    def test_trailing_punctuation_stripped(self) -> None:
        assert _words_match(["Cholesterol,"], ["Cholesterol"]) is True

    def test_length_mismatch(self) -> None:
        assert _words_match(["a", "b"], ["a"]) is False

    def test_empty_lists(self) -> None:
        assert _words_match([], []) is True

    def test_different_words(self) -> None:
        assert _words_match(["Glucose"], ["Potassium"]) is False


# ---------------------------------------------------------------------------
# _find_verbatim_bbox tests
# ---------------------------------------------------------------------------

_BLOCKS = [
    {"text": "Total", "x0": 50.0, "y0": 100.0, "x1": 90.0, "y1": 115.0, "page_width": 600.0, "page_height": 800.0},
    {"text": "Cholesterol:", "x0": 95.0, "y0": 100.0, "x1": 175.0, "y1": 115.0, "page_width": 600.0, "page_height": 800.0},
    {"text": "198", "x0": 180.0, "y0": 100.0, "x1": 210.0, "y1": 115.0, "page_width": 600.0, "page_height": 800.0},
    {"text": "mg/dL", "x0": 215.0, "y0": 100.0, "x1": 260.0, "y1": 115.0, "page_width": 600.0, "page_height": 800.0},
    {"text": "LDL:", "x0": 50.0, "y0": 125.0, "x1": 85.0, "y1": 140.0, "page_width": 600.0, "page_height": 800.0},
    {"text": "122", "x0": 90.0, "y0": 125.0, "x1": 120.0, "y1": 140.0, "page_width": 600.0, "page_height": 800.0},
]


class TestFindVerbatimBbox:
    def test_single_word_match(self) -> None:
        bbox = _find_verbatim_bbox("LDL:", _BLOCKS)
        assert bbox is not None
        x0, y0, x1, y1 = bbox
        assert x0 < x1 and y0 < y1

    def test_multi_word_match(self) -> None:
        bbox = _find_verbatim_bbox("Total Cholesterol:", _BLOCKS)
        assert bbox is not None

    def test_full_phrase_match(self) -> None:
        bbox = _find_verbatim_bbox("Total Cholesterol: 198 mg/dL", _BLOCKS)
        assert bbox is not None

    def test_not_found_returns_none(self) -> None:
        bbox = _find_verbatim_bbox("Triglycerides:", _BLOCKS)
        assert bbox is None

    def test_empty_quote_returns_none(self) -> None:
        assert _find_verbatim_bbox("", _BLOCKS) is None

    def test_empty_blocks_returns_none(self) -> None:
        assert _find_verbatim_bbox("LDL:", []) is None

    def test_bbox_coordinates_normalized(self) -> None:
        bbox = _find_verbatim_bbox("LDL:", _BLOCKS)
        assert bbox is not None
        for coord in bbox:
            assert 0.0 <= coord <= 1.0

    def test_bbox_x0_less_than_x1(self) -> None:
        bbox = _find_verbatim_bbox("Total Cholesterol:", _BLOCKS)
        assert bbox is not None
        x0, _, x1, _ = bbox
        assert x0 < x1

    def test_bbox_y0_less_than_y1(self) -> None:
        bbox = _find_verbatim_bbox("Total Cholesterol:", _BLOCKS)
        assert bbox is not None
        _, y0, _, y1 = bbox
        assert y0 < y1

    def test_partial_word_not_matched(self) -> None:
        """'Total' should not match 'Totals'."""
        blocks_with_typo = [
            {"text": "Totals", "x0": 50.0, "y0": 100.0, "x1": 90.0, "y1": 115.0,
             "page_width": 600.0, "page_height": 800.0},
        ]
        bbox = _find_verbatim_bbox("Total", blocks_with_typo)
        # 'Totals' stripped of punctuation == 'Totals' != 'Total' — no match
        assert bbox is None

    def test_none_quote_returns_none(self) -> None:
        assert _find_verbatim_bbox(None, _BLOCKS) is None  # type: ignore[arg-type]
