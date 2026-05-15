"""Graph node implementations for the LangGraph CopilotState graph.

Node contract: each function accepts CopilotState and returns a partial dict
update. LangGraph merges these updates into the running state.

Synthesizer (COPILOT_SYNTHESIS_MODEL, default Sonnet 4.6) is the ONLY LLM call
in the graph (AgDR-0041).
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


def _append_worker_handoff(
    state: CopilotState,
    from_node: str,
    to_node: str,
    reason: str,
) -> list[dict[str, Any]]:
    handoffs = list(state.get("worker_handoffs", []))
    handoffs.append({
        "from": from_node,
        "to": to_node,
        "reason": reason,
        "timestamp_ms": int(time.monotonic() * 1000),
    })
    return handoffs


def _eval_synthesis_response(state: CopilotState) -> dict[str, Any]:
    """Deterministic synthesis response for COPILOT_EVAL_MODE=1.

    A question-hash registered in ``_EVAL_SYNTHESIS_RESPONSES`` takes
    precedence over the packet-derived default — this is how AgDR-0075's
    critic eval cases pin specific brief shapes (uncited claim, dose-change
    without graded source) for the critic_node to evaluate. The legacy
    packet-derived fallback still fires for unregistered questions so
    existing eval cases keep their behavior.
    """

    question = state.get("question", "")
    key = hashlib.sha256(question.encode()).hexdigest()[:16]
    registered = _EVAL_SYNTHESIS_RESPONSES.get(key)
    if registered is not None:
        return dict(registered)

    base = dict(_EVAL_SYNTHESIS_RESPONSES["__default__"])
    packets = list(state.get("extracted_packets", [])) + list(state.get("guideline_packets", []))
    if packets:
        first = packets[0]
        source_id = first.get("source_id") if isinstance(first, dict) else None
        label = first.get("label") if isinstance(first, dict) else None
        value = first.get("value") if isinstance(first, dict) else None
        if isinstance(source_id, str) and source_id:
            base["claims"] = [{
                "text": f"{label or 'Document evidence'} is available: {value if value is not None else 'see cited source'}.",
                "claim_type": "fact",
                "source_ids": [source_id],
                "caveat": None,
            }]
    return base


def _register_eval_synthesis_response(question: str, response: dict[str, Any]) -> None:
    """Register a deterministic llm_output keyed by sha256(question)[:16].

    AgDR-0075 eval cases call this at import time so the critic_node sees
    the exact brief shape the case is designed to exercise. Kept private —
    consumers outside the test/eval surface should not rely on this; the
    registry's purpose is reproducibility under ``COPILOT_EVAL_MODE=1``.
    """

    key = hashlib.sha256(question.encode()).hexdigest()[:16]
    _EVAL_SYNTHESIS_RESPONSES[key] = response


# AgDR-0075 — pre-register critic eval-case llm_outputs. Question strings
# must match the ``request.question`` field in the matching case JSON
# verbatim; if the case is edited, this block must be edited in lockstep.
# The registry is the contract between the eval case and the synthesizer
# mock, so a drift surfaces as a synthesizer producing the default packet-
# derived claim instead of the dose-change scenario the case targets.
_register_eval_synthesis_response(
    "Critic eval: warfarin dose escalation",
    {
        "answer_type": "pre_room_brief",
        "claims": [
            {
                "text": "Increase warfarin to 7.5 mg daily.",
                "claim_type": "fact",
                "source_ids": ["lab:inr:apr"],
                "caveat": None,
            }
        ],
        "missing_data": [],
        "refusals": [],
        "suggested_followups": [],
    },
)
_register_eval_synthesis_response(
    "Critic eval: metformin discontinuation",
    {
        "answer_type": "pre_room_brief",
        "claims": [
            {
                "text": "Discontinue metformin given recent eGFR trend.",
                "claim_type": "fact",
                "source_ids": ["lab:egfr:apr"],
                "caveat": None,
            }
        ],
        "missing_data": [],
        "refusals": [],
        "suggested_followups": [],
    },
)
_register_eval_synthesis_response(
    "Critic eval: uncited inference",
    {
        "answer_type": "pre_room_brief",
        "claims": [
            {
                "text": "Patient is at elevated cardiovascular risk.",
                "claim_type": "fact",
                "source_ids": [],
                "caveat": None,
            }
        ],
        "missing_data": [],
        "refusals": [],
        "suggested_followups": [],
    },
)
_register_eval_synthesis_response(
    "Critic eval: well grounded answer",
    {
        "answer_type": "pre_room_brief",
        "claims": [
            {
                "text": "A1c was 7.4% on 2026-01-15.",
                "claim_type": "fact",
                "source_ids": ["lab:a1c:jan"],
                "caveat": None,
            }
        ],
        "missing_data": [],
        "refusals": [],
        "suggested_followups": [],
    },
)


def intake_extractor_node(state: CopilotState) -> dict[str, Any]:
    """Call the intake/lab extractors for uploaded documents.

    In eval mode returns a deterministic empty extraction result.
    In live mode delegates to app.extractors (Team A).
    """
    started = time.monotonic()

    # Update state to mark running
    documents = state.get("documents", [])

    if _EVAL_MODE and not documents:
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
        "worker_handoffs": _append_worker_handoff(
            state,
            state.get("current_node", "start"),
            "intake_extractor",
            f"processed documents={len(documents)}; intake_status={intake_status}; lab_status={lab_status}",
        ),
    }


# AgDR-0080 — deterministic keyword-based question classifier for
# domain-specific source filtering. The intent is a cheap quality lever
# (vaccine questions should not consider openFDA drug labels; drug-safety
# questions should not consider CDC ACIP) without paying for an LLM
# classifier. The triplet of regexes is the entire policy — extending or
# changing the policy requires (a) a code change here, (b) a unit test
# update, and (c) an AgDR if the change is durable.
import re

_VACCINE_QUESTION_RE = re.compile(
    r"\b(vaccin\w*|immuniz\w*|booster|inoculat\w*)\b", re.IGNORECASE
)
_DRUG_SAFETY_QUESTION_RE = re.compile(
    r"\b(safe|safety|contraindicat\w*|interact\w*|adverse|reaction|allerg\w*|"
    r"dose|dosing|dosage|titrat\w*|escalat\w*|discontinu\w*|taper|hold)\b",
    re.IGNORECASE,
)

_VACCINE_FILTER_SOURCES: list[str] = ["CDC-ACIP"]
_DRUG_SAFETY_FILTER_SOURCES: list[str] = [
    "FDA",
    "ACC-AHA",
    "ADA",
    "HMS-LOE",
]


def _classify_question_for_filter(question: str) -> tuple[str, list[str] | None]:
    """Map a natural-language question to a retrieval-filter source set.

    Returns a ``(category, source_organizations | None)`` tuple. Category
    is one of ``vaccine`` / ``drug_safety`` / ``broad`` and is logged
    so the Langfuse trace shows which classification path fired.
    LLM-based classifier deferred to Wk3 (AgDR-0080 follow-up).

    The order matters when both regexes match: vaccine wins because the
    canonical Wk2 vaccine questions ("is the patient due for a Tdap
    booster — is it safe given her history?") would otherwise route to
    drug-safety on the "safe" keyword.
    """
    if _VACCINE_QUESTION_RE.search(question):
        return ("vaccine", _VACCINE_FILTER_SOURCES)
    if _DRUG_SAFETY_QUESTION_RE.search(question):
        return ("drug_safety", _DRUG_SAFETY_FILTER_SOURCES)
    return ("broad", None)


def _derive_pre_room_query_from_packets(packets: list[dict[str, Any]]) -> str:
    """Plan_wk2_Claude_Next08 §W2 — derive a retrieval query from chart
    packets for pre_room_brief turns (where ``question`` is empty).

    The pre_room_brief use case has no user-supplied question, so the
    retriever was previously running with an empty query and returning
    zero chunks — leaving every synthesized claim without a citation and
    causing the verifier to drop them all. This helper concatenates the
    chart's most clinically meaningful labels (active problems +
    active medication drug names + active allergy substances) into a
    single retrieval query so the corpus surfaces guidelines that match
    the patient's clinical context.

    Limits the query to ~200 chars (typical RAG embedder token cap is
    generous, but we don't need novella-length queries). De-dupes labels.
    """
    if not packets:
        return ""
    labels: list[str] = []
    seen: set[str] = set()
    for p in packets:
        for key in ("label", "value"):
            raw = p.get(key)
            if not isinstance(raw, str):
                continue
            candidate = raw.strip()
            if not candidate or len(candidate) > 80:
                continue
            normalized = candidate.lower()
            if normalized in seen:
                continue
            seen.add(normalized)
            labels.append(candidate)
            if len(labels) >= 12:
                break
        if len(labels) >= 12:
            break
    return " ".join(labels)[:200]


def evidence_retriever_node(state: CopilotState) -> dict[str, Any]:
    """Retrieve guideline evidence via hybrid RAG (Team B).

    In eval mode returns deterministic empty guideline packets.
    In live mode delegates to app.rag (Team B), with AgDR-0080 source
    filtering applied based on the question's classified category.

    Plan_wk2_Claude_Next08 §W2: when the explicit user question is empty
    (the pre_room_brief use case), fall back to a query derived from the
    chart's source packets. Without this fallback the retriever ran with
    "" and returned zero chunks, leaving every synthesized claim without
    a citation. The verifier then dropped all claims as
    "no_grade_citation" and the brief surfaced as
    "Guideline evidence packets were not provided".
    """
    started = time.monotonic()
    question = state.get("question", "")
    patient_uuid_hash = state.get("patient_uuid_hash", "")

    if not question:
        question = _derive_pre_room_query_from_packets(state.get("extracted_packets", []))
        if question:
            logger.info(
                "evidence_retriever_node: derived pre-room query from %d chart packets: %r",
                len(state.get("extracted_packets", [])),
                question[:80] + ("…" if len(question) > 80 else ""),
            )

    try:
        from app.rag import retrieve_guidelines

        sanitized_question = _strip_phi_from_query(question, patient_uuid_hash)
        category, filter_sources = _classify_question_for_filter(sanitized_question)
        if filter_sources is not None:
            logger.info(
                "evidence_retriever_node: classified question as %s, "
                "restricting to %s",
                category,
                filter_sources,
            )
        # AgDR-0085 — turn on synonym expansion by default for the live
        # graph. Eval-mode mocks don't go through this path, so the cost
        # is real-only. The deterministic expander is cheap (<1ms);
        # paraphrase RRF reuses the same candidate pool.
        chunks = retrieve_guidelines(
            sanitized_question,
            source_organizations=filter_sources,
            expand_synonyms=True,
        )
        guideline_packets = [_guideline_chunk_to_packet(c, patient_uuid_hash) for c in chunks]
        retrieval_status = "done"
    except Exception as e:
        logger.error("evidence_retriever_node error: %s", e)
        guideline_packets = []
        retrieval_status = "error"
        category = "broad"

    elapsed_ms = (time.monotonic() - started) * 1000
    logger.info(
        "evidence_retriever_node: done in %.1fms, chunks=%d, category=%s",
        elapsed_ms,
        len(guideline_packets),
        category,
    )

    path = list(state.get("graph_path", []))
    path.append("evidence_retriever")

    return {
        "retrieval_status": retrieval_status,
        "guideline_packets": guideline_packets,
        "current_node": "evidence_retriever",
        "graph_path": path,
        "worker_handoffs": _append_worker_handoff(
            state,
            state.get("current_node", "start"),
            "evidence_retriever",
            f"retrieval_status={retrieval_status} category={category}",
        ),
    }


def _strip_phi_from_query(question: str, patient_uuid_hash: str) -> str:
    """Remove patient hash from retrieval query (no PHI in corpus queries)."""
    if patient_uuid_hash and patient_uuid_hash in question:
        return question.replace(patient_uuid_hash, "[PATIENT]")
    return question


def _guideline_chunk_to_packet(chunk: Any, patient_uuid_hash: str) -> dict[str, Any]:
    """Map a GuidelineChunk into the verifier's SourcePacket contract."""
    data = chunk.model_dump() if hasattr(chunk, "model_dump") else dict(chunk)
    chunk_id = str(data.get("chunk_id") or data.get("source_id") or "guideline")
    text = str(data.get("text") or "")
    return {
        "source_id": chunk_id,
        "patient_uuid": patient_uuid_hash,
        "resource_type": "Guideline",
        "source_table": "rag_corpus",
        "source_uuid": None,
        "field": "guideline.text",
        "label": str(data.get("source_name") or "Guideline evidence"),
        "value": text,
        "unit": None,
        "observed_at": None,
        "last_updated": None,
        "freshness": "unknown",
        "status": None,
        "sensitive": False,
        "source_type": "guideline_chunk",
        "field_or_chunk_id": chunk_id,
        "quote_or_value": text[:500],
        "page_or_section": data.get("page_or_section"),
        "recommendation_grade": data.get("recommendation_grade"),
        "source_year": data.get("source_year"),
        "source_organization": data.get("source_organization"),
    }


def synthesizer_node(state: CopilotState) -> dict[str, Any]:
    """Call Claude to synthesize extracted + guideline packets into a response.

    This is the ONLY LLM call in the graph (AgDR-0041).
    In eval mode returns a deterministic golden response per case hash.
    """
    started = time.monotonic()

    if _EVAL_MODE:
        llm_output = _eval_synthesis_response(state)
        synthesis_status = "done"
    else:
        try:
            llm_output = _call_synthesizer(state)
            if not llm_output.get("claims") and not (state.get("question") or "").strip():
                fallback_output = _fallback_pre_room_llm_output(state)
                if fallback_output.get("claims"):
                    logger.warning(
                        "synthesizer_node: live synthesis returned 0 claims for pre-room brief; "
                        "using deterministic source-packet fallback"
                    )
                    llm_output = fallback_output
            synthesis_status = "done"
        except Exception as e:
            logger.error("synthesizer_node LLM call failed: %s", e)
            fallback_output = _fallback_pre_room_llm_output(state)
            if not (state.get("question") or "").strip() and fallback_output.get("claims"):
                logger.warning(
                    "synthesizer_node: live synthesis failed for pre-room brief; "
                    "using deterministic source-packet fallback"
                )
                llm_output = fallback_output
                synthesis_status = "done"
            else:
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
        "worker_handoffs": _append_worker_handoff(
            state,
            state.get("current_node", "evidence_retriever"),
            "synthesizer",
            f"synthesis_status={synthesis_status}",
        ),
    }


