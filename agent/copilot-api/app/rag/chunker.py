"""Section-boundary chunker for guideline corpus ingestion.

Design
------
Chunks are **not** split by token count.  Instead we split on structural
section boundaries — headings, numbered-list items, blank-line delimiters —
so each chunk has a coherent semantic unit.  This preserves the heading
hierarchy required for ``page_or_section`` metadata.

Anti-pattern §13.7: token-count chunking is explicitly forbidden.

Metadata preservation
---------------------
Each ``GuidelineChunk`` produced here carries ``recommendation_grade`` and
``source_year`` forwarded from the ingestor (caller is responsible for
providing them).  The chunker does NOT derive grades from text — that would
introduce hallucination risk.  The ingestor knows the grade from the
structured source.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field

from .contracts import GuidelineChunk


# Patterns that identify a section boundary (new chunk starts after this line).
_HEADING_RE = re.compile(
    r"^"
    r"(?:"
    r"#{1,6}\s+"        # Markdown headings
    r"|(?:[A-Z][A-Z\s]{2,})\s*$"  # ALL-CAPS headers (CDC PDFs)
    r"|\d+\.\s+[A-Z]"   # Numbered sections  "1. Introduction"
    r"|\*{2,}[^*]+\*{2,}"  # Bold headings
    r")"
)

# Maximum characters per chunk (soft cap — we don't split mid-sentence).
_SOFT_MAX = 2000
# Minimum characters to be included (avoid tiny orphan chunks).
_SOFT_MIN = 40


@dataclass
class ChunkSource:
    source_id: str
    source_organization: str
    source_name: str
    source_year: int | None
    recommendation_grade: str | None = None
    extra_meta: dict[str, str] = field(default_factory=dict)


def chunk_text(
    text: str,
    source: ChunkSource,
    id_prefix: str = "",
) -> list[GuidelineChunk]:
    """Split *text* on section boundaries and return ``GuidelineChunk`` objects.

    Parameters
    ----------
    text:
        Full document text (UTF-8 string).
    source:
        Metadata that applies to every chunk derived from this document.
    id_prefix:
        Optional prefix for deterministic chunk IDs (e.g. ``"acip-2024-"``)
        so IDs are human-readable.  A UUID suffix makes them unique.
    """
    raw_sections = _split_sections(text)
    chunks: list[GuidelineChunk] = []
    for heading, body in raw_sections:
        # Merge short orphan bodies with their heading.
        content = (heading + "\n" + body).strip() if heading else body.strip()
        if len(content) < _SOFT_MIN:
            continue
        # Split oversized sections further at blank lines.
        sub_parts = _split_oversized(content) if len(content) > _SOFT_MAX else [content]
        for i, part in enumerate(sub_parts):
            if len(part.strip()) < _SOFT_MIN:
                continue
            section_label = _derive_section(heading, i, len(sub_parts))
            chunk_id = _make_id(id_prefix, source.source_id, section_label, part)
            chunks.append(
                GuidelineChunk(
                    chunk_id=chunk_id,
                    source_id=source.source_id,
                    source_organization=source.source_organization,
                    source_name=source.source_name,
                    page_or_section=section_label,
                    text=part.strip(),
                    recommendation_grade=source.recommendation_grade,
                    source_year=source.source_year,
                )
            )
    return chunks


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _split_sections(text: str) -> list[tuple[str, str]]:
    """Return list of (heading, body) pairs split on heading boundaries."""
    lines = text.splitlines()
    sections: list[tuple[str, str]] = []
    current_heading = ""
    current_body: list[str] = []

    for line in lines:
        if _HEADING_RE.match(line.strip()):
            # Flush current section.
            body = "\n".join(current_body).strip()
            if body or current_heading:
                sections.append((current_heading, body))
            current_heading = line.strip()
            current_body = []
        else:
            current_body.append(line)

    # Flush last section.
    body = "\n".join(current_body).strip()
    if body or current_heading:
        sections.append((current_heading, body))

    # If no boundaries were found, treat the whole text as one section.
    if not sections:
        sections = [("", text.strip())]

    return sections


def _split_oversized(text: str) -> list[str]:
    """Split an oversized section at blank lines (paragraph boundaries)."""
    parts = re.split(r"\n\s*\n", text)
    merged: list[str] = []
    buf = ""
    for part in parts:
        if len(buf) + len(part) > _SOFT_MAX and buf:
            merged.append(buf.strip())
            buf = part
        else:
            buf = (buf + "\n\n" + part) if buf else part
    if buf.strip():
        merged.append(buf.strip())
    return merged if merged else [text]


def _derive_section(heading: str, sub_index: int, sub_total: int) -> str:
    label = heading.strip() or "§main"
    if sub_total > 1:
        label = f"{label} (part {sub_index + 1}/{sub_total})"
    return label[:255]


def _make_id(prefix: str, source_id: str, section: str, text: str) -> str:
    import hashlib
    digest = hashlib.sha256(
        (source_id + "|" + section + "|" + text[:200]).encode()
    ).hexdigest()[:16]
    return f"{prefix}{digest}"
