"""Wk2 sidecar routes — Workstream A implementation (Plan §5 step 7, §6).

Endpoints implemented here:
  - ``POST /v1/extract/lab-pdf``         — Workstream A (lab PDF extractor)
  - ``POST /v1/extract/intake-form``     — Workstream A (intake-form extractor)
  - ``POST /v1/extract/medication-list`` — Phase 6.3 (medication-list extractor; AgDR-0077)
  - ``POST /v1/copilot/answer``          — Workstream C (LangGraph supervisor)

File-size limits (AgDR plan §6 / hard rules):
  - Maximum 10 pages; maximum 8 MB.
  - Validated at route entry before calling the extractor.

(AgDR-0044: contract-freeze artifact for Wk2 parallel teams.)
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import time
import uuid
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .auth import require_gateway_secret
from .observability import record_extract
from .schemas import ExtractedDocument

logger = logging.getLogger(__name__)

router = APIRouter()

_MAX_BYTES = 8 * 1024 * 1024  # 8 MB
_MAX_PAGES = 10

_EXT_RE = re.compile(r"^[a-z0-9]{1,8}$")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def redact_filename(raw_name: str, document_sha256: str) -> str:
    """AgDR-0084 / Plan §3.7 — strip PHI from an upload filename.

    Mirrors ``copilot_upload_redact_filename`` in
    ``interface/.../public/api/upload_common.php``. The PHP gateway is the
    primary scrub point; this sidecar-side helper is defense-in-depth so
    a future endpoint that forgets to redact at the gateway boundary
    cannot leak PHI (patient name, MRN, DOB) into FastAPI logs, sidecar
    exception messages, or Langfuse trace metadata.

    Returns ``"upload-{sha256_prefix_8}.{ext}"`` with the extension
    restricted to ``[a-z0-9]{1,8}`` to avoid path-traversal or injection
    at downstream consumers.
    """
    ext_part = os.path.splitext(raw_name)[1].lstrip(".").lower()
    if not ext_part or _EXT_RE.match(ext_part) is None:
        ext_part = "bin"
    return f"upload-{document_sha256[:8]}.{ext_part}"


def _validate_upload_size(content: bytes, filename: str) -> None:
    if len(content) > _MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"file_too_large: {filename!r} exceeds 8 MB limit",
        )


def _validate_pdf_page_count(content: bytes, filename: str) -> None:
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
    File constraints: max 10 pages, max 8 MB. Returns HTTP 413 if exceeded.
    """
    from .extractors.lab_pdf import extract_lab_pdf as _extract
    from .extractors.normalize import normalize_extracted_document

    content = await file.read()
    filename = file.filename or "upload.pdf"

    _validate_upload_size(content, filename)

    if content[:4] == b"%PDF":
        _validate_pdf_page_count(content, filename)

    document_sha256 = _sha256_bytes(content)

    # Plan_wk2_Claude_Next08 §W1 — extraction trace skeleton. Generated at
    # the top of the handler so the same UUID is in the Langfuse marker
    # AND the ExtractedDocument response envelope returned to the gateway.
    run_id = str(uuid.uuid4())
    started_at = time.monotonic()

    # AgDR-0084 / Plan §3.7 — the PHP gateway redacts the raw upload
    # filename to "upload-{sha8}.{ext}" BEFORE the multipart request
    # reaches this route. The ``redact_filename`` helper above is the
    # defense-in-depth Python equivalent; it's intentionally NOT applied
    # at this boundary because the eval-mode deterministic-mock fixture
    # resolver in ``_eval_mocks_a.py`` substring-matches synthetic
    # persona names against the filename (e.g. "p02-whitaker-intake")
    # and a route-level redaction would break the eval fixture lookups.
    # Live production traffic always sees the gateway-redacted form;
    # eval mode sees synthetic personas, not real PHI. Future work:
    # promote fixture resolution to a content-hash mapping so the
    # route-level redaction can land without breaking eval mocks.

    try:
        result = _extract(
            pdf_bytes=content,
            patient_uuid_hash=patient_uuid_hash,
            document_sha256=document_sha256,
            filename=filename,
        )
        result = normalize_extracted_document(
            result,
            doc_type="lab_pdf",
            document_sha256=document_sha256,
            patient_uuid_hash=patient_uuid_hash,
            filename=filename,
        )
        validated = ExtractedDocument.model_validate(result)
    except ValueError as exc:
        record_extract(
            trace_id=run_id, doc_type="lab_pdf", document_sha256=document_sha256,
            patient_uuid_hash=patient_uuid_hash, extracted_field_count=0,
            dropped_field_count=0, duration_ms=(time.monotonic() - started_at) * 1000,
            extractor_status="invalid_input",
        )
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Lab PDF extraction failed for %r: %s", filename, exc)
        record_extract(
            trace_id=run_id, doc_type="lab_pdf", document_sha256=document_sha256,
            patient_uuid_hash=patient_uuid_hash, extracted_field_count=0,
            dropped_field_count=0, duration_ms=(time.monotonic() - started_at) * 1000,
            extractor_status="failed",
        )
        raise HTTPException(status_code=500, detail="extraction_failed") from exc

    validated.trace_id = run_id
    record_extract(
        trace_id=run_id, doc_type="lab_pdf", document_sha256=document_sha256,
        patient_uuid_hash=patient_uuid_hash,
        extracted_field_count=validated.extracted_field_count,
        dropped_field_count=validated.dropped_field_count,
        duration_ms=(time.monotonic() - started_at) * 1000,
    )
    return validated.model_dump(mode="json")


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
    File constraints: max 10 pages (PDFs), max 8 MB.
    """
    from .extractors.intake_form import extract_intake_form as _extract
    from .extractors.normalize import normalize_extracted_document

    content = await file.read()
    filename = file.filename or "upload.pdf"

    _validate_upload_size(content, filename)

    if content[:4] == b"%PDF":
        _validate_pdf_page_count(content, filename)

    document_sha256 = _sha256_bytes(content)
    run_id = str(uuid.uuid4())
    started_at = time.monotonic()

    # AgDR-0084 / Plan §3.7 — see the matching block in extract_lab_pdf
    # for why the route-level redaction is deferred. PHP gateway is the
    # primary scrub; the ``redact_filename`` helper is exposed for
    # defense-in-depth use by future endpoints.

    try:
        result = _extract(
            content=content,
            patient_uuid_hash=patient_uuid_hash,
            document_sha256=document_sha256,
            filename=filename,
        )
        result = normalize_extracted_document(
            result,
            doc_type="intake_form",
            document_sha256=document_sha256,
            patient_uuid_hash=patient_uuid_hash,
            filename=filename,
        )
        validated = ExtractedDocument.model_validate(result)
    except ValueError as exc:
        record_extract(
            trace_id=run_id, doc_type="intake_form", document_sha256=document_sha256,
            patient_uuid_hash=patient_uuid_hash, extracted_field_count=0,
            dropped_field_count=0, duration_ms=(time.monotonic() - started_at) * 1000,
            extractor_status="invalid_input",
        )
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Intake form extraction failed for %r: %s", filename, exc)
        record_extract(
            trace_id=run_id, doc_type="intake_form", document_sha256=document_sha256,
            patient_uuid_hash=patient_uuid_hash, extracted_field_count=0,
            dropped_field_count=0, duration_ms=(time.monotonic() - started_at) * 1000,
            extractor_status="failed",
        )
        raise HTTPException(status_code=500, detail="extraction_failed") from exc

    validated.trace_id = run_id
    record_extract(
        trace_id=run_id, doc_type="intake_form", document_sha256=document_sha256,
        patient_uuid_hash=patient_uuid_hash,
        extracted_field_count=validated.extracted_field_count,
        dropped_field_count=validated.dropped_field_count,
        duration_ms=(time.monotonic() - started_at) * 1000,
    )
    return validated.model_dump(mode="json")


@router.post(
    "/v1/extract/medication-list",
    dependencies=[Depends(require_gateway_secret)],
    summary="Extract structured medication-list entries from a document.",
    response_model=ExtractedDocument,
)
async def extract_medication_list(
    file: UploadFile = File(..., description="Medication list (PDF, PNG, or JPEG; max 10 pages, 8 MB)"),
    patient_uuid_hash: str = Form(..., description="SHA-256 of patient UUID"),
) -> Any:
    """Extract a structured medication list (Plan §6.3, AgDR-0077).

    Returns an ``ExtractedDocument`` whose ``result`` payload is an
    ``ExtractedMedicationList`` carrying both a flat ``fields`` surface
    (one row per medication.<slug>.<attr>) and a structured ``entries``
    list of :class:`app.schemas.MedicationListEntry`. The PHP gateway
    feeds ``entries`` to ``MedicationReconciliation`` to compare against
    the OpenEMR ``prescriptions`` table.
    """
    from .extractors.medication_list import extract_medication_list as _extract
    from .extractors.normalize import normalize_extracted_document

    content = await file.read()
    filename = file.filename or "upload.pdf"

    _validate_upload_size(content, filename)

    if content[:4] == b"%PDF":
        _validate_pdf_page_count(content, filename)

    document_sha256 = _sha256_bytes(content)
    run_id = str(uuid.uuid4())
    started_at = time.monotonic()

    # AgDR-0084 / Plan §3.7 — same filename-redaction posture as
    # extract_lab_pdf / extract_intake_form. The PHP gateway scrubs PHI
    # from the upload filename BEFORE the multipart request reaches this
    # endpoint. The ``redact_filename`` helper above is exposed for
    # defense-in-depth; we don't apply it at the route boundary so the
    # eval-mode fixture resolver in ``_eval_mocks_a.py`` can still match
    # synthetic personas ("p02-whitaker-medication-list") by filename
    # substring.

    try:
        result = _extract(
            content=content,
            patient_uuid_hash=patient_uuid_hash,
            document_sha256=document_sha256,
            filename=filename,
        )
        result = normalize_extracted_document(
            result,
            doc_type="medication_list",
            document_sha256=document_sha256,
            patient_uuid_hash=patient_uuid_hash,
            filename=filename,
        )
        validated = ExtractedDocument.model_validate(result)
    except ValueError as exc:
        record_extract(
            trace_id=run_id, doc_type="medication_list", document_sha256=document_sha256,
            patient_uuid_hash=patient_uuid_hash, extracted_field_count=0,
            dropped_field_count=0, duration_ms=(time.monotonic() - started_at) * 1000,
            extractor_status="invalid_input",
        )
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Medication-list extraction failed for %r: %s", filename, exc)
        record_extract(
            trace_id=run_id, doc_type="medication_list", document_sha256=document_sha256,
            patient_uuid_hash=patient_uuid_hash, extracted_field_count=0,
            dropped_field_count=0, duration_ms=(time.monotonic() - started_at) * 1000,
            extractor_status="failed",
        )
        raise HTTPException(status_code=500, detail="extraction_failed") from exc

    validated.trace_id = run_id
    record_extract(
        trace_id=run_id, doc_type="medication_list", document_sha256=document_sha256,
        patient_uuid_hash=patient_uuid_hash,
        extracted_field_count=validated.extracted_field_count,
        dropped_field_count=validated.dropped_field_count,
        duration_ms=(time.monotonic() - started_at) * 1000,
    )
    return validated.model_dump(mode="json")


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


class _RagRetrieveRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    top_k: int = Field(5, ge=1, le=20)


@router.post(
    "/v1/rag/retrieve",
    dependencies=[Depends(require_gateway_secret)],
    summary="Retrieve guideline chunks from the Week 2 RAG runtime.",
)
async def rag_retrieve(body: _RagRetrieveRequest) -> dict[str, Any]:
    from .rag import retrieve_guidelines

    chunks = retrieve_guidelines(body.query, body.top_k)
    return {
        "query": body.query,
        "chunks": [chunk.model_dump(mode="json") for chunk in chunks],
    }


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
        graph_started = time.monotonic()
        final_state: CopilotState = await graph.ainvoke(initial_state)
        graph_elapsed_ms = (time.monotonic() - graph_started) * 1000.0
    except Exception as exc:
        logger.error("Graph execution failed for trace_id=%s: %s", run_id, exc)
        raise HTTPException(status_code=500, detail="graph_execution_failed") from exc

    # Emit a graph-completion span for Langfuse / log scrapers (AgDR-0055; PHI-safe via observability.scrub_phi).
    # Per Team C 2026-05-10 followup: the endpoint runs the graph but never recorded the completion span.
    try:
        from .observability import record_graph_span
        record_graph_span(
            trace_id=run_id,
            node_name="graph_complete",
            graph_path=final_state.get("graph_path", []),
            worker_handoffs=final_state.get("worker_handoffs", []),
            decision_reason=final_state.get("decision_reason", ""),
            duration_ms=graph_elapsed_ms,
        )
    except Exception as span_exc:
        # Span recording must never break the response path.
        logger.warning("record_graph_span failed for trace_id=%s: %s", run_id, span_exc)

    verified = final_state.get("verified_response")
    if verified is None:
        raise HTTPException(status_code=500, detail="verifier_produced_no_response")

    return JSONResponse(content=verified)
