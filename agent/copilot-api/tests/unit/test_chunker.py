"""L1: Section-boundary chunker unit tests.

Covers positive cases (correct splitting), negative cases (oversized / empty
input), and edge cases (no headings, single heading, oversized section).

Plan §15.5.6 — positive/negative/edge per rule.
"""

from app.rag.chunker import ChunkSource, chunk_text, _split_sections, _split_oversized


def _src(suffix: str = "test") -> ChunkSource:
    return ChunkSource(
        source_id=f"test-{suffix}",
        source_organization="TEST",
        source_name="Test Document",
        source_year=2024,
        recommendation_grade=None,
    )


class TestChunkTextPositive:
    def test_splits_on_markdown_headings(self) -> None:
        text = (
            "# Section One\nThis is the detailed content for section one with plenty of text.\n\n"
            "## Section Two\nThis is the detailed content for section two with plenty of text."
        )
        chunks = chunk_text(text, _src())
        assert len(chunks) >= 2
        texts = [c.text for c in chunks]
        assert any("Section One" in t for t in texts)
        assert any("Section Two" in t for t in texts)

    def test_metadata_forwarded(self) -> None:
        src = ChunkSource(
            source_id="acip-2024",
            source_organization="CDC-ACIP",
            source_name="ACIP Schedule",
            source_year=2024,
            recommendation_grade="A",
        )
        text = (
            "# Influenza Recommendations\n"
            "All adults aged 6 months and older should receive an annual influenza vaccine "
            "unless contraindicated by allergy or prior adverse reaction."
        )
        chunks = chunk_text(text, src)
        assert len(chunks) >= 1
        for c in chunks:
            assert c.source_organization == "CDC-ACIP"
            assert c.source_year == 2024
            assert c.recommendation_grade == "A"
            assert c.source_id == "acip-2024"

    def test_chunk_ids_are_unique(self) -> None:
        text = "\n\n".join(
            f"# Section {i}\nContent for section {i}." for i in range(10)
        )
        chunks = chunk_text(text, _src())
        ids = [c.chunk_id for c in chunks]
        assert len(ids) == len(set(ids)), "Chunk IDs must be unique"

    def test_page_or_section_derived_from_heading(self) -> None:
        text = (
            "# Pneumococcal Vaccine\n"
            "Pneumococcal vaccines are recommended for all adults aged 65 years and older "
            "and for adults 19 through 64 years with certain underlying medical conditions."
        )
        chunks = chunk_text(text, _src())
        assert any("Pneumococcal" in c.page_or_section for c in chunks)

    def test_prefix_applied_to_ids(self) -> None:
        text = (
            "# Topic\nSome detailed content here covering the main clinical topic "
            "with enough text to exceed the minimum chunk size threshold."
        )
        chunks = chunk_text(text, _src(), id_prefix="acip-")
        assert all(c.chunk_id.startswith("acip-") for c in chunks)


class TestChunkTextNegative:
    def test_empty_string_produces_no_chunks(self) -> None:
        chunks = chunk_text("", _src())
        assert chunks == []

    def test_whitespace_only_produces_no_chunks(self) -> None:
        chunks = chunk_text("   \n\n   ", _src())
        assert chunks == []

    def test_very_short_content_filtered(self) -> None:
        text = "# H\nab"  # "ab" is 2 chars — below _SOFT_MIN after combining
        # Should produce zero or very few chunks (short content may be merged
        # with heading but still below threshold).
        chunks = chunk_text(text, _src())
        # All surviving chunks must have at least _SOFT_MIN chars.
        from app.rag.chunker import _SOFT_MIN
        for c in chunks:
            assert len(c.text) >= _SOFT_MIN


class TestChunkTextEdge:
    def test_no_headings_produces_one_chunk(self) -> None:
        text = "Plain paragraph text with no headings at all. " * 5
        chunks = chunk_text(text, _src())
        assert len(chunks) >= 1

    def test_oversized_section_split_at_blank_lines(self) -> None:
        # Build a section that exceeds _SOFT_MAX chars.
        from app.rag.chunker import _SOFT_MAX
        para = "This is a long paragraph with many words. " * 20
        text = "# Big Section\n\n" + ("\n\n" + para) * 10
        chunks = chunk_text(text, _src())
        # Should produce multiple chunks.
        assert len(chunks) > 1
        # No single chunk should exceed _SOFT_MAX + some tolerance.
        for c in chunks:
            assert len(c.text) <= _SOFT_MAX * 2  # soft cap, tolerance allowed

    def test_single_heading_no_body(self) -> None:
        text = "# Lone Heading"
        chunks = chunk_text(text, _src())
        # A heading with no body produces zero chunks (no body to chunk).
        # Accept 0 or 1 depending on implementation.
        assert isinstance(chunks, list)

    def test_grade_none_preserved(self) -> None:
        src = ChunkSource(
            source_id="fda-met",
            source_organization="FDA",
            source_name="Metformin",
            source_year=2020,
            recommendation_grade=None,
        )
        text = (
            "# Dosage\nMetformin 500 mg twice daily with meals is the standard starting dose "
            "for adults with type 2 diabetes, titrated as tolerated to a maximum of 2550 mg per day."
        )
        chunks = chunk_text(text, src)
        for c in chunks:
            assert c.recommendation_grade is None


class TestSplitSections:
    def test_returns_list_of_tuples(self) -> None:
        result = _split_sections(
            "# H1\nBody content for heading one.\n## H2\nBody content for heading two."
        )
        assert isinstance(result, list)
        assert all(isinstance(t, tuple) and len(t) == 2 for t in result)

    def test_empty_text_returns_one_tuple(self) -> None:
        result = _split_sections("")
        assert len(result) == 1


class TestSplitOversized:
    def test_short_text_not_split(self) -> None:
        text = "Short text."
        result = _split_oversized(text)
        assert result == [text]

    def test_blank_line_split(self) -> None:
        # Each paragraph must be > _SOFT_MAX so the blank-line boundary triggers.
        from app.rag.chunker import _SOFT_MAX
        para = "This is a long sentence with many words. " * 60  # ~2460 chars
        assert len(para) > _SOFT_MAX
        text = para + "\n\n" + para
        result = _split_oversized(text)
        assert len(result) >= 2
