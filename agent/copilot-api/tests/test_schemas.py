"""Schema-boundary tests — Pydantic enforces the LLM contract."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas import BriefRequest, Claim, LLMOutput


def test_claim_requires_known_claim_type():
    with pytest.raises(ValidationError):
        Claim(text="x", claim_type="opinion", source_ids=["s:1"])


def test_llm_output_rejects_unknown_answer_type():
    with pytest.raises(ValidationError):
        LLMOutput(answer_type="freeform_essay", claims=[])


def test_brief_request_rejects_unknown_use_case():
    with pytest.raises(ValidationError):
        BriefRequest(
            trace_id="t-1",
            use_case="diagnose-the-patient",
            patient_uuid_hash="hash",
            packets=[],
        )


def test_llm_output_accepts_minimal_payload():
    out = LLMOutput(answer_type="refusal", claims=[])
    assert out.claims == []
    assert out.missing_data == []
    assert out.suggested_followups == []
