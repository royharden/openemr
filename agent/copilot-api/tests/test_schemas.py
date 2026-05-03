"""Schema-boundary tests — Pydantic enforces the LLM contract."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas import BriefRequest, Claim, LLMOutput, ToolCall, ToolPlanRequest, ToolPlanResponse


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


def test_brief_request_accepts_free_text_followup():
    req = BriefRequest(
        trace_id="t-1",
        use_case="free_text_followup",
        patient_uuid_hash="hash",
        packets=[],
        question="What dose of lisinopril is she on?",
        prior_turn_source_ids=["rx:prescriptions:1"],
        router_family="medication",
    )
    assert req.question == "What dose of lisinopril is she on?"
    assert req.prior_turn_source_ids == ["rx:prescriptions:1"]


def test_brief_request_accepts_immunization_history_and_tool_metadata():
    req = BriefRequest(
        trace_id="t-1",
        use_case="immunization_history",
        patient_uuid_hash="hash",
        packets=[],
        selected_tools=["get_patient_identity", "get_immunization_history"],
        planner_status="planned",
        tool_results_summary=[{"tool": "get_immunization_history", "packet_count": 1, "status": "ok"}],
    )
    assert req.use_case == "immunization_history"
    assert req.selected_tools == ["get_patient_identity", "get_immunization_history"]


def test_tool_plan_response_rejects_unknown_tool():
    with pytest.raises(ValidationError):
        ToolPlanResponse(
            trace_id="t-1",
            planner_status="planned",
            tool_calls=[{"name": "run_sql", "arguments": {}}],
        )


def test_tool_call_rejects_patient_override_args():
    with pytest.raises(ValidationError):
        ToolCall(name="get_recent_labs", arguments={"patient_uuid": "other"})


def test_tool_plan_request_accepts_minimal_payload():
    req = ToolPlanRequest(
        trace_id="t-1",
        use_case="recent_abnormal_labs",
        patient_uuid_hash="hash",
        router_family="labs",
    )
    assert req.router_family == "labs"


def test_brief_request_rejects_question_with_control_chars():
    with pytest.raises(ValidationError):
        BriefRequest(
            trace_id="t-1",
            use_case="free_text_followup",
            patient_uuid_hash="hash",
            packets=[],
            question="hello\x00world",
        )


def test_brief_request_rejects_overlong_question():
    with pytest.raises(ValidationError):
        BriefRequest(
            trace_id="t-1",
            use_case="free_text_followup",
            patient_uuid_hash="hash",
            packets=[],
            question="x" * 501,
        )


def test_brief_request_rejects_too_many_prior_source_ids():
    with pytest.raises(ValidationError):
        BriefRequest(
            trace_id="t-1",
            use_case="free_text_followup",
            patient_uuid_hash="hash",
            packets=[],
            question="hi",
            prior_turn_source_ids=[f"sid-{i}" for i in range(21)],
        )
