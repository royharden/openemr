"""Shared fixtures for the verifier / schema test suite."""

from __future__ import annotations

import pytest

from app.schemas import Claim, LLMOutput, SourcePacket


PATIENT_UUID = "patient-uuid-fixture"
OTHER_PATIENT_UUID = "patient-uuid-OTHER"


def _packet(source_id: str, **overrides) -> SourcePacket:
    base = dict(
        source_id=source_id,
        patient_uuid=PATIENT_UUID,
        resource_type="Condition",
        source_table="lists",
        field="title",
        label="Active problem",
        value="Type 2 diabetes mellitus",
        status="active",
        freshness="recent",
    )
    base.update(overrides)
    return SourcePacket(**base)


@pytest.fixture
def patient_uuid() -> str:
    return PATIENT_UUID


@pytest.fixture
def other_patient_uuid() -> str:
    return OTHER_PATIENT_UUID


@pytest.fixture
def packet_factory():
    return _packet


@pytest.fixture
def claim_factory():
    def _make(
        text: str,
        source_ids: list[str],
        claim_type: str = "fact",
        caveat: str | None = None,
    ) -> Claim:
        return Claim(text=text, claim_type=claim_type, source_ids=source_ids, caveat=caveat)

    return _make


@pytest.fixture
def llm_output_factory():
    def _make(claims: list[Claim], answer_type: str = "pre_room_brief") -> LLMOutput:
        return LLMOutput(
            answer_type=answer_type,
            claims=claims,
            missing_data=[],
            refusals=[],
            suggested_followups=[],
        )

    return _make
