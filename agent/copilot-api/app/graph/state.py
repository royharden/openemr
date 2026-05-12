"""CopilotState TypedDict — the shared state flowing through the LangGraph.

AgDR-0041: supervisor is deterministic on CopilotState fields — no LLM hop.
All routing decisions are pure Python rules on this dict.
"""

from __future__ import annotations

from typing import Any, TypedDict


class CopilotState(TypedDict, total=False):
    # --- input ---
    patient_uuid_hash: str
    question: str
    trace_id: str
    documents: list[dict[str, Any]]  # [{path, doc_type}]

    # --- extraction worker ---
    intake_status: str  # "pending" | "running" | "done" | "skipped" | "error"
    lab_status: str     # "pending" | "running" | "done" | "skipped" | "error"
    extracted_packets: list[dict[str, Any]]  # SourcePacket dicts from extraction

    # --- retrieval worker ---
    retrieval_status: str  # "pending" | "running" | "done" | "skipped" | "error"
    guideline_packets: list[dict[str, Any]]  # SourcePacket dicts from RAG

    # --- synthesizer ---
    synthesis_status: str  # "pending" | "running" | "done" | "error"
    llm_output: dict[str, Any] | None  # LLMOutput dict

    # --- critic (AgDR-0075, Phase 6.1) ---
    # Runs between synthesizer and verifier. On reject the critic rewrites
    # the in-flight llm_output to a safe-refusal shape so the verifier sees
    # a clean refusal rather than a flagged-but-still-claiming brief.
    critic_status: str  # "pending" | "passed" | "rejected" | "error" | "skipped"
    critic_verdict: dict[str, Any] | None  # CriticVerdict dict

    # --- verifier ---
    verifier_status: str  # "pending" | "done" | "error"
    verified_response: dict[str, Any] | None  # VerifiedResponse dict

    # --- router metadata ---
    current_node: str
    graph_path: list[str]  # ordered list of nodes visited
    worker_handoffs: list[dict[str, Any]]  # [{from, to, reason, timestamp}]
    decision_reason: str
    error_message: str | None

    # --- eval / observability ---
    low_confidence_count: int  # extracted fields with confidence < 1.0
    eval_mode: bool
    langfuse_trace_id: str | None
