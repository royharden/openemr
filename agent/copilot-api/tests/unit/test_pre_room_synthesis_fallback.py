"""Regression tests for blank-question pre-room synthesis."""

from __future__ import annotations

import hashlib
from typing import Any

from app.schemas import LLMOutput, SourcePacket
from app.verifier import verify


class _ToolBlock:
    type = "tool_use"

    def __init__(self, name: str, input_payload: dict[str, Any]) -> None:
        self.name = name
        self.input = input_payload


class _Response:
    def __init__(self, blocks: list[Any]) -> None:
        self.content = blocks


class _FakeMessages:
    def __init__(self, response: _Response) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> _Response:
        self.calls.append(kwargs)
        return self.response


class _FakeClient:
    def __init__(self, response: _Response) -> None:
        self.messages = _FakeMessages(response)


def _maria_packet(
    source_id: str,
    resource_type: str,
    source_table: str,
    field: str,
    label: str,
    value: str,
    patient_uuid: str,
    **extra: Any,
) -> dict[str, Any]:
    packet = {
        "source_id": source_id,
        "patient_uuid": patient_uuid,
        "resource_type": resource_type,
        "source_table": source_table,
        "field": field,
        "label": label,
        "value": value,
        "freshness": extra.pop("freshness", "recent"),
        "status": extra.pop("status", "active"),
    }
    packet.update(extra)
    return packet


def test_call_synthesizer_replaces_blank_pre_room_question(monkeypatch: Any) -> None:
    """The browser pre-room path sends no question; do not prompt with blank Question."""
    from app.graph.nodes import _call_synthesizer

    client = _FakeClient(
        _Response([
            _ToolBlock(
                "emit_briefing",
                {
                    "answer_type": "pre_room_brief",
                    "claims": [],
                    "missing_data": [],
                    "refusals": [],
                    "suggested_followups": [],
                },
            )
        ])
    )
    monkeypatch.setattr("anthropic.Anthropic", lambda *args, **kwargs: client)

    _call_synthesizer({
        "question": "",
        "extracted_packets": [],
        "guideline_packets": [],
    })

    prompt = client.messages.calls[0]["messages"][0]["content"]
    assert "Question: Prepare a concise pre-room brief" in prompt
    assert "Question: \n" not in prompt


def test_fallback_pre_room_summary_verifies_maria_packet_shape() -> None:
    """The deterministic fallback emits only verifier-clean source-backed facts."""
    from app.graph.nodes import _fallback_pre_room_llm_output

    patient_uuid = "11111111-1111-4111-8111-111111111111"
    request_hash = hashlib.sha256(patient_uuid.encode()).hexdigest()[:12]
    packets = [
        _maria_packet(
            "problem:lists:54",
            "Condition",
            "lists",
            "title",
            "Active problem",
            "Type 2 Diabetes",
            patient_uuid,
            freshness="stale",
            observed_at="2018-01-15 00:00:00",
        ),
        _maria_packet(
            "rx:prescriptions:36",
            "MedicationRequest",
            "prescriptions",
            "drug",
            "Active prescription",
            "Metformin",
            patient_uuid,
        ),
        _maria_packet(
            "rx:prescriptions:38",
            "MedicationRequest",
            "prescriptions",
            "drug",
            "Active prescription",
            "Atorvastatin",
            patient_uuid,
            freshness="stale",
            observed_at="2025-10-21 21:45:01",
        ),
        _maria_packet(
            "allergy:lists:57",
            "AllergyIntolerance",
            "lists",
            "title",
            "Allergy",
            "Penicillin",
            patient_uuid,
            freshness="stale",
            observed_at="2010-06-01 00:00:00",
        ),
        _maria_packet(
            "lab:procedure_result:23",
            "Observation",
            "procedure_result",
            "result",
            "Hemoglobin A1c",
            "8.4 (abnormal: high)",
            patient_uuid,
            unit="%",
            observed_at="2026-05-04 00:00:00",
            status="final",
        ),
        _maria_packet(
            "immunization:immunizations:8",
            "Immunization",
            "immunizations",
            "cvx_code",
            "Immunization",
            "pneumococcal polysaccharide vaccine, 23 valent",
            patient_uuid,
            freshness="stale",
            observed_at="2019-10-12 00:00:00",
            status="completed",
        ),
    ]

    output = _fallback_pre_room_llm_output({
        "question": "",
        "extracted_packets": packets,
        "guideline_packets": [],
    })
    verified = verify(
        LLMOutput(**output),
        [SourcePacket(**packet) for packet in packets],
        request_hash,
        trace_id="fallback-test",
    )

    assert len(output["claims"]) >= 5
    assert verified.unsupported_dropped == 0
    assert len(verified.claims) == len(output["claims"])