def _call_synthesizer(state: CopilotState) -> dict[str, Any]:
    """Make the actual synthesis API call. Only invoked in live mode."""
    import anthropic  # type: ignore[import-not-found]
    import os

    from app.schemas import LLMOutput

    extracted_packets = state.get("extracted_packets", [])
    guideline_packets = state.get("guideline_packets", [])
    question = (state.get("question") or "").strip() or (
        "Prepare a concise pre-room brief from the provided source packets. "
        "Summarize active problems, active prescriptions, allergies, recent labs, "
        "immunizations, and any retrieved guideline evidence. Cite only provided "
        "source_ids, include a caveat when citing stale packets, and do not make "
        "treatment recommendations."
    )

    all_packets_summary = json.dumps(
        {
            "extracted_facts": extracted_packets[:20],
            "guideline_evidence": guideline_packets[:10],
        },
        default=str,
    )

    tool_name = "emit_briefing"
    system_prompt = (
        "You are a clinical co-pilot. Synthesize the provided extracted patient facts "
        "and guideline evidence into a structured response. "
        "Every clinical claim MUST reference a source_id from the provided packets. "
        "Do NOT make treatment recommendations. Do NOT diagnose. "
        f"Use the {tool_name} tool. Drop unsupported claims rather than fabricating sources."
    )

    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))
    model = os.getenv("COPILOT_SYNTHESIS_MODEL", "claude-sonnet-4-6")

    def briefing_tool() -> dict[str, Any]:
        return {
            "name": tool_name,
            "description": "Emit the structured clinical briefing. Every claim cites source_ids from the provided packets.",
            "input_schema": LLMOutput.model_json_schema(),
        }

    def parse_tool_response(response: Any) -> tuple[dict[str, Any] | None, list[str], str]:
        raw_text = ""
        tool_input: dict[str, Any] | None = None
        for block in getattr(response, "content", []):
            block_type = getattr(block, "type", None)
            if block_type == "text":
                raw_text += str(getattr(block, "text", ""))
            elif block_type == "tool_use" and getattr(block, "name", None) == tool_name:
                candidate = getattr(block, "input", None)
                if isinstance(candidate, dict):
                    tool_input = candidate
        if tool_input is None:
            return None, ["missing emit_briefing tool call"], raw_text
        try:
            return LLMOutput.model_validate(tool_input).model_dump(), [], raw_text
        except Exception as exc:
            return None, [f"LLMOutput schema validation failed: {exc}"], raw_text

    def create_message(prompt: str) -> Any:
        return client.messages.create(
            model=model,
            max_tokens=1024,
            system=system_prompt,
            tools=[briefing_tool()],
            tool_choice={"type": "tool", "name": tool_name},
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
        )

    response = create_message(
        f"Question: {question}\n\nEvidence: {all_packets_summary}\n\n"
        "Return the response using the tool. Cite only source_ids present in Evidence."
    )
    parsed, errors, raw_text = parse_tool_response(response)
    if parsed is not None:
        return parsed

    logger.warning("synthesizer structured output retrying after invalid tool payload: %s", "; ".join(errors))
    repair_response = create_message(
        "Your previous response failed structured validation:\n- "
        + "\n- ".join(errors[:5])
        + "\nReturn a corrected response using the tool. "
        "Drop unsupported claims rather than fabricating citations.\n\n"
        f"Question: {question}\n\nEvidence: {all_packets_summary}"
        + ("\nPrevious non-tool text was ignored." if raw_text else "")
    )
    repaired, repair_errors, _ = parse_tool_response(repair_response)
    if repaired is not None:
        return repaired

    raise ValueError(
        "synthesizer_structured_output_failed: "
        + "; ".join(repair_errors or errors)
    )


