"""Orchestrator - request → LLM → verifier → repair-once → response."""

from __future__ import annotations

import time

from .llm import call_brief, call_brief_repair
from .observability import record_brief
from .schemas import BriefRequest, LLMOutput, VerifiedResponse, VerifierIssue
from .verifier import verify


def process_brief(req: BriefRequest) -> VerifiedResponse:
    started = time.monotonic()

    try:
        parsed, usage, raw = call_brief(req)
    except Exception as e:
        elapsed_ms = (time.monotonic() - started) * 1000
        return _llm_failure(req, str(e), elapsed_ms)

    if parsed is None:
        elapsed_ms = (time.monotonic() - started) * 1000
        return _llm_failure(req, "schema_parse_failed", elapsed_ms)

    verified = verify(parsed, req.packets, req.patient_uuid_hash, req.trace_id)

    if verified.verifier_status == "failed" and verified.verifier_issues:
        try:
            errors = [f"{i.rule}: {i.detail}" for i in verified.verifier_issues]
            repaired, repair_usage = call_brief_repair(req, errors, raw)
            if repaired is not None:
                verified = verify(repaired, req.packets, req.patient_uuid_hash, req.trace_id)
                usage = {**usage, **{f"repair_{k}": v for k, v in repair_usage.items()}}
        except Exception:
            pass

    elapsed_ms = (time.monotonic() - started) * 1000
    record_brief(
        trace_id=req.trace_id,
        use_case=req.use_case,
        patient_uuid_hash=req.patient_uuid_hash,
        packet_count=len(req.packets),
        usage=usage,
        verifier_status=verified.verifier_status,
        unsupported_dropped=verified.unsupported_dropped,
        duration_ms=elapsed_ms,
    )
    return verified


def _llm_failure(req: BriefRequest, message: str, elapsed_ms: float) -> VerifiedResponse:
    record_brief(
        trace_id=req.trace_id,
        use_case=req.use_case,
        patient_uuid_hash=req.patient_uuid_hash,
        packet_count=len(req.packets),
        usage={"model": "n/a", "input_tokens": 0, "output_tokens": 0},
        verifier_status="failed",
        unsupported_dropped=0,
        duration_ms=elapsed_ms,
    )
    return VerifiedResponse(
        answer_type="refusal",
        claims=[],
        missing_data=[
            "AI summary unavailable. Review the chart directly.",
        ],
        refusals=[message],
        suggested_followups=[],
        verifier_status="failed",
        unsupported_dropped=0,
        verifier_issues=[VerifierIssue(rule="llm_unavailable", detail=message)],
        trace_id=req.trace_id,
    )
