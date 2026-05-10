"""L1: GuidelineChunk Pydantic round-trip + validators (Wk2 W0.5 RAG contract-freeze)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.rag import GuidelineChunk


def _chunk(**overrides) -> GuidelineChunk:
    base = dict(
        chunk_id="acip:tdap:adult:2026:01",
        source_id="cdc-acip-2026-tdap-adult",
        source_organization="CDC-ACIP",
        source_name="Adult Tdap booster recommendation",
        page_or_section="Recommendation 4.2",
        text="Adults aged 19+ should receive a single Tdap dose...",
        recommendation_grade="A",
        source_year=2026,
    )
    base.update(overrides)
    return GuidelineChunk(**base)


def test_round_trip() -> None:
    c = _chunk()
    assert GuidelineChunk.model_validate(c.model_dump()) == c


def test_minimum_fields() -> None:
    c = GuidelineChunk(
        chunk_id="x",
        source_id="y",
        source_organization="FDA",
        source_name="metformin label",
        page_or_section="DOSAGE AND ADMINISTRATION",
        text="abc",
    )
    assert c.recommendation_grade is None
    assert c.source_year is None


def test_source_year_range() -> None:
    with pytest.raises(ValidationError):
        _chunk(source_year=1800)
    with pytest.raises(ValidationError):
        _chunk(source_year=2200)


def test_reranker_literal() -> None:
    for r in ("cohere", "fallback", "none"):
        _chunk(reranker=r)
    with pytest.raises(ValidationError):
        _chunk(reranker="bing")  # type: ignore[arg-type]


def test_organization_strip() -> None:
    c = _chunk(source_organization="  CDC-ACIP  ")
    assert c.source_organization == "CDC-ACIP"


def test_rerank_position_non_negative() -> None:
    _chunk(rerank_position=0)  # edge: top-of-list
    with pytest.raises(ValidationError):
        _chunk(rerank_position=-1)
