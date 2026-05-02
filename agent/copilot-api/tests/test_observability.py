"""Observability tests - traces stay PHI-minimized and feedback is scoreable."""

from __future__ import annotations

from app import observability


class FakeTrace:
    def __init__(self) -> None:
        self.generations = []

    def generation(self, **kwargs) -> None:
        self.generations.append(kwargs)


class FakeLangfuse:
    def __init__(self) -> None:
        self.trace_calls = []
        self.score_calls = []
        self.trace_obj = FakeTrace()

    def trace(self, **kwargs) -> FakeTrace:
        self.trace_calls.append(kwargs)
        return self.trace_obj

    def score(self, **kwargs) -> None:
        self.score_calls.append(kwargs)


def test_record_brief_metadata_excludes_raw_phi(monkeypatch):
    fake = FakeLangfuse()
    monkeypatch.setattr(observability, "_client", fake)

    observability.record_brief(
        trace_id="trace-123",
        use_case="pre_room_brief",
        patient_uuid_hash="8865441d74c3",
        packet_count=3,
        usage={
            "input_tokens": 100,
            "output_tokens": 25,
            "cache_read_input_tokens": 10,
            "cache_creation_input_tokens": 2,
            "model": "claude-haiku-4-5-20251001",
            "prompt_template_version": "v1",
        },
        verifier_status="passed",
        unsupported_dropped=0,
        duration_ms=123.4,
    )

    trace_call = fake.trace_calls[0]
    metadata = trace_call["metadata"]
    assert metadata["patient_uuid_hash"] == "8865441d74c3"
    assert "patient_uuid" not in metadata
    assert "claim_text" not in metadata
    assert "source_values" not in metadata
    assert metadata["estimated_cost_usd"] == 0.000228
    assert fake.trace_obj.generations[0]["usage"]["input"] == 100
    assert fake.trace_obj.generations[0]["metadata"]["duration_ms"] == 123.4
    assert fake.trace_obj.generations[0]["metadata"]["estimated_cost_usd"] == 0.000228


def test_record_feedback_maps_verdict_and_truncates_comment(monkeypatch):
    fake = FakeLangfuse()
    monkeypatch.setattr(observability, "_client", fake)
    long_comment = "x" * 600

    recorded = observability.record_feedback("trace-123", "incorrect", long_comment)

    assert recorded is True
    score_call = fake.score_calls[0]
    assert score_call["trace_id"] == "trace-123"
    assert score_call["name"] == "clinician_feedback"
    assert score_call["value"] == -1.0
    assert len(score_call["comment"]) == 500


def test_estimate_cost_uses_configurable_rates(monkeypatch):
    monkeypatch.setenv("COPILOT_COST_INPUT_PER_1M", "2")
    monkeypatch.setenv("COPILOT_COST_OUTPUT_PER_1M", "10")
    monkeypatch.setenv("COPILOT_COST_CACHE_READ_PER_1M", "0.2")
    monkeypatch.setenv("COPILOT_COST_CACHE_WRITE_PER_1M", "2.5")

    cost = observability.estimate_cost_usd(
        {
            "input_tokens": 100,
            "output_tokens": 25,
            "cache_read_input_tokens": 10,
            "cache_creation_input_tokens": 2,
        }
    )

    assert cost == 0.000457
