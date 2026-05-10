"""Deterministic supervisor router for the CopilotState graph.

AgDR-0041: NO LLM call here. Routing is pure rules over CopilotState fields.
Every routing decision is logged to graph_path and worker_handoffs so
Langfuse traces are inspectable.

The routing logic is:
  START -> intake_extractor  (if documents provided and intake_status == "pending")
  intake_extractor -> evidence_retriever  (after extraction completes or is skipped)
  evidence_retriever -> synthesizer
  synthesizer -> verifier
  verifier -> END

The supervisor is called by LangGraph as a conditional-edge function.
"""

from __future__ import annotations

import time
from typing import Any

from .state import CopilotState

# Node name constants to avoid string duplication.
NODE_INTAKE_EXTRACTOR = "intake_extractor"
NODE_EVIDENCE_RETRIEVER = "evidence_retriever"
NODE_SYNTHESIZER = "synthesizer"
NODE_VERIFIER = "verifier"
NODE_END = "__end__"


def _record_handoff(
    state: CopilotState,
    from_node: str,
    to_node: str,
    reason: str,
) -> None:
    """Append a handoff record to state[worker_handoffs]. Mutates the list."""
    handoffs: list[dict[str, Any]] = list(state.get("worker_handoffs", []))
    handoffs.append({
        "from": from_node,
        "to": to_node,
        "reason": reason,
        "timestamp_ms": int(time.monotonic() * 1000),
    })
    state["worker_handoffs"] = handoffs


def route_from_start(state: CopilotState) -> str:
    """Determine the first node after START.

    Rule: if documents are provided and not yet processed, run intake_extractor.
    Otherwise skip directly to evidence_retriever.
    """
    docs = state.get("documents", [])
    intake_status = state.get("intake_status", "pending")

    if docs and intake_status == "pending":
        reason = f"documents={len(docs)} provided; intake_status=pending"
        _record_handoff(state, "start", NODE_INTAKE_EXTRACTOR, reason)
        state["decision_reason"] = reason
        return NODE_INTAKE_EXTRACTOR

    reason = "no documents provided; skipping intake_extractor"
    _record_handoff(state, "start", NODE_EVIDENCE_RETRIEVER, reason)
    state["decision_reason"] = reason
    return NODE_EVIDENCE_RETRIEVER


def route_from_intake(state: CopilotState) -> str:
    """Route after intake_extractor completes.

    Always proceeds to evidence_retriever (extraction done or errored).
    """
    intake_status = state.get("intake_status", "unknown")
    reason = f"intake_status={intake_status}; proceeding to evidence_retriever"
    _record_handoff(state, NODE_INTAKE_EXTRACTOR, NODE_EVIDENCE_RETRIEVER, reason)
    state["decision_reason"] = reason
    return NODE_EVIDENCE_RETRIEVER


def route_from_retriever(state: CopilotState) -> str:
    """Route after evidence_retriever completes.

    Always proceeds to synthesizer.
    """
    retrieval_status = state.get("retrieval_status", "unknown")
    reason = f"retrieval_status={retrieval_status}; proceeding to synthesizer"
    _record_handoff(state, NODE_EVIDENCE_RETRIEVER, NODE_SYNTHESIZER, reason)
    state["decision_reason"] = reason
    return NODE_SYNTHESIZER


def route_from_synthesizer(state: CopilotState) -> str:
    """Route after synthesizer completes.

    Always proceeds to verifier.
    """
    synthesis_status = state.get("synthesis_status", "unknown")
    reason = f"synthesis_status={synthesis_status}; proceeding to verifier"
    _record_handoff(state, NODE_SYNTHESIZER, NODE_VERIFIER, reason)
    state["decision_reason"] = reason
    return NODE_VERIFIER


def route_from_verifier(state: CopilotState) -> str:
    """Route after verifier completes. Always ends the graph."""
    verifier_status = state.get("verifier_status", "unknown")
    reason = f"verifier_status={verifier_status}; graph complete"
    _record_handoff(state, NODE_VERIFIER, NODE_END, reason)
    state["decision_reason"] = reason
    return NODE_END
