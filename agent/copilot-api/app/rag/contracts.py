"""RAG contracts — locked Pydantic shapes for Workstream B.

W0.5 contract-freeze (Plan §5 step 7, §6 Workstream B, AgDR-0044). Field
NAMES on these models are locked so Team B's retriever/reranker output and
Team C's graph nodes can't drift apart.

Design choice: ``recommendation_grade`` is a plain ``str | None`` instead of
an ``enum.Enum`` because the corpus mixes grading systems (ACIP A/B,
USPSTF A/B/C/D/I, Oxford CEBM 1a/1b/.., openFDA which has no grade).
The ``RecommendationGrade`` Literal below is the *known* universe; the
Pydantic field accepts any string so future grade systems don't break
backward compat. The verifier rule ``guideline_grade_present`` checks
membership in the Literal set per source organization.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


# Known grade vocabularies (the verifier checks per-org subsets).
RecommendationGrade = Literal[
    # USPSTF
    "A",
    "B",
    "C",
    "D",
    "I",
    # Oxford CEBM (subset commonly used by HMS-LOE)
    "1a",
    "1b",
    "2a",
    "2b",
    "3a",
    "3b",
    "4",
    "5",
]


SourceOrganization = Literal[
    "CDC-ACIP",
    "FDA",
    "HMS-LOE",
    "USPSTF",  # deferred to Wk3 but the literal is locked now
    "NICE",
    "ACP",
]


class GuidelineChunk(BaseModel):
    """One retrievable guideline-corpus chunk.

    Materialized from the SQLite ``chunks`` table by ``HybridRetriever`` /
    ``CohereReranker``. Becomes a ``SourcePacket`` (with
    ``source_type="guideline_chunk"``) when handed to the synthesizer.

    Field names locked at W0.5 — extend with new fields, don't rename.
    """

    chunk_id: str = Field(..., min_length=1, max_length=128)
    source_id: str = Field(..., min_length=1, max_length=128)
    source_organization: str = Field(..., max_length=64)
    source_name: str = Field(..., max_length=256)
    page_or_section: str = Field(..., max_length=255)
    text: str = Field(..., min_length=1)
    recommendation_grade: str | None = Field(None, max_length=8)
    source_year: int | None = Field(None, ge=1900, le=2100)
    bm25_score: float | None = None
    vector_score: float | None = None
    rerank_score: float | None = None
    rerank_position: int | None = Field(None, ge=0)
    reranker: Literal["cohere", "fallback", "none"] | None = None

    @field_validator("source_organization")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()