def _fallback_pre_room_llm_output(state: CopilotState) -> dict[str, Any]:
    """Build a conservative source-only pre-room brief when live synthesis
    returns no usable claims.

    This fallback is intentionally narrow: it only summarizes facts already in
    SourcePackets, cites those packets directly, and leaves clinical judgment to
    the chart/user. It exists because the browser pre-room path has no user
    question; if the live model emits no tool payload for that richer packet set,
    an empty card is less useful than verified chart facts.
    """
    packets = list(state.get("extracted_packets", []))
    guideline_packets = list(state.get("guideline_packets", []))
    claims: list[dict[str, Any]] = []
    missing_data: list[str] = []

    def packet_text(packet: dict[str, Any]) -> str:
        value = packet.get("value")
        unit = packet.get("unit")
        text = str(value) if value is not None else ""
        if unit:
            text = f"{text} {unit}".strip()
        return text.strip()

    def stale_caveat(selected: list[dict[str, Any]], noun: str) -> str | None:
        stale = [p for p in selected if p.get("freshness") == "stale"]
        if not stale:
            return None
        dates = [
            str(p.get("observed_at") or p.get("last_updated") or "").split(" ")[0]
            for p in stale
        ]
        dates = [d for d in dates if d]
        if dates:
            return f"One or more cited {noun} records are stale as of {', '.join(dates[:3])}."
        return f"One or more cited {noun} records are stale."

    problems = [
        p for p in packets
        if p.get("resource_type") == "Condition" and p.get("status") == "active"
    ]
    if problems:
        names = [packet_text(p) for p in problems if packet_text(p)]
        if names:
            claims.append({
                "text": "Problem list includes " + ", ".join(names) + ".",
                "claim_type": "fact",
                "source_ids": [str(p["source_id"]) for p in problems],
                "caveat": stale_caveat(problems, "problem"),
            })

    prescriptions = [
        p for p in packets
        if p.get("resource_type") == "MedicationRequest" and p.get("status") == "active"
    ]
    if prescriptions:
        names = [packet_text(p) for p in prescriptions if packet_text(p)]
        if names:
            claims.append({
                "text": "Active prescriptions include " + ", ".join(names) + ".",
                "claim_type": "fact",
                "source_ids": [str(p["source_id"]) for p in prescriptions],
                "caveat": stale_caveat(prescriptions, "prescription"),
            })

    allergies = [
        p for p in packets
        if p.get("resource_type") == "AllergyIntolerance" and p.get("status") == "active"
    ]
    if allergies:
        names = [packet_text(p) for p in allergies if packet_text(p)]
        if names:
            claims.append({
                "text": "Allergy list includes " + ", ".join(names) + ".",
                "claim_type": "fact",
                "source_ids": [str(p["source_id"]) for p in allergies],
                "caveat": stale_caveat(allergies, "allergy"),
            })

    labs = [
        p for p in packets
        if p.get("resource_type") == "Observation" and p.get("source_table") == "procedure_result"
    ]
    for lab in labs[:3]:
        label = str(lab.get("label") or "Lab result").strip()
        value = packet_text(lab)
        date = str(lab.get("observed_at") or "").split(" ")[0]
        if not value:
            continue
        text = f"{label} was {value}"
        if date:
            text += f" on {date}"
        text += "."
        claims.append({
            "text": text,
            "claim_type": "fact",
            "source_ids": [str(lab["source_id"])],
            "caveat": stale_caveat([lab], "lab"),
        })

    immunizations = [
        p for p in packets
        if p.get("resource_type") == "Immunization"
    ]
    for imm in immunizations[:1]:
        value = packet_text(imm)
        date = str(imm.get("observed_at") or "").split(" ")[0]
        if not value:
            continue
        text = f"Immunization record includes {value}"
        if date:
            text += f" on {date}"
        if imm.get("status"):
            text += f" with status {imm['status']}"
        text += "."
        claims.append({
            "text": text,
            "claim_type": "fact",
            "source_ids": [str(imm["source_id"])],
            "caveat": stale_caveat([imm], "immunization"),
        })

    if guideline_packets:
        guideline = guideline_packets[0]
        label = str(guideline.get("label") or "Retrieved guideline evidence").strip()
        claims.append({
            "text": f"Retrieved guideline evidence is available from {label}.",
            "claim_type": "fact",
            "source_ids": [str(guideline["source_id"])],
            "caveat": stale_caveat([guideline], "guideline"),
        })

    return {
        "answer_type": "pre_room_brief",
        "claims": claims,
        "missing_data": missing_data,
        "refusals": [],
        "suggested_followups": [],
    }


