"""Wk2 sidecar routes — contract-freeze stubs (Plan §5 step 7, §6).

This module locks the URL surface for parallel teams:
  - ``POST /v1/extract/lab-pdf``      — Workstream A (lab PDF extractor)
  - ``POST /v1/extract/intake-form``  — Workstream A (intake-form extractor)
  - ``POST /v1/copilot/answer``       — Workstream C (LangGraph supervisor)

Routes go through the shared ``require_gateway_secret`` dependency so the
auth contract is identical to the existing /v1/brief and /v1/tool-plan
endpoints — gateway-secret + (optional) task-token.

(AgDR-0044: contract-freeze artifact for Wk2 parallel teams.)
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .auth import require_gateway_secret

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/v1/extract/lab-pdf",
    dependencies=[Depends(require_gateway_secret)],
    status_code=501,
    summary="[W0.5 stub] Extract structured fields from a lab PDF.",
)
def extract_lab_pdf() -> dict[str, str]:
    """Workstream A deliverable. Returns ``ExtractedDocument`` with ``LabResult``.

    Stub at W0.5 — the body is implemented in the Workstream A PR.
    """

    raise HTTPException(
        status_code=501,
        detail="not_implemented_workstream_a",
    )


@router.post(
    "/v1/extract/intake-form",
    dependencies=[Depends(require_gateway_secret)],
    status_code=501,
    summary="[W0.5 stub] Extract structured fields from an intake form.",
)
def extract_intake_form() -> dict[str, str]:
    """Workstream A deliverable. Returns ``ExtractedDocument`` with ``IntakeFields``.

    Stub at W0.5 — the body is implemented in the Workstream A PR.
    """

    raise HTTPException(
        status_code=501,
        detail="not_implemented_workstream_a",
    )


# === Wk2 Workstream C: POST /v1/copilot/answer — LangGraph supervisor ===


class _CopilotAnswerRequest(BaseModel):
    """Request body for POST /v1/copilot/answer."""

    trace_id: str = Field(..., description="Caller-supplied trace ID for observability.")
    patient_uuid_hash: str = Field(..., description="SHA-256 of patient UUID (no raw PII).")
    question: str | None = Field(None, max_length=500, description="Free-text clinical question.")
    use_case: str = Field("pre_room_brief", max_length=64)
    documents: list[dict[str, str]] | None = Field(
        None,
        description="Optional document refs [{path, doc_type}] triggering intake_extractor.",
    )
    packets: list[dict[str, Any]] | None = Field(
        None,
        description="Pre-fetched SourcePackets from the gateway tool execution layer.",
    )


@router.post(
    "/v1/copilot/answer",
    dependencies=[Depends(require_gateway_secret)],
    summary="Run the LangGraph clinical supervisor and return a VerifiedResponse.",
    response_model=None,
)
async def copilot_answer(body: _CopilotAnswerRequest) -> JSONResponse:
    """Execute the CopilotState LangGraph graph.

    Accepts a clinical question + optional document refs + pre-fetched packets.
    Runs through intake_extractor -> evidence_retriever -> synthesizer -> verifier
    (some nodes may be skipped by the deterministic supervisor routing).

    Returns a VerifiedResponse-shaped JSON payload. Always returns 200 on
    logical completion; verifier_status reflects clinical quality, not HTTP status.
    """
    from .graph.build import get_compiled_graph
    from .graph.state import CopilotState

    eval_mode = os.getenv("COPILOT_EVAL_MODE") == "1"
    run_id = body.trace_id or str(uuid.uuid4())

    initial_state: CopilotState = {
        "patient_uuid_hash": body.patient_uuid_hash,
        "question": body.question or "",
        "trace_id": run_id,
        "documents": body.documents or [],
        "intake_status": "pending" if body.documents else "skipped",
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
        "eval_mode": eval_mode,
        "langfuse_trace_id": run_id,
    }

    if body.packets:
        from .schemas import SourcePacket

        try:
            parsed = [SourcePacket(**p) for p in body.packets]
            initial_state["extracted_packets"] = [p.model_dump() for p in parsed]
        except Exception as exc:
            logger.warning("Invalid source packets in request: %s", exc)
            raise HTTPException(status_code=422, detail=f"invalid_packets: {exc}") from exc

    try:
        graph = get_compiled_graph()
        final_state: CopilotState = await graph.ainvoke(initial_state)
    except Exception as exc:
        logger.error("Graph execution failed for trace_id=%s: %s", run_id, exc)
        raise HTTPException(status_code=500, detail="graph_execution_failed") from exc

    verified = final_state.get("verified_response")
    if verified is None:
        raise HTTPException(status_code=500, detail="verifier_produced_no_response")

    return JSONResponse(content=verified)
