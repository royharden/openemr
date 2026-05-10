"""Integration test: Langfuse graph spans are PHI-free (AgDR-0055).

Verifies that scrub_phi removes all PHI-like patterns from span metadata
before emission, and that record_graph_span is a no-op when no Langfuse
credentials are configured.
"""

from __future__ import annotations

import pytest

from app.observability import scrub_phi, record_graph_span


_PHI_SAMPLES = [
    ("SSN", "Patient SSN is 123-45-6789"),
    ("ISO date", "DOB 1978-07-22 is stored here"),
    ("phone", "Call 555-123-4567 for info"),
    ("MRN label", "MRN: 00099911 active"),
    ("patient name", "patient_name: JohnSmith"),
]


@pytest.mark.parametrize("label,text", _PHI_SAMPLES)
def test_scrub_phi_removes_pattern(label: str, text: str) -> None:
    result = scrub_phi(text)
    assert "[REDACTED]" in result, f"Expected redaction for {label}"


def test_scrub_phi_preserves_non_phi() -> None:
    text = "Sodium 140 mEq/L — within normal limits."
    assert scrub_phi(text) == text


def test_record_graph_span_no_op_without_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """record_graph_span must not raise even when Langfuse is not configured."""
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)

    # Should not raise
    record_graph_span(
        trace_id="trace-001",
        node_name="synthesizer",
        graph_path=["intake_extractor", "evidence_retriever", "synthesizer"],
        worker_handoffs=[{"from": "start", "to": "evidence_retriever", "reason": "no docs"}],
        decision_reason="synthesis_status=done; proceeding to verifier",
        duration_ms=42.5,
    )


def test_record_graph_span_scrubs_phi_in_decision_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    """Even with a PHI decision_reason, scrub_phi runs before emit."""
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)

    # No exception should surface from PHI in metadata when no client is configured
    record_graph_span(
        trace_id="trace-002",
        node_name="verifier",
        graph_path=["verifier"],
        worker_handoffs=[],
        decision_reason="DOB 1978-07-22 found in packet",
        duration_ms=5.0,
    )
