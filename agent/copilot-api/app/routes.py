"""Wk2 sidecar routes — Workstream A implementation (Plan §5 step 7, §6).

Endpoints implemented here:
  - ``POST /v1/extract/lab-pdf``      — Workstream A (lab PDF extractor)
  - ``POST /v1/extract/intake-form``  — Workstream A (intake-form extractor)
  - ``POST /v1/copilot/answer``       — Workstream C (LangGraph supervisor)

File-size limits (AgDR plan §6 / hard rules):
  - Maximum 10 pages; maximum 8 MB.
  - Validated at route entry before calling the extractor.

(AgDR-0044: contract-freeze artifact for Wk2 parallel teams.)
"""

from __future__ import annotations

import hashlib
import io
import logging
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .auth import require_gateway_secret
from .schemas import ExtractedDocument

logger = logging.getLogger(__name__)

router = APIRouter()

_MAX_BYTES = 8 * 1024 * 1024  # 8 MB
_MAX_PAGES = 10


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _validate_upload_size(content: bytes, filename: str) -> None:
    if len(content) > _MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"file_too_large: {filename!r} exceeds 8 MB limit",
        )


def _validate_pdf_page_count(content: bytes, filename: str) -> None:
    """Reject PDFs with more than 10 pages."""
    try:
        import pypdfium2 as pdfium  # type: ignore[import-untyped]
        doc = pdfium.PdfDocument(content)
        try:
            count = len(doc)
        finally:
            doc.close()
        if count > _MAX_PAGES:
            raise HTTPException(
                status_code=413,
                detail=f"too_many_pages: {filename!r} has {count} pages; limit is {_MAX_PAGES}",
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Could not count pages in %r: %s", filename, exc)


@router.post(
    "/v1/extract/lab-pdf",
    dependencies=[Depends(require_gateway_secret)],
    summary="Extract structured fields from a lab PDF.",
    response_model=ExtractedDocument,
)
async def extract_lab_pdf(
    file: UploadFile = File(..., description="Lab PDF file (max 10 pages, 8 MB)"),
    patient_uuid_hash: str = Form(..., description="SHA-256 of patient UUID"),
) -> Any:
    """Extract structured lab results from a PDF using Anthropic Vision + pdfplumber.

    Returns an ``ExtractedDocument`` with ``LabResult`` payload.
    The PHP gateway is responsible for persisting the results to
    ``copilot_document_facts`` via ``DocumentFactsRepository``.

    File constraints: max 10 pages, max 8 MB. Returns HTTP 413 if exceeded.
    """
    from .extractors.lab_pdf import extract_lab_pdf as _extract

    content = await file.read()
    filename = file.filename or "upload.pdf"

    _validate_upload_size(content, filename)

    if content[:4] == b"%PDF":
        _validate_pdf_page_count(content, filename)

    document_sha256 = _sha256_bytes(content)

    try:
        result = _extract(
            pdf_bytes=content,
            patient_uuid_hash=patient_uuid_hash,
            document_sha256=document_sha256,
            filename=filename,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Lab PDF extraction failed for %r: %s", filename, exc)
        raise HTTPException(status_code=500, detail="extraction_failed") from exc

    return JSONResponse(content=result)


@router.post(
    "/v1/extract/intake-form",
    dependencies=[Depends(require_gateway_secret)],
    summary="Extract structured fields from an intake form.",
    response_model=ExtractedDocument,
)
async def extract_intake_form(
    file: UploadFile = File(..., description="Intake form (PDF, PNG, or JPEG; max 10 pages, 8 MB)"),
    patient_uuid_hash: str = Form(..., description="SHA-256 of patient UUID"),
) -> Any:
    """Extract structured fields from an intake form (typed PDF, scanned PNG/JPEG).

    Returns an ``ExtractedDocument`` with ``IntakeFields`` payload.
    For image-only forms, bbox is omitted; verbatim quotes may be null for
    handwritten fields.

    File constraints: max 10 pages (PDFs), max 8 MB.
    """
    from .extractors.intake_form import extract_intake_form as _extract

    content = await file.read()
    filename = file.filename or "upload.pdf"

    _validate_upload_size(content, filename)

    if content[:4] == b"%PDF":
        _validate_pdf_page_count(content, filename)

    document_sha256 = _sha256_bytes(content)

    try:
        result = _extract(
            content=content,
            patient_uuid_hash=patient_uuid_hash,
            document_sha256=document_sha256,
            filename=filename,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Intake form extraction failed for %r: %s", filename, exc)
        raise HTTPException(status_code=500, detail="extraction_failed") from exc

    return JSONResponse(content=result)


# === Wk2 Workstream C: POST /v1/copilot/answer — LangGraph supervisor entrypoint ===


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
    Runs through intake_extractor → evidence_retriever → synthesizer → verifier
    (some nodes may be skipped by the deterministic supervisor routing).

    Returns a ``VerifiedResponse``-shaped JSON payload. Always returns 200 on
    logical completion; verifier_status reflects clinical quality, not HTTP status.
    """
    import os
    import uuid

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
        "worker_handoffs": 0,
        "decision_reason": "",
        "error_message": None,
        "low_confidence_count": 0,
        "eval_mode": eval_mode,
        "langfuse_trace_id": run_id,
    }

    # Inject pre-fetched gateway packets into extracted_packets
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