def critic_node(state: CopilotState) -> dict[str, Any]:
    """AgDR-0075 — LLM-layer safety critic.

    Runs after ``synthesizer_node``, before ``verifier_node``. Emits a
    ``CriticVerdict`` over the synthesized brief and, on any
    ``severity="reject"`` flag, rewrites the in-flight ``llm_output`` to
    a safe-refusal shape so the verifier sees a clean refusal instead of a
    flagged-but-still-claiming brief.

    Eval mode (``COPILOT_EVAL_MODE=1``) uses ``deterministic_critic_verdict``
    so the eval suite is reproducible without an Anthropic key. Live mode
    calls Haiku 4.5 via forced tool-use with a one-shot repair; on any
    failure it degrades to the same deterministic policy — safer than
    silently passing every brief through.
    """

    started = time.monotonic()

    from .critic import (
        _call_live_critic,
        apply_critic_verdict_to_llm_output,
        deterministic_critic_verdict,
    )

    llm_output_dict: dict[str, Any] = dict(state.get("llm_output") or {})
    all_packets: list[dict[str, Any]] = (
        list(state.get("extracted_packets", []))
        + list(state.get("guideline_packets", []))
    )
    question = state.get("question", "")
    answer_type = llm_output_dict.get("answer_type", "pre_room_brief")
    claims = llm_output_dict.get("claims") or []

    if answer_type == "refusal" or not claims:
        # Nothing to critique on an already-refused or empty-claim brief.
        # Surface as "skipped" so the Langfuse span carries the reason.
        verdict_dict: dict[str, Any] = {
            "accepted": True,
            "flagged_claims": [],
            "confidence": 1.0,
        }
        critic_status = "skipped"
    else:
        try:
            if _EVAL_MODE:
                verdict_dict = deterministic_critic_verdict(llm_output_dict, all_packets)
            else:
                verdict_dict = _call_live_critic(llm_output_dict, all_packets, question)
            critic_status = "passed" if verdict_dict.get("accepted") else "rejected"
        except Exception as e:
            logger.error("critic_node error: %s", e)
            verdict_dict = {
                "accepted": True,
                "flagged_claims": [],
                "confidence": 0.0,
            }
            critic_status = "error"

    # On reject — rewrite llm_output to a safe-refusal shape so verifier_node
    # produces a clean refusal VerifiedResponse downstream.
    updated_llm_output = apply_critic_verdict_to_llm_output(
        llm_output_dict, verdict_dict
    )

    elapsed_ms = (time.monotonic() - started) * 1000
    flag_count = len(verdict_dict.get("flagged_claims") or [])
    reject_count = sum(
        1 for f in (verdict_dict.get("flagged_claims") or [])
        if isinstance(f, dict) and f.get("severity") == "reject"
    )
    logger.info(
        "critic_node: done in %.1fms, status=%s, flags=%d (rejects=%d)",
        elapsed_ms,
        critic_status,
        flag_count,
        reject_count,
    )

    path = list(state.get("graph_path", []))
    path.append("critic")

    return {
        "critic_status": critic_status,
        "critic_verdict": verdict_dict,
        "llm_output": updated_llm_output,
        "current_node": "critic",
        "graph_path": path,
        "worker_handoffs": _append_worker_handoff(
            state,
            state.get("current_node", "synthesizer"),
            "critic",
            f"critic_status={critic_status} flags={flag_count} rejects={reject_count}",
        ),
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
            "critic_verdict": None,
        }
        verifier_status = "error"

    # AgDR-0075 — propagate the critic verdict (if any) so consumers see
    # the per-claim flag list on the final response packet. Verifier itself
    # is critic-unaware; the merge happens here at the node boundary.
    critic_verdict = state.get("critic_verdict")
    if critic_verdict is not None:
        verified_response["critic_verdict"] = critic_verdict

    elapsed_ms = (time.monotonic() - started) * 1000
    logger.info("verifier_node: done in %.1fms, status=%s", elapsed_ms, verifier_status)

    path = list(state.get("graph_path", []))
    path.append("verifier")

    return {
        "verifier_status": verifier_status,
        "verified_response": verified_response,
        "current_node": "verifier",
        "graph_path": path,
        "worker_handoffs": _append_worker_handoff(
            state,
            state.get("current_node", "critic"),
            "verifier",
            f"verifier_status={verifier_status}",
        ),
    }
