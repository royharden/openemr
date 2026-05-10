"""Wk2 sidecar routes — contract-freeze stubs (Plan §5 step 7, §6).

This module locks the URL surface for parallel teams:
  - ``POST /v1/extract/lab-pdf``      — Workstream A (lab PDF extractor)
  - ``POST /v1/extract/intake-form``  — Workstream A (intake-form extractor)
  - ``POST /v1/copilot/answer``       — Workstream C (LangGraph entrypoint)

All three return HTTP 501 Not Implemented at W0.5. Teams A and C replace the
bodies in their own PRs without renaming the paths or changing the response
envelope (``ExtractedDocument`` / ``VerifiedResponse``).

Routes go through the shared ``require_gateway_secret`` dependency so the
auth contract is identical to the existing /v1/brief and /v1/tool-plan
endpoints — gateway-secret + (optional) task-token.

(AgDR-0044: contract-freeze artifact for Wk2 parallel teams.)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from .auth import require_gateway_secret

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


@router.post(
    "/v1/copilot/answer",
    dependencies=[Depends(require_gateway_secret)],
    status_code=501,
    summary="[W0.5 stub] LangGraph supervisor entrypoint.",
)
def copilot_answer() -> dict[str, str]:
    """Workstream C deliverable. Returns ``VerifiedResponse``.

    Stub at W0.5 — the body is implemented in the Workstream C PR.
    """

    raise HTTPException(
        status_code=501,
        detail="not_implemented_workstream_c",
    )
