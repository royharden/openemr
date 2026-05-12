"""Unit tests for app.graph.supervisor — 100% line coverage required (AgDR-0041).

Tests verify that routing functions are deterministic based on CopilotState fields
and that _record_handoff correctly mutates the state's worker_handoffs list.
"""

from __future__ import annotations

import pytest

from app.graph.supervisor import (
    NODE_CRITIC,
    NODE_END,
    NODE_EVIDENCE_RETRIEVER,
    NODE_INTAKE_EXTRACTOR,
    NODE_SYNTHESIZER,
    NODE_VERIFIER,
    _record_handoff,
    route_from_critic,
    route_from_intake,
    route_from_retriever,
    route_from_start,
    route_from_synthesizer,
    route_from_verifier,
)
from app.graph.state import CopilotState


def _make_state(**overrides: object) -> CopilotState:
    """Return a minimal CopilotState with sensible defaults."""
    state: CopilotState = {
        "patient_uuid_hash": "abc123",
        "question": "Any abnormal labs?",
        "trace_id": "trace-001",
        "documents": [],
        "intake_status": "pending",
        "lab_status": "pending",
        "extracted_packets": [],
        "retrieval_status": "pending",
        "guideline_packets": [],
        "synthesis_status": "pending",
        "llm_output": None,
        "verifier_status": "pending",
        "verified_response": None,
        "current_node": "start",
        "graph_path": [],
        "worker_handoffs": [],
        "decision_reason": "",
        "error_message": None,
        "low_confidence_count": 0,
        "eval_mode": True,
        "langfuse_trace_id": None,
    }
    state.update(overrides)  # type: ignore[typeddict-item]
    return state


# ---------------------------------------------------------------------------
# _record_handoff
# ---------------------------------------------------------------------------


class TestRecordHandoff:
    def test_appends_to_empty_list(self) -> None:
        state = _make_state()
        _record_handoff(state, "start", NODE_INTAKE_EXTRACTOR, "reason")
        assert len(state["worker_handoffs"]) == 1
        h = state["worker_handoffs"][0]
        assert h["from"] == "start"
        assert h["to"] == NODE_INTAKE_EXTRACTOR
        assert h["reason"] == "reason"
        assert isinstance(h["timestamp_ms"], int)

    def test_appends_multiple_handoffs(self) -> None:
        state = _make_state()
        _record_handoff(state, "a", "b", "first")
        _record_handoff(state, "b", "c", "second")
        assert len(state["worker_handoffs"]) == 2
        assert state["worker_handoffs"][1]["from"] == "b"

    def test_does_not_mutate_original_list_reference(self) -> None:
        original_list: list = []
        state = _make_state(worker_handoffs=original_list)
        _record_handoff(state, "a", "b", "r")
        # The state should now have a new list (copied via list()), but the function
        # replaces state["worker_handoffs"] so original_list should still be empty.
        assert original_list == []
        assert len(state["worker_handoffs"]) == 1

    def test_handoff_with_missing_worker_handoffs_key(self) -> None:
        state: CopilotState = {
            "patient_uuid_hash": "x",
            "question": "",
            "trace_id": "t",
        }  # type: ignore[typeddict-item]
        _record_handoff(state, "a", "b", "r")
        assert len(state["worker_handoffs"]) == 1


# ---------------------------------------------------------------------------
# route_from_start
# ---------------------------------------------------------------------------


class TestRouteFromStart:
    def test_routes_to_intake_when_documents_and_pending(self) -> None:
        state = _make_state(documents=[{"path": "doc.pdf", "doc_type": "lab_pdf"}], intake_status="pending")
        result = route_from_start(state)
        assert result == NODE_INTAKE_EXTRACTOR

    def test_routes_to_retriever_when_no_documents(self) -> None:
        state = _make_state(documents=[], intake_status="pending")
        result = route_from_start(state)
        assert result == NODE_EVIDENCE_RETRIEVER

    def test_routes_to_retriever_when_intake_already_skipped(self) -> None:
        state = _make_state(
            documents=[{"path": "doc.pdf", "doc_type": "lab_pdf"}],
            intake_status="skipped",
        )
        result = route_from_start(state)
        assert result == NODE_EVIDENCE_RETRIEVER

    def test_routes_to_retriever_when_intake_done(self) -> None:
        state = _make_state(
            documents=[{"path": "doc.pdf", "doc_type": "lab_pdf"}],
            intake_status="done",
        )
        result = route_from_start(state)
        assert result == NODE_EVIDENCE_RETRIEVER

    def test_decision_reason_set_on_intake_path(self) -> None:
        state = _make_state(documents=[{"path": "d.pdf", "doc_type": "lab_pdf"}], intake_status="pending")
        route_from_start(state)
        assert "intake_status=pending" in state["decision_reason"]
        assert "1" in state["decision_reason"]  # len(docs)

    def test_decision_reason_set_on_skip_path(self) -> None:
        state = _make_state(documents=[])
        route_from_start(state)
        assert "skipping intake_extractor" in state["decision_reason"]

    def test_handoff_recorded_on_intake_path(self) -> None:
        state = _make_state(documents=[{"path": "d.pdf", "doc_type": "lab_pdf"}], intake_status="pending")
        route_from_start(state)
        assert state["worker_handoffs"][-1]["to"] == NODE_INTAKE_EXTRACTOR

    def test_handoff_recorded_on_skip_path(self) -> None:
        state = _make_state(documents=[])
        route_from_start(state)
        assert state["worker_handoffs"][-1]["to"] == NODE_EVIDENCE_RETRIEVER

    def test_missing_documents_key_treated_as_no_docs(self) -> None:
        state: CopilotState = {"patient_uuid_hash": "x", "trace_id": "t"}  # type: ignore[typeddict-item]
        result = route_from_start(state)
        assert result == NODE_EVIDENCE_RETRIEVER


