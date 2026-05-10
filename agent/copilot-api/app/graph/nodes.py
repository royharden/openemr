"""Graph node implementations for the LangGraph CopilotState graph.

Node contract: each function accepts CopilotState and returns a partial dict
update. LangGraph merges these updates into the running state.

Synthesizer (Haiku 4.5) is the ONLY LLM call in the graph (AgDR-0041).
Workers call their respective modules (Team A extractors / Team B retriever).
In COPILOT_EVAL_MODE=1 all vendor calls are replaced by deterministic mocks.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from typing import Any

from .state import CopilotState

logger = logging.getLogger(__name__)

_EVAL_MODE = os.getenv("COPILOT_EVAL_MODE") == "1"

# Deterministic golden synthesis responses keyed by case_id for eval mode.
# Extend by adding entries; the key is extracted from the question field.
_EVAL_SYNTHESIS_RESPONSES: dict[str, dict[str, Any]] = {
    "__default__": {
        "answer_type": "pre_room_brief",
        "claims": [
            {
                "text": "Patient has documented lab results on file.",
                "claim_type": "fact",
                "source_ids": [],
                "caveat": None,
            }
        ],
        "missing_data": [],
        "refusals": [],
        "suggested_followups": [],
    }
}


def _eval_synthesis_response(state: CopilotState) -> dict[str, Any]:
    """Deterministic synthesis response for COPILOT_EVAL_MODE=1."""
    question = state.get("question", "")
    key = hashlib.sha256(question.encode()).hexdigest()[:16]
    return _EVAL_SYNTHESIS_RESPONSES.get(key, _EVAL_SYNTHESIS_RESPONSES["__default__"])


def intake_extractor_node(state: CopilotState) -> dict[str, Any]:
    """Call the intake/lab extractors for uploaded documents.

    In eval mode returns a deterministic empty extraction result.
    In live mode delegates to app.extractors (Team A).
    """
    started = time.monotonic()

    # Update state to mark running
    documents = state.get("documents", [])

    if _EVAL_MODE:
        # TODO(team-c): swap to team-a mock when their PR lands
        extracted_packets: list[dict[str, Any]] = []
        intake_status = "done"
        lab_status = "done"
        low_confidence_count = 0
    else:
        try:
            # Attempt to import Team A's extractors; fallback gracefully.
            from app.extractors import run_extraction  # type: ignore[import-not-found]
            result = run_extraction(documents, state.get("patient_uuid_hash", ""))
            extracted_packets = result.get("packets", [])
            intake_status = "done"
            lab_status = "done"
            low_confidence_count = result.get("low_confidence_count", 0)
        except ImportError:
            logger.warning("app.extractors not yet available (Team A pending); returning empty extraction")
            extracted_packets = []
            intake_status = "skipped"
            lab_status = "skipped"
            low_confidence_count = 0
        except Exception as e:
            logger.error("intake_extractor_node error: %s", e)
            extracted_packets = []
            intake_status = "error"
            lab_status = "error"
            low_confidence_count = 0

    elapsed_ms = (time.monotonic() - started) * 1000
    logger.info("intake_extractor_node: done in %.1fms, packets=%d", elapsed_ms, len(extracted_packets))

    path = list(state.get("graph_path", []))
    path.append("intake_extractor")

    return {
        "intake_status": intake_status,
        "lab_status": lab_status,
        "extracted_packets": extracted_packets,
        "low_confidence_count": low_confidence_count,
        "current_node": "intake_extractor",
        "graph_path": path,
    }


def evidence_retriever_node(state: CopilotState) -> dict[str, Any]:
    """Retrieve guideline evidence via hybrid RAG (Team B).

    In eval mode returns deterministic empty guideline packets.
    In live mode delegates to app.rag (Team B).
    """
    started = time.monotonic()
    question = state.get("question", "")
    patient_uuid_hash = state.get("patient_uuid_hash", "")

    if _EVAL_MODE:
        # TODO(team-c): swap to team-b mock when their PR lands
        guideline_packets: list[dict[str, Any]] = []
        retrieval_status = "done"
    else:
        try:
            from app.rag import retrieve_guidelines  # type: ignore[import-not-found]
            # Strip patient identifiers before passing to retriever (no PHI in queries)
            sanitized_question = _strip_phi_from_query(question, patient_uuid_hash)
            chunks = retrieve_guidelines(sanitized_question)
            guideline_packets = [c.model_dump() for c in chunks]
            retrieval_status = "done"
        except ImportError:
            logger.warning("app.rag not yet available (Team B pending); returning empty retrieval")
            guideline_packets = []
            retrieval_status = "skipped"
        except Exception as e:
            logger.error("evidence_retriever_node error: %s", e)
            guideline_packets = []
            retrieval_status = "error"

    elapsed_ms = (time.monotonic() - started) * 1000
    logger.info("evidence_retriever_node: done in %.1fms, chunks=%d", elapsed_ms, len(guideline_packets))

    path = list(state.get("graph_path", []))
    path.append("evidence_retriever")

    return {
        "retrieval_status": retrieval_status,
        "guideline_packets": guideline_packets,
        "current_node": "evidence_retriever",
        "graph_path": path,
    }


def _strip_phi_from_query(question: str, patient_uuid_hash: str) -> str:
    """Remove patient hash from retrieval query (no PHI in corpus queries)."""
    if patient_uuid_hash and patient_uuid_hash in question:
        return question.replace(patient_uuid_hash, "[PATIENT]")
    return question


def synthesizer_node(state: CopilotState) -> dict[str, Any]:
    """Call Haiku 4.5 to synthesize extracted + guideline packets into a response.

    This is the ONLY LLM call in the graph (AgDR-0041).
    In eval mode returns a deterministic golden response per case hash.
    """
    started = time.monotonic()

    if _EVAL_MODE:
        llm_output = _eval_synthesis_response(state)
        synthesis_status = "done"
    else:
        try:
            llm_output = _call_haiku_synthesizer(state)
            synthesis_status = "done"
        except Exception as e:
            logger.error("synthesizer_node LLM call failed: %s", e)
            llm_output = {
                "answer_type": "pre_room_brief",
                "claims": [],
                "missing_data": ["Synthesis failed; please review chart directly."],
                "refusals": [],
                "suggested_followups": [],
            }
            synthesis_status = "error"

    elapsed_ms = (time.monotonic() - started) * 1000
    logger.info("synthesizer_node: done in %.1fms, claims=%d", elapsed_ms, len(llm_output.get("claims", [])))

    path = list(state.get("graph_path", []))
    path.append("synthesizer")

    return {
        "synthesis_status": synthesis_status,
        "llm_output": llm_output,
        "current_node": "synthesizer",
        "graph_path": path,
    }


def _call_haiku_synthesizer(state: CopilotState) -> dict[str, Any]:
    """Make the actual Haiku 4.5 API call. Only invoked in live mode."""
    import anthropic  # type: ignore[import-not-found]
    import os

    extracted_packets = state.get("extracted_packets", [])
    guideline_packets = state.get("guideline_packets", [])
    question = state.get("question", "What changed and what should I pay attention to?")

    all_packets_summary = json.dumps(
        {
            "extracted_facts": extracted_packets[:20],
            "guideline_evidence": guideline_packets[:10],
        },
        default=str,
    )

    system_prompt = (
        "You are a clinical co-pilot. Synthesize the provided extracted patient facts "
        "and guideline evidence into a structured response. "
        "Every clinical claim MUST reference a source_id from the provided packets. "
        "Do NOT make treatment recommendations. Do NOT diagnose. "
        "Return valid JSON matching the LLMOutput schema: "
        '{"answer_type": "pre_room_brief", "claims": [...], "missing_data": [...], '
        '"refusals": [...], "suggested_followups": [...]}'
    )

    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))
    model = "claude-haiku-4-5-20251001"

    response = client.messages.create(
        model=model,
        max_tokens=1024,
        system=system_prompt,
        messages=[
            {
                "role": "user",
                "content": f"Question: {question}\n\nEvidence: {all_packets_summary}",
            }
        ],
    )

    text = response.content[0].text if response.content else "{}"
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {
            "answer_type": "pre_room_brief",
            "claims": [],
            "missing_data": ["Could not parse synthesizer output."],
            "refusals": [],
            "suggested_followups": [],
        }


def verifier_node(state: CopilotState) -> dict[str, Any]:
    """Run the deterministic verifier on the synthesizer's LLM output."""
    started = time.monotonic()

    llm_output_dict = state.get("llm_output") or {}
    all_packets = (
        list(state.get("extracted_packets", []))
        + list(state.get("guideline_packets", []))
    )

    try:
        from app.schemas import LLMOutput, SourcePacket
        from app.verifier import patient_uuid_hash, verify

        llm_output = LLMOutput(**llm_output_dict)
        packets = [SourcePacket(**p) for p in all_packets]
        req_hash = state.get("patient_uuid_hash", "")
        trace_id = state.get("trace_id", "graph-eval")

        verified = verify(llm_output, packets, req_hash, trace_id=trace_id)
        verified_response = verified.model_dump()
        verifier_status = "done"
    except Exception as e:
        logger.error("verifier_node error: %s", e)
        verified_response = {
            "answer_type": "pre_room_brief",
            "claims": [],
            "missing_data": [f"Verifier error: {e}"],
            "refusals": [],
            "suggested_followups": [],
            "verifier_status": "failed",
            "unsupported_dropped": 0,
            "verifier_issues": [],
            "trace_id": state.get("trace_id", ""),
            "selected_tools": [],
            "planner_status": None,
            "tool_results_summary": [],
        }
        verifier_status = "error"

    elapsed_ms = (time.monotonic() - started) * 1000
    logger.info("verifier_node: done in %.1fms, status=%s", elapsed_ms, verifier_status)

    path = list(state.get("graph_path", []))
    path.append("verifier")

    return {
        "verifier_status": verifier_status,
        "verified_response": verified_response,
        "current_node": "verifier",
        "graph_path": path,
    }