# ---------------------------------------------------------------------------
# route_from_intake
# ---------------------------------------------------------------------------


class TestRouteFromIntake:
    def test_always_returns_evidence_retriever(self) -> None:
        for status in ("done", "error", "skipped", "running", "pending"):
            state = _make_state(intake_status=status)
            assert route_from_intake(state) == NODE_EVIDENCE_RETRIEVER

    def test_decision_reason_includes_status(self) -> None:
        state = _make_state(intake_status="done")
        route_from_intake(state)
        assert "done" in state["decision_reason"]

    def test_handoff_recorded(self) -> None:
        state = _make_state(intake_status="done")
        route_from_intake(state)
        h = state["worker_handoffs"][-1]
        assert h["from"] == NODE_INTAKE_EXTRACTOR
        assert h["to"] == NODE_EVIDENCE_RETRIEVER


# ---------------------------------------------------------------------------
# route_from_retriever
# ---------------------------------------------------------------------------


class TestRouteFromRetriever:
    def test_always_returns_synthesizer(self) -> None:
        for status in ("done", "error", "skipped", "pending"):
            state = _make_state(retrieval_status=status)
            assert route_from_retriever(state) == NODE_SYNTHESIZER

    def test_decision_reason_includes_status(self) -> None:
        state = _make_state(retrieval_status="done")
        route_from_retriever(state)
        assert "done" in state["decision_reason"]

    def test_handoff_recorded(self) -> None:
        state = _make_state(retrieval_status="done")
        route_from_retriever(state)
        h = state["worker_handoffs"][-1]
        assert h["from"] == NODE_EVIDENCE_RETRIEVER
        assert h["to"] == NODE_SYNTHESIZER


# ---------------------------------------------------------------------------
# route_from_synthesizer
# ---------------------------------------------------------------------------


class TestRouteFromSynthesizer:
    def test_always_returns_critic(self) -> None:
        """AgDR-0075 (Phase 6.1): synthesizer always hands off to the critic
        before the verifier. A regression that reverted this edge to
        NODE_VERIFIER would silently disable the LLM-layer safety gate."""
        for status in ("done", "error", "pending"):
            state = _make_state(synthesis_status=status)
            assert route_from_synthesizer(state) == NODE_CRITIC

    def test_decision_reason_includes_status(self) -> None:
        state = _make_state(synthesis_status="done")
        route_from_synthesizer(state)
        assert "done" in state["decision_reason"]

    def test_handoff_recorded(self) -> None:
        state = _make_state(synthesis_status="done")
        route_from_synthesizer(state)
        h = state["worker_handoffs"][-1]
        assert h["from"] == NODE_SYNTHESIZER
        assert h["to"] == NODE_CRITIC


# ---------------------------------------------------------------------------
# route_from_critic (AgDR-0075, Phase 6.1)
# ---------------------------------------------------------------------------


class TestRouteFromCritic:
    def test_always_returns_verifier(self) -> None:
        """Critic always proceeds to the verifier. On reject, the in-flight
        llm_output has already been rewritten by critic_node — the verifier
        sees a refusal-shaped output and produces a clean refusal."""
        for status in ("passed", "rejected", "skipped", "error"):
            state = _make_state(critic_status=status)
            assert route_from_critic(state) == NODE_VERIFIER

    def test_decision_reason_includes_status(self) -> None:
        state = _make_state(critic_status="passed")
        route_from_critic(state)
        assert "passed" in state["decision_reason"]

    def test_handoff_recorded(self) -> None:
        state = _make_state(critic_status="passed")
        route_from_critic(state)
        h = state["worker_handoffs"][-1]
        assert h["from"] == NODE_CRITIC
        assert h["to"] == NODE_VERIFIER


# ---------------------------------------------------------------------------
# route_from_verifier
# ---------------------------------------------------------------------------


class TestRouteFromVerifier:
    def test_always_returns_end(self) -> None:
        for status in ("done", "passed", "failed", "error"):
            state = _make_state(verifier_status=status)
            assert route_from_verifier(state) == NODE_END

    def test_decision_reason_includes_graph_complete(self) -> None:
        state = _make_state(verifier_status="done")
        route_from_verifier(state)
        assert "graph complete" in state["decision_reason"]

    def test_handoff_recorded(self) -> None:
        state = _make_state(verifier_status="done")
        route_from_verifier(state)
        h = state["worker_handoffs"][-1]
        assert h["from"] == NODE_VERIFIER
        assert h["to"] == NODE_END


# ---------------------------------------------------------------------------
# Node name constant sanity checks
# ---------------------------------------------------------------------------


class TestNodeConstants:
    def test_all_constants_are_strings(self) -> None:
        for const in (
            NODE_INTAKE_EXTRACTOR,
            NODE_EVIDENCE_RETRIEVER,
            NODE_SYNTHESIZER,
            NODE_CRITIC,
            NODE_VERIFIER,
            NODE_END,
        ):
            assert isinstance(const, str)
            assert len(const) > 0

    def test_constants_are_unique(self) -> None:
        consts = [
            NODE_INTAKE_EXTRACTOR,
            NODE_EVIDENCE_RETRIEVER,
            NODE_SYNTHESIZER,
            NODE_CRITIC,
            NODE_VERIFIER,
            NODE_END,
        ]
        assert len(consts) == len(set(consts))
